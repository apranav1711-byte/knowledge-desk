"""Structure-aware document parsing.

Every supported format is converted into an ordered list of `Block`s that keep:
  * page (PDF page / slide number / sheet index; 1 for formats without pages),
  * section (nearest preceding heading, slide title, or sheet name),
  * kind ('text' or 'table'; tables become Markdown so rows stay together).

Supported: PDF (text layer, tables, heading detection, repeated header/footer removal, optional OCR when Tesseract
is installed), DOCX, XLSX, CSV, PPTX (incl. speaker notes), HTML, Markdown, plain text.
"""
from __future__ import annotations

import csv
import io
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings


class ParseError(ValueError):
    """Raised with a user-presentable message when a document cannot be parsed."""


@dataclass
class Block:
    page: int
    section: str
    kind: str  # 'text' | 'table'
    text: str


@dataclass
class ParsedDocument:
    title: str
    file_type: str
    pages: int
    blocks: list[Block]
    warnings: list[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.blocks)


SUPPORTED = {".pdf", ".docx", ".xlsx", ".csv", ".pptx", ".html", ".htm", ".md", ".markdown", ".txt"}


# ----------------------------------------------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------------------------------------------
def _clean(text: str) -> str:
    text = text.replace("\x00", "").replace("­", "")
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r"\s+", " ", str(value)).strip().replace("|", "\\|")


