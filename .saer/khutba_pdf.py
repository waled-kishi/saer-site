#!/usr/bin/env python3
"""PDF for one khutba or episode, and a booklet for a whole series (WeasyPrint, A5, Amiri + Noto Kufi).

khutba_pdf(item, out_path)             item: {title, number, date, location, route, text, kind}
booklet_pdf(series, items, out_path)   series: {title, summary, kind_label}
booklet_pdf(series, [], out, parts=[{title, summary, items}])   a book of several series
"kind" is the word for one piece ("خطبة" by default, "حلقة" for a programme).
text is Markdown (### subheadings, ﴿ ﴾ verses, « » quotes).
"""
import html, os, re
import markdown
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.normpath(os.path.join(HERE, "..", "user", "themes", "saer", "fonts"))
AUTHOR = "الشيخ محمد سائر الشبعان"
SITE = os.environ.get("SITE_URL", "https://saer1.rifd-dt.com").split("://")[-1].rstrip("/")

CSS_TEXT = """
@font-face { font-family: Kufi; font-weight: 400; src: url('file://%(f)s/noto-kufi-arabic-arabic-400-normal.woff2'); }
@font-face { font-family: Kufi; font-weight: 700; src: url('file://%(f)s/noto-kufi-arabic-arabic-700-normal.woff2'); }
@font-face { font-family: Kufi; font-weight: 800; src: url('file://%(f)s/noto-kufi-arabic-arabic-800-normal.woff2'); }
@page {
  size: A5; margin: 18mm 16mm 20mm 16mm;
  @bottom-center { content: counter(page, arabic-indic); font: 10pt Amiri; color: #7a6a8f; }
  @top-center { content: string(running); font: 8pt Kufi; color: #9a8aae; }
}
@page cover { margin: 0; @bottom-center { content: none; } @top-center { content: none; } }
@page :blank { @bottom-center { content: none; } @top-center { content: none; } }
html { direction: rtl; }
body { font-family: Amiri, serif; font-size: 12.5pt; line-height: 1.95; color: #1b1424; text-align: justify; }
h1, h2, h3 { font-family: Kufi, sans-serif; color: #2a1245; line-height: 1.5; text-align: right; }
h1 { font-size: 19pt; font-weight: 800; margin: 0 0 4mm; string-set: running content(); }
h3 { font-size: 11.5pt; font-weight: 700; margin: 7mm 0 2mm; color: #5a2d82; page-break-after: avoid; }
p { margin: 0 0 3.2mm; text-indent: 6mm; orphans: 3; widows: 3; }
h3 + p, .meta + p { text-indent: 0; }
.verse { color: #5a2d82; }
.meta { font-family: Kufi, sans-serif; font-size: 8.5pt; color: #7a6a8f; margin-bottom: 7mm;
        border-bottom: .6pt solid #d6b26e; padding-bottom: 3mm; }
.eyebrow { font-family: Kufi, sans-serif; font-size: 9pt; color: #c99a45; font-weight: 700; margin-bottom: 1mm; }
.end { margin-top: 8mm; padding-top: 3mm; border-top: .6pt solid #d6b26e; font-family: Kufi, sans-serif;
       font-size: 8pt; color: #7a6a8f; text-align: center; text-indent: 0; }
.chapter { page-break-before: always; }
.chapter:first-of-type { page-break-before: auto; }
.cover { page: cover; height: 210mm; background: #150826; color: #fff; text-align: center;
         border-right: 7mm solid #c99a45; padding: 62mm 16mm 0 16mm; box-sizing: border-box; position: relative; }
.cover .k { font-family: Kufi; font-size: 10pt; color: #ebd3a0; margin-bottom: 8mm; text-align: center; }
.cover h1 { color: #fff; font-size: 30pt; text-align: center; string-set: none; margin: 0 0 10mm; line-height: 1.4; }
.cover .by { font-family: Kufi; font-size: 12pt; color: #ebd3a0; text-align: center; }
.cover .foot { position: absolute; bottom: 14mm; left: 0; right: 0; font-family: Kufi; font-size: 8pt; color: #cfc2e2; text-align: center; }
.intro { page-break-before: always; padding-top: 30mm; text-align: center; }
.intro p { text-indent: 0; text-align: center; text-align-last: center; font-size: 14pt; }
.toc { page-break-before: always; }
.toc h2 { font-size: 15pt; string-set: running "الفهرس"; }
.toc ol { list-style: none; padding: 0; margin: 0; font-family: Kufi; font-size: 9.5pt; }
.toc li { padding: 2mm 0; border-bottom: .4pt dotted #cbbfdc; }
.toc li .n { color: #c99a45; font-weight: 700; display: inline-block; width: 8mm; }
.toc li a { color: #1b1424; text-decoration: none; }
.toc li a::after { content: leader('.') target-counter(attr(href), page, arabic-indic); color: #5a2d82; }
.toc li.part { font-weight: 700; color: #2a1245; border-bottom: .6pt solid #d6b26e; margin-top: 4mm; }
section.part { page-break-before: always; padding-top: 55mm; text-align: center; }
section.part h1 { text-align: center; font-size: 24pt; string-set: running content(); }
section.part .eyebrow { text-align: center; }
.part-sum { text-indent: 0; text-align: center; font-size: 12pt; color: #5a2d82; margin-top: 6mm; }
"""


