"""Evidence-first extractive answering (no LLM).

Selects supported sentences / table rows from the retrieved, already-authorised chunks and cites them as [C1], [C2].
If the evidence is not sufficient it says so instead of guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import settings

FALLBACK = "I cannot find sufficient information within the documents available to your account."

_STOP = set(
    "a an the what which who when where why how many much is are was were do does did can could should would will may "
    "i we you they our their your my me to of for in on at by with from and or if per get have has be been please tell "
    "explain show about according company employee employees policy policies".split()
)


def terms(text: str) -> set[str]:
    return {w.rstrip("s") for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 1}


def coverage(question: str, passage: str) -> float:
    wanted = terms(question)
    return len(wanted & terms(passage)) / len(wanted) if wanted else 0.0


def is_supported(question: str, hit: dict) -> bool:
    """Conservative guard: strong semantic match with decent term coverage, or near-complete exact-term coverage
    (identifiers, codes). A heuristic, not entailment proof."""
    cov = coverage(question, hit["content"])
    return (hit["dense_score"] >= settings.RETRIEVAL_MIN_SCORE and cov >= 0.5) or cov >= 0.8


def _best_sentences(question: str, hit: dict, limit: int = 2) -> list[str]:
    q = terms(question)
    if hit["kind"] == "table":
        lines = hit["content"].splitlines()
        header, rows = lines[:2], lines[2:]
        scored = sorted(((len(q & terms(r)), i, r) for i, r in enumerate(rows)), reverse=True)
        best = scored[0][0] if scored else 0  # only the rows that match the question best, not every partial match
        picked = [(i, r) for s, i, r in scored[: limit + 1] if s > 0 and s == best]
        if not picked:
            return []
        return ["\n".join(header + [r for _, r in sorted(picked)])]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", hit["content"]) if len(s.strip()) > 3]
    scored = sorted(((len(q & terms(s)), -i, s) for i, s in enumerate(sentences)), reverse=True)
    best, keys = [], set()
    for sc, neg, s in scored:
        if sc <= 0 or len(best) >= limit:
            break
        k = s.lower()
        if k not in keys:  # a passage may repeat the same sentence
            keys.add(k)
            best.append((-neg, s))
    return [s for _, s in sorted(best)]


def _near_dup(a: frozenset, b: frozenset) -> bool:
    """Same fact quoted twice (e.g. identical policy text in two files, or a PDF line-break split a word).
    Sentences whose numbers differ are never treated as duplicates: different numbers are different facts."""
    num = lambda s: {w for w in s if any(ch.isdigit() for ch in w)}
    if num(a) != num(b):
        return False
    return a <= b or len(a & b) / len(a | b) >= 0.7


@dataclass
class Answer:
    text: str
    mode: str  # 'extractive_answer' | 'fallback'
    sources: list[dict]
    reason: str | None = None


def build_answer(question: str, hits: list[dict], max_sources: int = 3) -> Answer:
    supported = [h for h in hits if is_supported(question, h)]
    if not supported:
        return Answer(FALLBACK, "fallback", [], "insufficient_evidence")
    sources, parts, seen = [], [], set()
    for hit in supported:
        if len(sources) >= max_sources:
            break
        picked = []
        for s in _best_sentences(question, hit):  # drop sentences already quoted (same or near-same text elsewhere)
            if hit["kind"] == "table":
                if s not in seen:
                    seen.add(s)
                    picked.append(s)
                continue
            t = frozenset(terms(s))
            if t and not any(_near_dup(t, prev) for prev in seen if isinstance(prev, frozenset)):
                seen.add(t)
                picked.append(s)
        if not picked:
            continue
        cid = f"C{len(sources) + 1}"
        sources.append(
            dict(
                id=cid, chunk_id=str(hit["chunk_id"]), document_id=str(hit["document_id"]), title=hit["title"],
                page=hit["page"], section=hit["section"], kind=hit["kind"], excerpt=hit["content"],
                classification=hit["classification"], score=round(hit["dense_score"], 4),
                lexical=round(hit["lexical_score"], 4),
            )
        )
        parts.append("\n".join(picked) + f" [{cid}]" if hit["kind"] != "table" else "\n".join(picked) + f"\n[{cid}]")
    if not sources:
        return Answer(FALLBACK, "fallback", [], "insufficient_evidence")
    return Answer("\n\n".join(parts), "extractive_answer", sources)