def rows_to_markdown(rows: list[list]) -> str:
    """First non-empty row is treated as the header."""
    rows = [[_cell(c) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def _title_from(filename: str) -> str:
    stem = Path(filename.replace("\\", "/")).stem
    return re.sub(r"[_\-]+", " ", stem).strip() or "Untitled"


# ----------------------------------------------------------------------------------------------------------------
# PDF
# ----------------------------------------------------------------------------------------------------------------
def _parse_pdf(data: bytes) -> tuple[list[Block], int, list[str]]:
    import pymupdf

    warnings: list[str] = []
    try:
        pdf = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ParseError("The PDF could not be read. It may be corrupted.")
    with pdf:
        if pdf.needs_pass:
            raise ParseError("The PDF is password-protected. Remove the password and upload again.")
        n_pages = len(pdf)
        if n_pages == 0:
            raise ParseError("The PDF has no pages.")

        # Body font size = most common size weighted by characters; headings are noticeably larger.
        sizes: Counter = Counter()
        for page in pdf:
            for b in page.get_text("dict").get("blocks", []):
                for line in b.get("lines", []):
                    for s in line.get("spans", []):
                        sizes[round(s["size"], 1)] += len(s["text"].strip())
        body_size = sizes.most_common(1)[0][0] if sizes else 11.0

        per_page: list[list[tuple[float, str, str, bool]]] = []  # (y0, kind, text, is_heading)
        margin_texts: Counter = Counter()
        ocr_pages = 0
        for page in pdf:
            height = page.rect.height
            items: list[tuple[float, str, str, bool]] = []
            table_boxes = []
            try:
                for t in page.find_tables().tables:
                    md = rows_to_markdown(t.extract())
                    if md:
                        table_boxes.append(pymupdf.Rect(t.bbox))
                        items.append((t.bbox[1], "table", md, False))
            except Exception:
                pass  # table detection is best-effort; text still extracted below

            text_items = 0
            for b in page.get_text("dict").get("blocks", []):
                if b.get("type") != 0:
                    continue
                rect = pymupdf.Rect(b["bbox"])
                if any(rect.intersects(tb) and (rect & tb).get_area() > 0.5 * rect.get_area() for tb in table_boxes):
                    continue
                lines, max_size = [], 0.0
                for line in b.get("lines", []):
                    txt = "".join(s["text"] for s in line.get("spans", [])).strip()
                    if txt:
                        lines.append(txt)
                        max_size = max([max_size] + [s["size"] for s in line["spans"] if s["text"].strip()])
                if not lines:
                    continue
                text = re.sub(r"-\n", "", "\n".join(lines))
                text = " ".join(text.split("\n")) if len("\n".join(lines)) < 400 else "\n".join(lines)
                is_heading = max_size >= body_size * 1.18 and len(text) <= 160
                y0 = b["bbox"][1]
                in_margin = y0 < height * 0.07 or b["bbox"][3] > height * 0.93
                if in_margin:
                    margin_texts[re.sub(r"\d+", "#", text.lower())] += 1
                items.append((y0, "text", text, is_heading))
                text_items += 1

            if text_items == 0 and not any(i[1] == "table" for i in items):
                # No text layer: try OCR (needs Tesseract on the host); otherwise reported below.
                try:
                    tp = page.get_textpage_ocr(dpi=200, full=True)
                    ocr_text = page.get_text("text", textpage=tp).strip()
                    if ocr_text:
                        items.append((0.0, "text", ocr_text, False))
                        ocr_pages += 1
                except Exception:
                    pass
            per_page.append(sorted(items, key=lambda i: i[0]))

        repeated = {k for k, c in margin_texts.items() if n_pages >= 3 and c >= max(3, n_pages // 2)}
        blocks: list[Block] = []
        section = ""
        for pno, items in enumerate(per_page, start=1):
            for y0, kind, text, is_heading in items:
                norm = re.sub(r"\d+", "#", text.lower())
                if kind == "text" and (norm in repeated or re.fullmatch(r"(page\s*)?#(\s*(of|/)\s*#)?", norm)):
                    continue  # running header/footer or bare page number
                if kind == "text" and is_heading:
                    section = _clean(text)
                    continue
                blocks.append(Block(pno, section, kind, _clean(text)))
        if ocr_pages:
            warnings.append(f"OCR was used on {ocr_pages} page(s); verify extracted text.")
        if not any(b.text for b in blocks):
            raise ParseError(
                "No selectable text found. This looks like a scanned PDF; install Tesseract OCR on the server or "
                "upload a text-based PDF."
            )
        return blocks, n_pages, warnings


# ----------------------------------------------------------------------------------------------------------------
# DOCX
# ----------------------------------------------------------------------------------------------------------------
def _parse_docx(data: bytes) -> tuple[list[Block], int, list[str]]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception:
        raise ParseError("The Word document could not be read. Use a valid .docx file.")
    blocks: list[Block] = []
    section = ""
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = _clean(para.text)
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            if style.startswith("heading") or style == "title":
                section = text
            else:
                blocks.append(Block(1, section, "text", text))
        elif tag == "tbl":
            table = Table(child, document)
            rows = []
            for row in table.rows:
                seen, cells = set(), []
                for cell in row.cells:  # merged cells repeat; keep one copy
                    if id(cell._tc) in seen:
                        continue
                    seen.add(id(cell._tc))
                    cells.append(cell.text)
                rows.append(cells)
            md = rows_to_markdown(rows)
            if md:
                blocks.append(Block(1, section, "table", md))
    return blocks, 1, []


# ----------------------------------------------------------------------------------------------------------------
# XLSX / CSV
# ----------------------------------------------------------------------------------------------------------------
def _parse_xlsx(data: bytes) -> tuple[list[Block], int, list[str]]:
    import openpyxl

    try:
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise ParseError("The Excel file could not be read. Use a valid .xlsx file.")
    blocks: list[Block] = []
    total = 0
    for idx, ws in enumerate(wb.worksheets, start=1):
        rows = []
        for row in ws.iter_rows(values_only=True):
            if any(c is not None and str(c).strip() for c in row):
                rows.append(list(row))
                total += sum(len(str(c)) for c in row if c is not None)
            if total > settings.MAX_TEXT_CHARS:
                raise ParseError("The spreadsheet is too large to index (text limit exceeded).")
        md = rows_to_markdown(rows)
        if md:
            blocks.append(Block(idx, ws.title, "table", md))
    wb.close()
    return blocks, max(len(wb.worksheets), 1), []


def _parse_csv(data: bytes) -> tuple[list[Block], int, list[str]]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    md = rows_to_markdown(rows)
    return ([Block(1, "Data", "table", md)] if md else []), 1, []


# ----------------------------------------------------------------------------------------------------------------
# PPTX
# ----------------------------------------------------------------------------------------------------------------
def _parse_pptx(data: bytes) -> tuple[list[Block], int, list[str]]:
    from pptx import Presentation

    try:
        prs = Presentation(io.BytesIO(data))
    except Exception:
        raise ParseError("The PowerPoint file could not be read. Use a valid .pptx file.")
    blocks: list[Block] = []
    for idx, slide in enumerate(prs.slides, start=1):
        title = ""
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = _clean(slide.shapes.title.text_frame.text)
        section = title or f"Slide {idx}"
        for shape in slide.shapes:
            if shape.has_text_frame and shape is not slide.shapes.title:
                text = _clean("\n".join(p.text for p in shape.text_frame.paragraphs))
                if text:
                    blocks.append(Block(idx, section, "text", text))
            if getattr(shape, "has_table", False) and shape.has_table:
                md = rows_to_markdown([[c.text for c in r.cells] for r in shape.table.rows])
                if md:
                    blocks.append(Block(idx, section, "table", md))
        if slide.has_notes_slide:
            notes = _clean(slide.notes_slide.notes_text_frame.text)
            if notes:
                blocks.append(Block(idx, section, "text", "Speaker notes: " + notes))
    return blocks, len(prs.slides), []


# ----------------------------------------------------------------------------------------------------------------
# HTML / Markdown / text
# ----------------------------------------------------------------------------------------------------------------
def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return data.decode(enc)
        except (UnicodeError, ValueError):
            continue
    return data.decode("utf-8", errors="replace")


def _parse_html(data: bytes) -> tuple[list[Block], int, list[str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(_decode(data), "lxml")
    for t in soup(["script", "style", "nav", "footer", "noscript", "svg", "form"]):
        t.decompose()
    blocks: list[Block] = []
    section = ""
    root = soup.body or soup
    for el in root.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "blockquote", "table"]):
        if el.name != "table" and el.find_parent("table"):
            continue
        if el.name == "table":
            rows = [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])] for tr in el.find_all("tr")]
            md = rows_to_markdown(rows)
            if md:
                blocks.append(Block(1, section, "table", md))
        elif el.name.startswith("h"):
            section = _clean(el.get_text(" ", strip=True))
        else:
            text = _clean(el.get_text(" ", strip=True))
            if text:
                blocks.append(Block(1, section, "text", text))
    if not blocks and soup.title and soup.title.string:
        blocks.append(Block(1, "", "text", _clean(soup.title.string)))
    return blocks, 1, []


def _parse_markdown(data: bytes) -> tuple[list[Block], int, list[str]]:
    blocks: list[Block] = []
    section, para, table = "", [], []

    def flush_para():
        if para:
            blocks.append(Block(1, section, "text", _clean(" ".join(para) if len(para) < 3 else "\n".join(para))))
            para.clear()

    def flush_table():
        if table:
            rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in table]
            rows = [r for r in rows if not all(re.fullmatch(r":?-{2,}:?", c) for c in r if c)]
            md = rows_to_markdown(rows)
            if md:
                blocks.append(Block(1, section, "table", md))
            table.clear()

    in_code = False
    for line in _decode(data).splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        m = re.match(r"^(#{1,6})\s+(.*?)\s*#*$", line) if not in_code else None
        if m:
            flush_para(); flush_table()
            section = _clean(m.group(2))
        elif line.strip().startswith("|") and not in_code:
            flush_para()
            table.append(line)
        elif not line.strip():
            flush_para(); flush_table()
        else:
            flush_table()
            para.append(line.strip())
    flush_para(); flush_table()
    return blocks, 1, []


