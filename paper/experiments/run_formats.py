"""E6: format robustness. The same facts are written into 8 file formats and pushed through the real parsers/chunker/retriever.
Measures (a) extraction: is the fact sentence recoverable verbatim from some chunk, (b) retrieval of that fact (hybrid, no ACL).
Writes results_formats.json.
"""
import asyncio, io, json, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_experiments as rx  # noqa: E402  (sets sys.path / cwd for the backend)
import docx, openpyxl, pptx, pymupdf  # noqa: E402
from pptx.util import Inches  # noqa: E402
from corpus import build  # noqa: E402

norm = lambda t: " ".join(t.split())


def make(fmt, d):
    sents = [f.sentence for f in d.facts]
    if fmt == "md":
        return d.text.encode()
    if fmt == "txt":
        return "\n\n".join([d.title] + sents).encode()
    if fmt == "html":
        return ("<html><head><title>%s</title><style>p{}</style></head><body><nav>menu</nav><h1>%s</h1>%s</body></html>"
                % (d.title, d.title, "".join(f"<p>{s}</p>" for s in sents))).encode()
    if fmt == "docx":
        x = docx.Document(); x.add_heading(d.title, 1)
        for s in sents: x.add_paragraph(s)
        b = io.BytesIO(); x.save(b); return b.getvalue()
    if fmt == "xlsx":
        wb = openpyxl.Workbook(); ws = wb.active; ws.title = d.title[:30]; ws.append(["Provision", "Statement"])
        for i, s in enumerate(sents, 1): ws.append([f"P{i}", s])
        b = io.BytesIO(); wb.save(b); return b.getvalue()
    if fmt == "csv":
        import csv
        b = io.StringIO(); w = csv.writer(b); w.writerow(["Provision", "Statement"])
        for i, s in enumerate(sents, 1): w.writerow([f"P{i}", s])
        return b.getvalue().encode()
    if fmt == "pptx":
        p = pptx.Presentation()
        for s in sents:
            sl = p.slides.add_slide(p.slide_layouts[1]); sl.shapes.title.text = d.title; sl.placeholders[1].text = s
        b = io.BytesIO(); p.save(b); return b.getvalue()
    if fmt == "pdf":
        doc = pymupdf.open(); page = doc.new_page(); page.insert_textbox(pymupdf.Rect(60, 60, 540, 120), d.title, fontsize=16)
        y = 130
        for s in sents:
            page.insert_textbox(pymupdf.Rect(60, y, 540, y + 50), s, fontsize=11); y += 55
        return doc.tobytes()
    raise ValueError(fmt)


async def main():
    docs, queries = build(11)
    docs = [d for d in docs if d.classification in ("General_Internal", "Public")][:20]
    qs = [q for q in queries if q.kind == "answerable" and q.variant == "orig" and q.doc_id in {d.id for d in docs}]
    fact_of = {(f.topic, f.entity): f for d in docs for f in d.facts}
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        for fmt in ("md", "txt", "html", "docx", "xlsx", "csv", "pptx", "pdf"):
            db = await rx.fresh_db(str(Path(tmp) / fmt)); Path(tmp, fmt).mkdir(exist_ok=True)
            db = await rx.fresh_db(str(Path(tmp) / fmt))
            emb, chunk_text, rows, ts = rx.embedder(), {}, [], rx.dbmod.now()
            for d in docs:
                parsed = rx.parse_document(f"{d.id}.{fmt}", make(fmt, d))
                chunks = rx.chunk_blocks(parsed.title, parsed.blocks)
                vecs = emb.embed_passages([c.embed_text for c in chunks]); did = f"doc-{d.id}"
                await db.execute("insert into documents (id, tenant_id, title, filename, file_type, file_size, checksum, classification, status,"
                                 " created_at, updated_at) values (?,?,?,?,?,?,?,?,'ready',?,?)", did, rx.T, d.title, f"{d.id}.{fmt}", fmt, 1, did,
                                 d.classification, ts, ts)
                for c, v in zip(chunks, vecs):
                    cid = rx.dbmod.new_id(); chunk_text[cid] = norm(c.content)
                    rows.append((cid, did, rx.T, c.index, c.page, c.section, c.kind, c.content, c.tokens, d.classification,
                                 json.dumps(rx.roles_for_classification(d.classification)), rx.dbmod.vec(v)))
            async with db.acquire() as conn:
                async with conn.transaction():
                    await conn.executemany("insert into chunks (id, document_id, tenant_id, chunk_index, page, section, kind, content, token_count,"
                                           " classification, allowed_roles, embedding) values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
            facts = [f for d in docs for f in d.facts]
            extracted = sum(any(norm(f.sentence) in t for t in chunk_text.values()) for f in facts)
            r1 = r3 = n = 0
            for q in qs:
                gold = norm(fact_of[(q.topic, q.entity)].sentence)
                hits = await db.match_chunks(emb.embed_query(q.text), q.text, rx.T, rx.ALL_ROLES, 3)
                pos = next((i for i, h in enumerate(hits, 1) if gold in norm(h["content"])), None)
                n += 1; r1 += pos == 1; r3 += pos is not None
            out[fmt] = dict(facts=len(facts), extracted=extracted, extraction_rate=extracted / len(facts), queries=n,
                            recall_at_1=r1 / n, recall_at_3=r3 / n, chunks=len(chunk_text))
            print(fmt, out[fmt], flush=True)
            await rx.dbmod.close_pool()
    (HERE / "results_formats.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


asyncio.run(main())
