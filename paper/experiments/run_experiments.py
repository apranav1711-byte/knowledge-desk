"""Experiments for the paper. Uses the real Knowledge Desk pipeline end to end:
parser -> chunker -> bge-small embeddings -> SQLite store -> hybrid retrieval -> evidence-first answer guard.

    python run_experiments.py [--seeds 1 2 3 4 5] [--skip-scaling]

Writes results.json next to this file. Nothing here is hand-edited; the paper's tables and figures are generated from it.
"""
import argparse, asyncio, json, os, statistics as st, sys, tempfile, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parents[1] / "backend"))
os.chdir(HERE.parents[1] / "backend")

import numpy as np
from app.core import db as dbmod
from app.core.acl import ALL_ROLES, can_read, roles_for_classification
from app.services import answer as ans
from app.services.chunking import chunk_blocks
from app.services.embeddings import BgeEmbedder
from app.services.parsing import parse_document
from corpus import build

T = dbmod.DEFAULT_TENANT
EMB = None


def embedder():
    global EMB
    if EMB is None:
        EMB = BgeEmbedder()
    return EMB


async def fresh_db(tmp: str):
    dbmod.settings.DATA_DIR = Path(tmp)
    dbmod.settings.DATABASE_PATH = Path(tmp) / "bench.db"
    dbmod._db = None
    return await dbmod.init_pool()


