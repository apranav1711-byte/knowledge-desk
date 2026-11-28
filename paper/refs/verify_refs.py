"""Look up every candidate reference in arXiv / Crossref and build refs.bib from the *retrieved* metadata.
A reference is only written to refs.bib if the retrieved title matches the requested one (similarity >= 0.85).
Usage: python verify_refs.py   ->  refs.bib + verification_report.md
"""
import difflib, json, re, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).parent
UA = {"User-Agent": "reference-verifier/1.0"}
ATOM = {"a": "http://www.w3.org/2005/Atom"}

# key, title to look up, source ("arxiv" or a Crossref DOI), note on why it is cited
REFS = [
    ("lewis2020rag", "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks", "arxiv", "RAG origin"),
    ("karpukhin2020dpr", "Dense Passage Retrieval for Open-Domain Question Answering", "arxiv", "dense retrieval"),
    ("guu2020realm", "REALM: Retrieval-Augmented Language Model Pre-Training", "arxiv", "retrieval-augmented LMs"),
    ("izacard2021fid", "Leveraging Passage Retrieval with Generative Models for Open Domain Question Answering", "arxiv", "FiD"),
    ("asai2023selfrag", "Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection", "arxiv", "Self-RAG"),
    ("gao2023ragsurvey", "Retrieval-Augmented Generation for Large Language Models: A Survey", "arxiv", "RAG survey"),
    ("barnett2024failure", "Seven Failure Points When Engineering a Retrieval Augmented Generation System", "arxiv", "RAG failure points"),
    ("xiao2023cpack", "C-Pack: Packed Resources For General Chinese Embeddings", "arxiv", "BGE embeddings"),
    ("reimers2019sbert", "Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks", "arxiv", "sentence embeddings"),
    ("thakur2021beir", "BEIR: A Heterogeneous Benchmark for Zero-shot Evaluation of Information Retrieval Models", "arxiv", "IR benchmark"),
    ("es2023ragas", "RAGAS: Automated Evaluation of Retrieval Augmented Generation", "arxiv", "RAG evaluation"),
    ("saadfalcon2023ares", "ARES: An Automated Evaluation Framework for Retrieval-Augmented Generation Systems", "arxiv", "RAG evaluation"),
    ("ji2023hallucination", "Survey of Hallucination in Natural Language Generation", "arxiv", "hallucination survey"),
    ("huang2023hallucination", "A Survey on Hallucination in Large Language Models: Principles, Taxonomy, Challenges, and Open Questions", "arxiv", "hallucination survey"),
    ("liu2023lost", "Lost in the Middle: How Language Models Use Long Contexts", "arxiv", "long context"),
    ("rajpurkar2016squad", "SQuAD: 100,000+ Questions for Machine Comprehension of Text", "arxiv", "extractive QA"),
    ("rajpurkar2018squad2", "Know What You Don't Know: Unanswerable Questions for SQuAD", "arxiv", "unanswerable questions"),
    ("zou2024poisonedrag", "PoisonedRAG: Knowledge Corruption Attacks to Retrieval-Augmented Generation of Large Language Models", "arxiv", "RAG security"),
    ("zeng2024privacy", "The Good and The Bad: Exploring Privacy Issues in Retrieval-Augmented Generation (RAG)", "arxiv", "RAG privacy"),
    ("greshake2023indirect", "Not what you've signed up for: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection", "arxiv", "prompt injection"),
    ("malkov2018hnsw", "Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs", "10.1109/TPAMI.2018.2889473", "ANN index"),
    ("johnson2019faiss", "Billion-scale similarity search with GPUs", "arxiv", "vector search"),
    ("cormack2009rrf", "Reciprocal rank fusion outperforms condorcet and individual rank learning methods", "10.1145/1571941.1572114", "RRF"),
    ("robertson2009bm25", "The Probabilistic Relevance Framework: BM25 and Beyond", "10.1561/1500000019", "BM25"),
    ("sandhu1996rbac", "Role-based access control models", "10.1109/2.485845", "RBAC"),
    ("ferraiolo2001nist", "Proposed NIST standard for role-based access control", "10.1145/501978.501980", "RBAC standard"),
    ("schneier1999audit", "Secure audit logs to support computer forensics", "10.1145/317087.317089", "tamper-evident logs"),
    ("crosby2009tamper", "Efficient Data Structures for Tamper-Evident Logging", "usenix", "tamper-evident logs"),
]
EXTRA = HERE / "extra_candidates.json"  # optional: [{"key","title","source","note"}] added after web search
if EXTRA.exists():
    REFS += [(r["key"], r["title"], r["source"], r["note"]) for r in json.loads(EXTRA.read_text(encoding="utf-8"))]


def sim(a: str, b: str) -> float:
    n = lambda s: re.sub(r"[^a-z0-9 ]", "", s.lower())
    return difflib.SequenceMatcher(None, n(a), n(b)).ratio()


def get(url: str) -> bytes:
    for attempt in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30).read()
        except Exception:
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"fetch failed: {url}")


