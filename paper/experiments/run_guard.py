"""E3b: entity-span guard. Requires every named-entity span of the question (runs of capitalised / coded tokens, e.g.
"Engineering (Bengaluru)", "G5-technical", "Project Cedar-2") to appear verbatim in the quoted sentence.
Compared with the deployed guard and the sentence-coverage guard. Writes results_guard.json.
"""
import asyncio, json, re, statistics as st, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_experiments as rx  # noqa: E402
from corpus import build  # noqa: E402

ans = rx.ans
CITE = re.compile(r"\s*\[C\d\]")


def entity_spans(question: str) -> list[str]:
    toks, spans, cur = question.rstrip("?.! ").split(), [], []
    for i, t in enumerate(toks):
        core = t.strip(",;:")
        ent = i > 0 and (core[:1].isupper() or core[:1].isdigit() or core.startswith("(") or "-" in core and any(c.isdigit() for c in core))
        if ent: cur.append(core)
        elif cur: spans.append(" ".join(cur)); cur = []
    if cur: spans.append(" ".join(cur))
    return spans


def quoted_lines(a):
    ls = [CITE.sub("", ln).strip() for ln in a.text.splitlines()]
    return [ln for ln in ls if ln]


def esg(q, hits, with_standard=True):
    a = ans.build_answer(q.text, [dict(h) for h in hits])
    if a.mode == "fallback" and with_standard: return a
    if a.mode == "fallback": return a
    spans = entity_spans(q.text)
    text = " ".join(quoted_lines(a)).lower()
    return a if all(s.lower() in text for s in spans) else ans.Answer(ans.FALLBACK, "fallback", [], "entity_span")


def tally(sel_a, sel_u, fn, fact_of, cache):
    corr = wrong = abst = 0
    for q in sel_a:
        a = fn(q, cache[id(q)])
        if a.mode == "fallback": abst += 1
        elif fact_of[(q.topic, q.entity)].sentence in a.text: corr += 1
        else: wrong += 1
    fa = sum(fn(q, cache[id(q)]).mode != "fallback" for q in sel_u)
    n, u = len(sel_a), len(sel_u)
    answered = corr + wrong + fa
    return dict(correct=corr / n, wrong_entity=wrong / n, abstain_answerable=abst / n, false_answer_unanswerable=fa / u,
                precision=corr / answered if answered else 1.0)


async def seed_run(seed, tmp):
    docs, queries = build(seed)
    db = await rx.fresh_db(tmp)
    await rx.ingest(db, docs)
    fact_of = {(f.topic, f.entity): f for d in docs for f in d.facts}
    qv = dict(zip(map(id, queries), rx.qvecs(queries)))
    cache = {id(q): await db.match_chunks(qv[id(q)], q.text, rx.T, rx.ALL_ROLES, 10) for q in queries}
    std = lambda q, h: ans.build_answer(q.text, [dict(x) for x in h])

    def strict08(q, h):
        a = std(q, h)
        if a.mode == "fallback": return a
        best = max((ans.coverage(q.text, ln) for ln in quoted_lines(a) if not ln.startswith("|")), default=0.0)
        return a if best >= 0.8 else ans.Answer(ans.FALLBACK, "fallback", [], "cov")

    out = {}
    for name, fn in (("standard", std), ("sentence_coverage_0.8", strict08), ("entity_span", lambda q, h: esg(q, h))):
        out[name] = {}
        for var in ("all", "keyword", "synonym"):
            sa = [q for q in queries if q.kind == "answerable" and (var == "all" or (q.variant == "syn") == (var == "synonym"))]
            su = [q for q in queries if q.kind == "unanswerable" and (var == "all" or (q.variant == "syn") == (var == "synonym"))]
            out[name][var] = tally(sa, su, fn, fact_of, cache)

    # silent substitution: unauthorised questions answered (without leaking) from readable near-duplicate documents
    sub = {"standard": [0, 0], "entity_span": [0, 0]}
    for role in ("employee", "manager", "hr"):
        for q in queries:
            if q.kind != "answerable" or rx.can_read(role, q.classification): continue
            hits = await db.match_chunks(qv[id(q)], q.text, rx.T, [role], 10)
            sub["standard"][1] += 1; sub["entity_span"][1] += 1
            sub["standard"][0] += std(q, hits).mode != "fallback"
            sub["entity_span"][0] += esg(q, hits).mode != "fallback"
    out["unauthorised_answered"] = {k: dict(answered=v[0], total=v[1], rate=v[0] / v[1]) for k, v in sub.items()}
    await rx.dbmod.close_pool()
    return out


async def main():
    res = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in (1, 2, 3, 4, 5):
            Path(tmp, f"s{s}").mkdir()
            r = await seed_run(s, str(Path(tmp, f"s{s}")))
            res.append(r)
            print(f"seed {s}: ESG all={ {k: round(v, 3) for k, v in r['entity_span']['all'].items()} } | substitution {r['unauthorised_answered']}", flush=True)
    (HERE / "results_guard.json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print("wrote results_guard.json")

asyncio.run(main())