def md(text):
    h = markdown.markdown(text or "", extensions=["extra"])
    h = re.sub(r"(﴿[^﴾]*﴾)", r'<span class="verse">\1</span>', h)
    return h


def meta(it):
    parts = [AUTHOR]
    if it.get("location"):
        parts.append(it["location"])
    if it.get("date"):
        parts.append(str(it["date"])[:10].replace("-", "/"))
    return " · ".join(html.escape(p) for p in parts)


def chapter(it, cls="", anchor=""):
    kind = it.get("kind") or "خطبة"
    eyebrow = f"{kind} {it['number']}" if it.get("number") else ""
    if it.get("series"):
        eyebrow = f"{it['series']} · {eyebrow}" if eyebrow else it["series"]
    end = f"شاهد ال{kind} واستمع إليها: {SITE}{it['route']}" if it.get("route") else ""
    return (f'<section class="{cls}" id="{anchor or ("k" + str(it.get("number", "")))}">'
            f'<div class="eyebrow">{html.escape(eyebrow)}</div><h1>{html.escape(it["title"])}</h1>'
            f'<div class="meta">{meta(it)}</div>{md(it["text"])}'
            f'<p class="end">{html.escape(end)}</p></section>')


def render(body, out):
    fc = FontConfiguration()
    doc = f'<html lang="ar" dir="rtl"><head><meta charset="utf-8"></head><body>{body}</body></html>'
    HTML(string=doc, base_url=HERE).write_pdf(
        out, stylesheets=[CSS(string=CSS_TEXT % {"f": FONTS}, font_config=fc)], font_config=fc)


def khutba_pdf(item, out):
    render(chapter(item), out)


def booklet_pdf(series, items, out, parts=None):
    """One series (items), or a book made of several series (parts)."""
    label = series.get("kind_label") or "سلسلة خطب جمعة"
    cover = (f'<div class="cover"><div class="band"></div><div class="k">{html.escape(label)}</div>'
             f'<h1>{html.escape(series["title"])}</h1><div class="by">{AUTHOR}</div>'
             f'<div class="foot">{SITE}</div></div>')
    intro = ""
    if series.get("summary"):
        intro = f'<section class="intro"><p>{html.escape(series["summary"])}</p></section>'

    groups = parts if parts else [{"title": "", "items": items}]
    toc_rows, chapters, n = [], [], 0
    for gi, g in enumerate(groups, 1):
        if parts:
            toc_rows.append(f'<li class="part">{html.escape(g["title"])}</li>')
            chapters.append(
                f'<section class="part" id="p{gi}"><div class="eyebrow">القسم {gi}</div>'
                f'<h1>{html.escape(g["title"])}</h1>'
                + (f'<p class="part-sum">{html.escape(g["summary"])}</p>' if g.get("summary") else "")
                + '</section>')
        for it in g["items"]:
            n += 1
            anchor = f"c{n}"
            toc_rows.append(f'<li><span class="n">{it.get("number", "")}</span>'
                            f'<a href="#{anchor}">{html.escape(it["title"])}</a></li>')
            chapters.append(chapter(it, "chapter", anchor))
    toc = f'<section class="toc"><h2>الفهرس</h2><ol>{"".join(toc_rows)}</ol></section>'
    render(cover + intro + toc + "".join(chapters), out)
