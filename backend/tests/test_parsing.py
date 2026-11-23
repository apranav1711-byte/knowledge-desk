"""Parsing + chunking across every supported format, using real generated files."""
import io

import pytest

from app.services.chunking import chunk_blocks
from app.services.parsing import ParseError, parse_document


def make_pdf(pages: int = 1) -> bytes:
    import pymupdf

    pdf = pymupdf.open()
    for i in range(pages):
        page = pdf.new_page()
        page.insert_text((72, 40), "ACME Confidential Footer", fontsize=8)  # repeated running header
        page.insert_text((72, 100), "Travel Policy", fontsize=22)
        page.insert_text((72, 140), "Hotel limit for a domestic trip is INR 6,500 per night.", fontsize=11)
        page.insert_text((72, 160), "Airport taxis are reimbursable with receipts.", fontsize=11)
        page.insert_text((72, 800), f"{i + 1}", fontsize=8)
    data = pdf.tobytes()
    pdf.close()
    return data


def test_pdf_text_heading_and_running_header_removed():
    doc = parse_document("travel.pdf", make_pdf(4))
    assert doc.pages == 4
    text = " ".join(b.text for b in doc.blocks)
    assert "INR 6,500" in text
    assert "ACME Confidential Footer" not in text  # repeated header on >=3 pages is stripped
    assert all(b.section == "Travel Policy" for b in doc.blocks)
    assert {b.page for b in doc.blocks} == {1, 2, 3, 4}


def test_scanned_pdf_reports_clear_error():
    import pymupdf

    pdf = pymupdf.open()
    pdf.new_page()
    data = pdf.tobytes()
    with pytest.raises(ParseError, match="No selectable text"):
        parse_document("scan.pdf", data)


def test_docx_headings_and_tables():
    import docx

    d = docx.Document()
    d.add_heading("Leave Policy", level=1)
    d.add_paragraph("Full-time employees receive 24 days of paid annual leave.")
    d.add_heading("Carry forward", level=2)
    t = d.add_table(rows=2, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "Type", "Days"
    t.rows[1].cells[0].text, t.rows[1].cells[1].text = "Annual", "24"
    buf = io.BytesIO()
    d.save(buf)
    doc = parse_document("leave.docx", buf.getvalue())
    kinds = [(b.section, b.kind) for b in doc.blocks]
    assert ("Leave Policy", "text") in kinds
    assert ("Carry forward", "table") in kinds
    assert "| Annual | 24 |" in next(b.text for b in doc.blocks if b.kind == "table")


def test_xlsx_sheets_become_tables():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Bands"
    ws.append(["Grade", "Min", "Max"])
    ws.append(["G7", 1200000, 1800000])
    buf = io.BytesIO()
    wb.save(buf)
    doc = parse_document("bands.xlsx", buf.getvalue())
    assert doc.blocks[0].section == "Bands" and doc.blocks[0].kind == "table"
    assert "| G7 | 1200000 | 1800000 |" in doc.blocks[0].text


def test_pptx_slides_titles_notes():
    from pptx import Presentation

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Expansion Plan"
    slide.placeholders[1].text = "Project Cedar launches in Q3 2027."
    slide.notes_slide.notes_text_frame.text = "Budget owner is planning."
    buf = io.BytesIO()
    prs.save(buf)
    doc = parse_document("plan.pptx", buf.getvalue())
    assert doc.pages == 1
    assert all(b.section == "Expansion Plan" for b in doc.blocks)
    assert any("Project Cedar" in b.text for b in doc.blocks)
    assert any(b.text.startswith("Speaker notes:") for b in doc.blocks)


def test_html_markdown_txt_csv():
    html = b"<html><body><nav>skip</nav><h1>Remote Work</h1><p>Two days per week.</p><table><tr><th>Day</th><th>Hours</th></tr><tr><td>Fri</td><td>10-16</td></tr></table></body></html>"
    d = parse_document("rw.html", html)
    assert d.blocks[0].section == "Remote Work" and "skip" not in " ".join(b.text for b in d.blocks)
    assert any(b.kind == "table" and "| Fri | 10-16 |" in b.text for b in d.blocks)

    md = b"# Policy\nIntro line.\n\n## Limits\n| Item | Limit |\n|---|---|\n| Meal | 1800 |\n"
    d = parse_document("p.md", md)
    assert [b.section for b in d.blocks] == ["Policy", "Limits"]
    assert d.blocks[1].kind == "table"

    d = parse_document("n.txt", b"EQUIPMENT\nEvery employee receives a laptop.\n\nSETUP\nComplete MFA on day one.")
    assert [b.section for b in d.blocks] == ["Equipment", "Setup"]

    d = parse_document("t.csv", b"name;role\nAva;HR\nBen;Manager\n")
    assert "| Ben | Manager |" in d.blocks[0].text


@pytest.mark.parametrize("name,data", [("x.exe", b"zz"), ("e.md", b""), ("bad.docx", b"not a zip"), ("bad.pdf", b"nope")])
def test_rejections(name, data):
    with pytest.raises(ParseError):
        parse_document(name, data)


def test_chunking_overlap_sections_and_table_headers():
    from app.services.parsing import Block

    long_text = " ".join(f"Sentence number {i} describes the policy in some detail." for i in range(120))
    rows = "\n".join(f"| R{i} | {i} |" for i in range(200))
    blocks = [
        Block(1, "Alpha", "text", long_text),
        Block(2, "Beta", "text", "Short beta section."),
        Block(2, "Beta", "table", "| K | V |\n| --- | --- |\n" + rows),
    ]
    chunks = chunk_blocks("Doc", blocks)
    alpha = [c for c in chunks if c.section == "Alpha"]
    assert len(alpha) > 1 and all(c.tokens <= 450 for c in alpha)
    # overlap: consecutive chunks share trailing/leading sentence text
    assert alpha[0].content.split(". ")[-1][:20] in alpha[1].content
    assert not any(c.section == "Alpha" and "Beta" in c.content for c in chunks)  # no cross-section bleed
    tables = [c for c in chunks if c.kind == "table"]
    assert len(tables) > 1 and all(c.content.startswith("| K | V |") for c in tables)
    assert chunks[0].embed_text.startswith("Doc > Alpha\n")
    assert [c.index for c in chunks] == list(range(len(chunks)))