async def ingest(db, docs):
    """Index documents through the real parse -> chunk -> embed path. Returns chunk_id -> fact sentences it contains."""
    emb, chunk_facts, rows = embedder(), {}, []
    for d in docs:
        parsed = parse_document(f"{d.id}.md", d.text.encode())
        chunks = chunk_blocks(parsed.title, parsed.blocks)
        vecs = emb.embed_passages([c.embed_text for c in chunks])
        ts = dbmod.now()
        did = f"doc-{d.id}"
        await db.execute("insert into documents (id, tenant_id, title, filename, file_type, file_size, checksum, classification,"
                         " status, created_at, updated_at) values (?,?,?,?,?,?,?,?,'ready',?,?)",
                         did, T, d.title, f"{d.id}.md", "md", len(d.text), did, d.classification, ts, ts)
        for c, v in zip(chunks, vecs):
            cid = dbmod.new_id()
            rows.append((cid, did, T, c.index, c.page, c.section, c.kind, c.content, c.tokens, d.classification,
                         json.dumps(roles_for_classification(d.classification)), dbmod.vec(v)))
            chunk_facts[cid] = [f for f in d.facts if f.sentence in c.content]
    async with db.acquire() as conn:
        async with conn.transaction():
            await conn.executemany("insert into chunks (id, document_id, tenant_id, chunk_index, page, section, kind, content,"
                                   " token_count, classification, allowed_roles, embedding) values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return chunk_facts


def qvecs(queries):
    emb = embedder()
    return [emb.embed_query(q.text) for q in queries]


def metrics_at(ranks, ks=(1, 3, 5, 10)):
    out = {f"recall@{k}": float(np.mean([r is not None and r <= k for r in ranks])) for k in ks}
    out["mrr"] = float(np.mean([1.0 / r if r else 0.0 for r in ranks]))
    return out


def gold_rank(hits, query, chunk_facts):
    for i, h in enumerate(hits, start=1):
        if any(f.doc_id == query.doc_id and f.entity == query.entity and f.topic == query.topic for f in chunk_facts[h["chunk_id"]]):
            return i
    return None


def hits_for(res):  # the same dict shape build_answer expects
    return [dict(r) for r in res]


def answer_has(text, sentence):
    return sentence in text


async def run_seed(seed, tmp):
    docs, queries = build(seed)
    db = await fresh_db(tmp)
    chunk_facts = await ingest(db, docs)
    all_facts = [f for d in docs for f in d.facts]
    fact_of = {(f.topic, f.entity): f for f in all_facts}
    ans_q = [q for q in queries if q.kind == "answerable"]
    una_q = [q for q in queries if q.kind == "unanswerable"]
    qv = dict(zip(map(id, queries), qvecs(queries)))
    res = {"seed": seed, "docs": len(docs), "chunks": len(chunk_facts), "facts": len(all_facts),
           "answerable": len(ans_q), "unanswerable": len(una_q),
           "chunks_per_doc": round(len(chunk_facts) / len(docs), 2)}

    # ---------------- E1: retrieval ablation (administrator sees everything, so this isolates ranking quality) -------------
    e1, e1v, cache_all = {}, {}, {}   # cache_all: hybrid, all roles, k=10 -> reused by E2 (post-filter / no-ACL), E3, E4
    for mode in ("lexical", "dense", "hybrid"):
        ranks, by_var = [], {"keyword": [], "synonym": []}
        for q in ans_q:
            hits = await db.match_chunks(qv[id(q)], q.text, T, ALL_ROLES, 10, mode)
            if mode == "hybrid": cache_all[id(q)] = hits
            r_ = gold_rank(hits, q, chunk_facts)
            ranks.append(r_); by_var["synonym" if q.variant == "syn" else "keyword"].append(r_)
        e1[mode] = metrics_at(ranks)
        e1v[mode] = {k: metrics_at(v) for k, v in by_var.items()}
    for q in una_q:
        cache_all[id(q)] = await db.match_chunks(qv[id(q)], q.text, T, ALL_ROLES, 10)
    res["E1_retrieval"] = e1
    res["E1_by_query_type"] = e1v

    print(f"  seed {seed}: E1 done", flush=True)
    # ---------------- E2: access control. every answerable query asked by every role -----------------------------------
    cache_pre = {}
    forbidden_by_role = {r: [f.sentence for f in all_facts if not can_read(r, f.classification)] for r in ALL_ROLES}
    systems = {"prefilter": dict(kind="pre"), "postfilter": dict(kind="post"), "no_acl": dict(kind="none")}
    e2 = {s: dict(auth_correct=0, auth_total=0, unauth_total=0, unauth_leak=0, unauth_abstain=0, unauth_hits_leak=0) for s in systems}
    for r in ALL_ROLES:
        forb = forbidden_by_role[r]
        for q in ans_q:
            gold = fact_of[(q.topic, q.entity)]
            authorized = can_read(r, q.classification)
            for name, cfg in systems.items():
                if cfg["kind"] == "pre":
                    hits = await db.match_chunks(qv[id(q)], q.text, T, [r], 10)
                    cache_pre[(r, id(q))] = hits
                elif cfg["kind"] == "post":
                    hits = [h for h in cache_all[id(q)] if can_read(r, h["classification"])]
                else:
                    hits = cache_all[id(q)]
                a = ans.build_answer(q.text, hits_for(hits))
                m = e2[name]
                if authorized:
                    m["auth_total"] += 1
                    m["auth_correct"] += answer_has(a.text, gold.sentence)
                else:
                    m["unauth_total"] += 1
                    m["unauth_abstain"] += a.mode == "fallback"
                    shown = a.text + " " + " ".join(s["excerpt"] for s in a.sources)
                    m["unauth_leak"] += any(s in shown for s in forb)
                    m["unauth_hits_leak"] += any(not can_read(r, h["classification"]) for h in hits[:5])
    res["E2_access"] = e2
    ksweep = {"prefilter": {}, "postfilter": {}}
    for k in (1, 2, 3, 5, 10):
        for name in ksweep:
            ok = tot = 0
            for r in ALL_ROLES:
                for q in ans_q:
                    if not can_read(r, q.classification): continue
                    gold = fact_of[(q.topic, q.entity)]
                    if name == "prefilter":
                        hits = cache_pre[(r, id(q))][:k]
                    else:
                        hits = [h for h in cache_all[id(q)][:k] if can_read(r, h["classification"])]
                    ok += answer_has(ans.build_answer(q.text, hits_for(hits)).text, gold.sentence); tot += 1
            ksweep[name][str(k)] = ok / tot
        print(f"  seed {seed}: k={k} pre={ksweep['prefilter'][str(k)]:.3f} post={ksweep['postfilter'][str(k)]:.3f}", flush=True)
    res["E2_ksweep"] = ksweep

    # ---------------- E3: answer guard (unanswerable questions + threshold sweep), administrator role -------------------
    sweep = {}
    for theta in (0.0, 0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8):
        dbmod.settings.RETRIEVAL_MIN_SCORE = theta
        corr = wrong = abst = false_ans = 0
        for q in ans_q:
            a = ans.build_answer(q.text, hits_for(cache_all[id(q)]))
            if a.mode == "fallback": abst += 1
            elif answer_has(a.text, fact_of[(q.topic, q.entity)].sentence): corr += 1
            else: wrong += 1
        for q in una_q:
            false_ans += ans.build_answer(q.text, hits_for(cache_all[id(q)])).mode != "fallback"
        n, u = len(ans_q), len(una_q)
        answered = corr + wrong + false_ans
        sweep[str(theta)] = dict(correct=corr / n, wrong_entity=wrong / n, abstain_answerable=abst / n,
                                 false_answer_unanswerable=false_ans / u,
                                 precision=corr / answered if answered else 1.0)
    dbmod.settings.RETRIEVAL_MIN_SCORE = 0.55
    res["E3_guard"] = sweep

    def strict(q, hits, tau):
        """Stricter guard: after the standard guard, every quoted sentence must itself cover >= tau of the question's terms."""
        a = ans.build_answer(q.text, hits_for(hits))
        if a.mode == "fallback": return a
        lines = [ln.replace("[C1]", "").replace("[C2]", "").replace("[C3]", "").strip() for ln in a.text.splitlines()]
        lines = [ln for ln in lines if ln and not ln.startswith("|")] or lines
        best = max((ans.coverage(q.text, ln) for ln in lines), default=0.0)
        return a if best >= tau else ans.Answer(ans.FALLBACK, "fallback", [], "sentence_coverage")
    strict_res = {}
    for tau in (0.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
        for variant in ("all", "keyword", "synonym"):
            sel = [q for q in ans_q if variant == "all" or (q.variant == "syn") == (variant == "synonym")]
            corr = wrong = abst = 0
            for q in sel:
                a = strict(q, cache_all[id(q)], tau)
                if a.mode == "fallback": abst += 1
                elif answer_has(a.text, fact_of[(q.topic, q.entity)].sentence): corr += 1
                else: wrong += 1
            fa = [q for q in una_q if variant == "all" or (q.variant == "syn") == (variant == "synonym")]
            false_ans = sum(strict(q, cache_all[id(q)], tau).mode != "fallback" for q in fa)
            answered = corr + wrong + false_ans
            strict_res[f"{tau}|{variant}"] = dict(correct=corr / len(sel), wrong_entity=wrong / len(sel), abstain_answerable=abst / len(sel),
                                                 false_answer_unanswerable=false_ans / len(fa), precision=corr / answered if answered else 1.0)
    res["E3_strict_guard"] = strict_res

    # ---------------- E4: faithfulness of produced answers (extractive by construction, verified empirically) -------------
    verbatim = total = 0
    for q in ans_q[:400]:
        hits = hits_for(cache_all[id(q)])
        a = ans.build_answer(q.text, hits)
        if a.mode == "fallback": continue
        corpus_text = " ".join(h["content"] for h in hits)
        for line in a.text.replace("[C1]", "").replace("[C2]", "").replace("[C3]", "").splitlines():
            line = line.strip()
            if line and not line.startswith("|"):
                total += 1; verbatim += line in corpus_text or line in " ".join(" ".join(h["content"].split()) for h in hits)
    res["E4_faithfulness"] = dict(answer_lines=total, verbatim_lines=verbatim, rate=verbatim / total if total else None)
    await dbmod.close_pool()
    return res


async def audit_experiment(tmp):
    """E7: tamper detection in the hash-chained audit log."""
    import random
    out = {}
    for n in (1000, 5000):
        db = await fresh_db(tmp + f"/audit{n}")
        for i in range(n):
            await db.append_audit(T, None, "u@x.y", "admin", "query", f"q{i}", "a", "extractive_answer", [], 0.5, 10, {"i": i})
        t0 = time.perf_counter(); ok = await db.verify_audit(T); vt = time.perf_counter() - t0
        rng, detected, trials = random.Random(5), 0, 40
        await db.execute("drop trigger audit_logs_no_update"); await db.execute("drop trigger audit_logs_no_delete")
        for k in range(trials):
            seq = rng.randint(1, n)
            kind = k % 3
            orig = await db.fetchrow("select * from audit_logs where seq=?", seq)
            if kind == 0: await db.execute("update audit_logs set query='forged' where seq=?", seq)           # edit content
            elif kind == 1: await db.execute("delete from audit_logs where seq=?", seq)                        # delete record
            else: await db.execute("update audit_logs set prev_hash=? where seq=?", "f" * 64, seq)             # break link
            detected += not (await db.verify_audit(T))["valid"]
            cols = ",".join(orig); await db.execute("delete from audit_logs where seq=?", seq)
            await db.execute(f"insert into audit_logs ({cols}) values ({','.join('?' * len(orig))})", *orig.values())
        out[str(n)] = dict(records=n, clean_chain_valid=ok["valid"], verify_seconds=round(vt, 3), tamper_trials=trials, detected=detected)
        await dbmod.close_pool()
    return out


async def scaling_experiment(tmp):
    """E5: retrieval latency vs index size (brute-force vectors + FTS5 + role pre-filter)."""
    import random
    docs, queries = build(1)
    base_texts = [s.sentence for d in docs for s in d.facts]
    qs = qvecs([q for q in queries if q.kind == "answerable"][:60])
    out = {}
    rng = np.random.default_rng(0); pyr = random.Random(0)
    for n in (1000, 5000, 20000, 50000):
        db = await fresh_db(tmp + f"/scale{n}")
        vecs = rng.standard_normal((n, 384)).astype(np.float32); vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        roles = [json.dumps(roles_for_classification(c)) for c in ("Public", "General_Internal", "Management", "HR_Confidential", "Restricted")]
        ts = dbmod.now()
        await db.execute("insert into documents (id, tenant_id, title, filename, file_type, file_size, checksum, classification, status,"
                         " created_at, updated_at) values ('d',?,'t','f','md',1,'c','Public','ready',?,?)", T, ts, ts)
        rows = [(dbmod.new_id(), "d", T, i, 1, "", "text", base_texts[pyr.randrange(len(base_texts))] + f" ref{i}", 30, "Public",
                 pyr.choice(roles), dbmod.vec(vecs[i])) for i in range(n)]
        async with db.acquire() as conn:
            async with conn.transaction():
                await conn.executemany("insert into chunks (id, document_id, tenant_id, chunk_index, page, section, kind, content,"
                                       " token_count, classification, allowed_roles, embedding) values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        lat = {}
        for role in ("employee", "admin"):
            ts_ = []
            for i, v in enumerate(qs):
                t0 = time.perf_counter(); await db.match_chunks(v, "annual leave days engineering " + str(i), T, [role], 10)
                ts_.append((time.perf_counter() - t0) * 1000)
            lat[role] = dict(p50_ms=round(float(np.percentile(ts_, 50)), 1), p95_ms=round(float(np.percentile(ts_, 95)), 1))
        out[str(n)] = lat
        print("  scaling", n, lat, flush=True)
        await dbmod.close_pool()
    return out


def aggregate(runs):
    def agg(path):
        vals = []
        for r in runs:
            x = r
            for p in path: x = x[p]
            vals.append(x)
        return vals
    return {"n_runs": len(runs)}


async def main(seeds, skip_scaling):
    out = {"seeds": [], "embedding_model": "BAAI/bge-small-en-v1.5 (ONNX, int8)", "platform": sys.platform}
    with tempfile.TemporaryDirectory() as tmp:
        for s in seeds:
            t0 = time.perf_counter()
            Path(tmp, f"s{s}").mkdir()
            r = await run_seed(s, str(Path(tmp, f"s{s}")))
            out["seeds"].append(r)
            print(f"seed {s}: {r['docs']} docs, {r['chunks']} chunks, {time.perf_counter() - t0:.0f}s | "
                  f"hybrid R@1={r['E1_retrieval']['hybrid']['recall@1']:.3f} | prefilter leak={r['E2_access']['prefilter']['unauth_leak']} "
                  f"| no_acl leak={r['E2_access']['no_acl']['unauth_leak']}/{r['E2_access']['no_acl']['unauth_total']}", flush=True)
        for sub in ("audit", "scale"):
            Path(tmp, sub).mkdir(exist_ok=True)
        out["E7_audit"] = await audit_experiment(str(Path(tmp, "audit")))
        print("audit:", out["E7_audit"], flush=True)
        if not skip_scaling:
            out["E5_scaling"] = await scaling_experiment(str(Path(tmp, "scale")))
    (HERE / "results.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("wrote results.json")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5]); ap.add_argument("--skip-scaling", action="store_true")
    a = ap.parse_args(); asyncio.run(main(a.seeds, a.skip_scaling))