def _arxiv_query(q: str):
    root = ET.fromstring(get(f"https://export.arxiv.org/api/query?search_query={urllib.parse.quote(q)}&max_results=8"))
    time.sleep(4)  # arXiv API etiquette: one request every few seconds
    return root.findall("a:entry", ATOM)


def from_arxiv(title: str):
    # 1) exact phrase on the title; 2) distinctive words; keep the best-matching entry across both
    words = [w for w in re.findall(r"[A-Za-z0-9]+", title) if len(w) > 3]
    best = None
    for q in (f'ti:"{title}"', " AND ".join(f"ti:{w}" for w in words[:6])):
        for e in _arxiv_query(q):
            t = re.sub(r"\s+", " ", e.find("a:title", ATOM).text).strip()
            sc = sim(t, title)
            if best is None or sc > best[0]:
                best = (sc, e, t)
        if best and best[0] >= 0.92:
            break
    if not best:
        return None
    s, e, t = best
    arx = e.find("a:id", ATOM).text.rsplit("/abs/", 1)[1]
    authors = [a.find("a:name", ATOM).text for a in e.findall("a:author", ATOM)]
    year = e.find("a:published", ATOM).text[:4]
    doi = e.find("{http://arxiv.org/schemas/atom}doi")
    return dict(score=s, title=t, authors=authors, year=year, arxiv=arx.split("v")[0], doi=doi.text if doi is not None else None,
                url=f"https://arxiv.org/abs/{arx.split('v')[0]}", type="misc")


def from_crossref(doi: str):
    j = json.loads(get(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}"))["message"]
    authors = [f"{a.get('given', '')} {a.get('family', '')}".strip() for a in j.get("author", [])]
    year = str((j.get("issued") or j.get("published") or {}).get("date-parts", [[None]])[0][0])
    return dict(title=re.sub(r"<[^>]+>", "", j["title"][0]), authors=authors, year=year, doi=doi,
                venue=(j.get("container-title") or [""])[0], volume=j.get("volume"), pages=j.get("page"),
                issue=j.get("issue"), publisher=j.get("publisher"), url=f"https://doi.org/{doi}", type=j.get("type"))


def from_usenix(title: str):
    j = json.loads(get("https://api.crossref.org/works?rows=5&query.bibliographic=" + urllib.parse.quote(title + " Crosby Wallach")))
    for it in j["message"]["items"]:
        t = re.sub(r"<[^>]+>", "", (it.get("title") or [""])[0])
        if sim(t, title) >= 0.85:
            return from_crossref(it["DOI"]) if it.get("DOI") else None
    # Not in Crossref: USENIX Security 2009 (verified manually against the USENIX proceedings page below)
    return None


def bibtex(key, m):
    names = " and ".join(f"{a.split()[-1]}, {' '.join(a.split()[:-1])}" if len(a.split()) > 1 else a for a in m["authors"])
    f = [f"  author = {{{names}}}", f"  title = {{{{{m['title']}}}}}", f"  year = {{{m['year']}}}"]
    if m.get("arxiv") and not m.get("venue"):
        f += [f"  journal = {{arXiv preprint arXiv:{m['arxiv']}}}"]
    else:
        f += [f"  journal = {{{m.get('venue', '')}}}"]
        for k, n in (("volume", "volume"), ("issue", "number"), ("pages", "pages")):
            if m.get(k): f.append(f"  {n} = {{{m[k]}}}")
    if m.get("doi"): f.append(f"  doi = {{{m['doi']}}}")
    f.append(f"  url = {{{m['url']}}}")
    return f"@article{{{key},\n" + ",\n".join(f) + "\n}\n"


bib, report, ok = [], ["| Key | Requested title | Retrieved title | Year | Match | Source |", "| --- | --- | --- | --- | --- | --- |"], 0
for key, title, src, note in REFS:
    try:
        m = from_arxiv(title) if src == "arxiv" else from_usenix(title) if src == "usenix" else from_crossref(src)
    except Exception as ex:
        m = None; print("ERR  ", key, str(ex)[:100])
    if not m:
        report.append(f"| {key} | {title} | NOT FOUND | | NO | {src} |"); print("MISS ", key); continue
    s = sim(m["title"], title)
    good = s >= 0.85
    if good:
        bib.append(bibtex(key, m)); ok += 1
    report.append(f"| {key} | {title} | {m['title']} | {m['year']} | {'yes (%.2f)' % s if good else 'NO (%.2f)' % s} | {'arXiv:' + m['arxiv'] if m.get('arxiv') else 'doi:' + str(m.get('doi'))} |")
    print("OK   " if good else "WEAK ", key, m["year"], m["title"][:70])
(HERE / "refs.bib").write_text("\n".join(bib), encoding="utf-8")
(HERE / "verification_report.md").write_text("# Reference verification\n\nEach entry was looked up live in arXiv or Crossref; only entries whose retrieved title matches (>= 0.85) are in refs.bib.\n\n" + "\n".join(report) + "\n", encoding="utf-8")
print(f"\n{ok}/{len(REFS)} verified")
