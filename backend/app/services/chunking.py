"""Heading-aware chunking.

* Text: sentences are packed to ~300 tokens with ~50 tokens of overlap, never crossing a section boundary.
* Tables: split by rows to ~300 tokens with the header row repeated, so every table chunk is self-describing.
* Each chunk keeps (page, section) provenance; the embedded text is prefixed with "Title > Section" for context,
  while the stored/cited content stays exactly as in the source.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.parsing import Block

TARGET_TOKENS = 300
OVERLAP_TOKENS = 50
MAX_TOKENS = 450


def approx_tokens(text: str) -> int:
    return int(len(re.findall(r"\S+", text)) * 1.3) + 1


@dataclass
class Chunk:
    index: int
    page: int
    section: str
    kind: str
    content: str
    embed_text: str
    tokens: int


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(\[])|\n+")


def _sentences(text: str) -> list[str]:
    out = []
    for part in _SENT.split(text):
        part = part.strip()
        if not part:
            continue
        words = part.split()
        # Hard-split pathological run-on sentences.
        step = int(MAX_TOKENS / 1.3)
        for i in range(0, len(words), step):
            out.append(" ".join(words[i : i + step]))
    return out


def _pack(sentences: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Pack (page, sentence) into (page, text) windows with sentence-level overlap."""
    chunks: list[tuple[int, str]] = []
    cur: list[tuple[int, str]] = []
    cur_tokens = 0
    for page, sent in sentences:
        t = approx_tokens(sent)
        if cur and cur_tokens + t > TARGET_TOKENS:
            chunks.append((cur[0][0], " ".join(s for _, s in cur)))
            tail, tail_tokens = [], 0
            for item in reversed(cur):  # carry ~OVERLAP_TOKENS of trailing sentences forward
                tail_tokens += approx_tokens(item[1])
                if tail_tokens > OVERLAP_TOKENS:
                    break
                tail.insert(0, item)
            cur, cur_tokens = tail, sum(approx_tokens(s) for _, s in tail)
        cur.append((page, sent))
        cur_tokens += t
    if cur:
        chunks.append((cur[0][0], " ".join(s for _, s in cur)))
    return chunks


def _split_table(md: str) -> list[str]:
    lines = md.splitlines()
    if len(lines) <= 2:
        return [md]
    header, rows = lines[:2], lines[2:]
    out, cur, tokens = [], [], approx_tokens("\n".join(header))
    for row in rows:
        t = approx_tokens(row)
        if cur and tokens + t > TARGET_TOKENS:
            out.append("\n".join(header + cur))
            cur, tokens = [], approx_tokens("\n".join(header))
        cur.append(row)
        tokens += t
    if cur:
        out.append("\n".join(header + cur))
    return out


def chunk_blocks(title: str, blocks: list[Block]) -> list[Chunk]:
    chunks: list[Chunk] = []

    def emit(page: int, section: str, kind: str, content: str):
        content = content.strip()
        if not content:
            return
        prefix = " > ".join(x for x in (title, section) if x)
        chunks.append(Chunk(len(chunks), page, section, kind, content, f"{prefix}\n{content}", approx_tokens(content)))

    pending: list[tuple[int, str]] = []
    pending_section = None

    def flush():
        nonlocal pending, pending_section
        if pending:
            for page, text in _pack(pending):
                emit(page, pending_section or "", "text", text)
        pending, pending_section = [], None

    for b in blocks:
        if b.kind == "table":
            flush()
            for part in _split_table(b.text):
                emit(b.page, b.section, "table", part)
            continue
        if pending_section is not None and b.section != pending_section:
            flush()
        pending_section = b.section
        pending.extend((b.page, s) for s in _sentences(b.text))
    flush()
    return chunks