def _parse_text(data: bytes) -> tuple[list[Block], int, list[str]]:
    blocks: list[Block] = []
    section = ""
    for chunk in re.split(r"\n\s*\n", _decode(data)):
        text = _clean(chunk)
        if not text:
            continue
        first, _, rest = text.partition("\n")
        if len(first) <= 80 and first.upper() == first and re.search(r"[A-Z]", first) and not first.endswith("."):
            section = first.title()
            text = _clean(rest)
        if text:
            blocks.append(Block(1, section, "text", text))
    return blocks, 1, []


_PARSERS = {
    ".pdf": _parse_pdf, ".docx": _parse_docx, ".xlsx": _parse_xlsx, ".csv": _parse_csv, ".pptx": _parse_pptx,
    ".html": _parse_html, ".htm": _parse_html, ".md": _parse_markdown, ".markdown": _parse_markdown,
    ".txt": _parse_text,
}


def parse_document(filename: str, data: bytes) -> ParsedDocument:
    if not data:
        raise ParseError("The file is empty.")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise ParseError(f"The file exceeds the {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    suffix = Path(filename.replace("\\", "/")).suffix.lower()
    if suffix not in SUPPORTED:
        raise ParseError("Unsupported file type. Supported: PDF, DOCX, XLSX, CSV, PPTX, HTML, Markdown, TXT.")
    blocks, pages, warnings = _PARSERS[suffix](data)
    blocks = [b for b in blocks if b.text.strip()]
    if not blocks:
        raise ParseError("No readable text was found in the document.")
    doc = ParsedDocument(_title_from(filename), suffix.lstrip("."), pages, blocks, warnings)
    if doc.char_count > settings.MAX_TEXT_CHARS:
        raise ParseError("The document contains too much text to index in one file.")
    return doc
