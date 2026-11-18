#!/usr/bin/env python3
"""Word (.docx) version of a series booklet, right-to-left, for editing in Word.

booklet_docx(series, items, out)   same arguments as khutba_pdf.booklet_pdf.
Fonts: Traditional Arabic for the text, Sakkal Majalla for headings (both ship with Windows).
"""
import os, re
from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor

BODY, HEAD = "Traditional Arabic", "Sakkal Majalla"
PURPLE, GOLD = RGBColor(0x2A, 0x12, 0x45), RGBColor(0xC9, 0x9A, 0x45)
AUTHOR = "الشيخ محمد سائر الشبعان"
SITE = os.environ.get("SITE_URL", "https://saer1.rifd-dt.com").split("://")[-1].rstrip("/")


def rtl_par(p, align=WD_ALIGN_PARAGRAPH.JUSTIFY):
    pPr = p._p.get_or_add_pPr()
    bidi = OxmlElement("w:bidi")
    pPr.insert(0, bidi)
    p.alignment = align
    return p


def run(p, text, font=BODY, size=16, bold=False, color=None):
    r = p.add_run(text)
    rPr = r._r.get_or_add_rPr()
    fonts = rPr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rPr.insert(0, fonts)
    for k in ("w:ascii", "w:hAnsi", "w:cs"):
        fonts.set(qn(k), font)
    rPr.append(OxmlElement("w:rtl"))
    r.font.size = Pt(size)
    szcs = OxmlElement("w:szCs")
    szcs.set(qn("w:val"), str(int(size * 2)))
    rPr.append(szcs)
    if bold:
        r.bold = True
        rPr.append(OxmlElement("w:bCs"))
    if color is not None:
        r.font.color.rgb = color
    return r


def para(doc, text="", **kw):
    align = kw.pop("align", WD_ALIGN_PARAGRAPH.JUSTIFY)
    space = kw.pop("space", 6)
    p = rtl_par(doc.add_paragraph(), align)
    p.paragraph_format.space_after = Pt(space)
    p.paragraph_format.line_spacing = 1.15
    if text:
        add_inline(p, text, **kw)
    return p


def add_inline(p, text, **kw):
    """**bold** spans; everything else plain."""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            run(p, part, bold=(i % 2 == 1) or kw.get("bold", False),
                **{k: v for k, v in kw.items() if k != "bold"})


def page_break(doc):
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def booklet_docx(series, items, out):
    doc = Document()
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(148), Mm(210)
    sec.left_margin = sec.right_margin = Mm(16)
    sec.top_margin, sec.bottom_margin = Mm(18), Mm(20)
    sectPr = sec._sectPr
    sectPr.append(OxmlElement("w:bidi"))

    # Cover
    for _ in range(8):
        para(doc, space=0)
    para(doc, "سلسلة خطب جمعة", font=HEAD, size=14, color=GOLD, align=WD_ALIGN_PARAGRAPH.CENTER)
    para(doc, series["title"], font=HEAD, size=34, bold=True, color=PURPLE, align=WD_ALIGN_PARAGRAPH.CENTER, space=18)
    para(doc, AUTHOR, font=HEAD, size=16, color=GOLD, align=WD_ALIGN_PARAGRAPH.CENTER)
    if series.get("summary"):
        page_break(doc)
        para(doc, series["summary"], size=18, align=WD_ALIGN_PARAGRAPH.CENTER)

    # Contents
    page_break(doc)
    para(doc, "الفهرس", font=HEAD, size=20, bold=True, color=PURPLE, align=WD_ALIGN_PARAGRAPH.RIGHT, space=12)
    for it in items:
        p = para(doc, align=WD_ALIGN_PARAGRAPH.RIGHT, space=4)
        run(p, f"{it.get('number', '')}  ", font=HEAD, size=14, bold=True, color=GOLD)
        run(p, it["title"], font=HEAD, size=14)

    # Khutbas
    for it in items:
        page_break(doc)
        eyebrow = f"{it.get('series', '')} · خطبة {it.get('number', '')}".strip(" ·")
        para(doc, eyebrow, font=HEAD, size=12, color=GOLD, align=WD_ALIGN_PARAGRAPH.RIGHT, space=0)
        para(doc, it["title"], font=HEAD, size=24, bold=True, color=PURPLE, align=WD_ALIGN_PARAGRAPH.RIGHT, space=14)
        for block in re.split(r"\n\s*\n", (it.get("text") or "").strip()):
            block = block.strip()
            if not block:
                continue
            m = re.match(r"^#{1,6}\s+(.*)", block)
            if m:
                para(doc, m.group(1), font=HEAD, size=17, bold=True, color=PURPLE, align=WD_ALIGN_PARAGRAPH.RIGHT, space=4)
            elif block.startswith(">"):
                para(doc, re.sub(r"^>\s?", "", block, flags=re.M), size=16, color=PURPLE)
            else:
                para(doc, " ".join(block.split("\n")), size=16)
        if it.get("route"):
            para(doc, f"شاهد الخطبة واستمع إليها: {SITE}{it['route']}", font=HEAD, size=10,
                 color=RGBColor(0x7A, 0x6A, 0x8F), align=WD_ALIGN_PARAGRAPH.CENTER)
    doc.save(out)
