#!/usr/bin/env python3
"""Turn the episodes of a programme series into a booklet (PDF + Word) and a book page.

For each book listed in BOOKS:
  1. every episode gets a book-style version from Gemini once (header.written), written from
     the page's text; the page itself is not touched.
  2. a booklet PDF and a Word version are built from those chapters, with a cover, a preface
     and a table of contents; a book of several series gets a title page per series.
  3. the files land on a book page under /books, created unpublished and "soon", so Walid
     reviews it before anyone sees it. Turning off "تحديث الكتيّب تلقائياً" (booklet_auto)
     on that page stops this script from overwriting his own edited file.

Env: GRAV_API_URL, GRAV_API_KEY, GEMINI_API_KEY, BOOKS (keys or "all"), FORCE_PDF=1.
"""
import importlib.util, json, os, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ys = _load("ys", "youtube-sync.py")
tp = _load("tp", "transcribe-publish.py")
from khutba_write import write  # noqa: E402
from khutba_pdf import booklet_pdf  # noqa: E402
from khutba_docx import booklet_docx  # noqa: E402

FORCE = os.environ.get("FORCE_PDF") == "1"
# The episodes on the site are already readable text, so the booklet uses them as they are.
# USE_WRITTEN=1 switches to the Gemini book-style rewrite in header.written instead.
USE_WRITTEN = os.environ.get("USE_WRITTEN") == "1"
LABEL = "من برنامج معايير سوريا الجديدة"

BOOKS = [
    {"key": "nabni", "route": "/books/surya-nabni", "order": 60,
     "series": ["/programs/surya-jadida/nabni"]},
    {"key": "nusqit", "route": "/books/surya-nusqit", "order": 61,
     "series": ["/programs/surya-jadida/nusqit"]},
    {"key": "nuwahhid", "route": "/books/surya-nuwahhid", "order": 62,
     "series": ["/programs/surya-jadida/nuwahhid"]},
    {"key": "surya", "route": "/books/maayir-surya-al-jadida", "order": 63,
     "title": "معايير سوريا الجديدة", "parent": "/programs/surya-jadida",
     "series": ["/programs/surya-jadida/nuwahhid",
                "/programs/surya-jadida/nusqit",
                "/programs/surya-jadida/nabni"]},
]


def chapters_of(series_page, pages):
    """The episodes of one series, in order, each with its book-style text."""
    eps = [p for p in ys.children_of(pages, series_page) if p.get("template") != "series"]
    eps.sort(key=lambda p: (p.get("order") or "", p["route"]))
    out = []
    for ep in eps:
        page = tp.get_page(ep["route"]) or ep
        hd = page.get("header") or {}
        content = (page.get("content") or "").strip()
        if not content:
            print(f"  - {ep['route']}: no text yet")
            continue
        text = (hd.get("written") or "").strip() if USE_WRITTEN else content
        out.append({"title": ep["title"], "date": hd.get("date"), "route": ep["route"],
                    "text": text or content, "kind": "حلقة", "series": series_page["title"],
                    "ready": bool(text or content)})
    return out


def preface(book, parts, pages):
    """The booklet's opening page: the series summary, or one Gemini writes once."""
    if len(parts) == 1:
        return parts[0].get("summary") or ""
    parent_route = book.get("parent")
    parent = tp.get_page(parent_route) if parent_route else None
    saved = ((parent or {}).get("header") or {}).get("booklet_intro")
    if saved:
        return saved.strip()
    body = "\n".join(
        f"- {p['title']}: " + "؛ ".join(c["title"] for c in p["items"]) for p in parts)
    if not os.environ.get("GEMINI_API_KEY"):
        return ((parent or {}).get("header") or {}).get("summary") or ""
    r = write(book.get("title") or "", [body], kind="preface", min_ratio=0)
    text = (r or {}).get("text", "").strip()
    if text and parent:
        tp.patch(parent_route, {"booklet_intro": text})
    return text


def ensure_book_page(book, title, subtitle, summary):
    page = tp.get_page(book["route"])
    if page:
        return page
    body = {"route": book["route"], "title": title, "template": "book", "order": book["order"],
            "content": "",
            "header": {"title": title, "subtitle": subtitle, "author": "محمد سائر الشبعان",
                       "status": "soon", "published": False, "summary": summary}}
    st, res = ys.call("POST", "/pages", body)
    print(f"  + book page {book['route']}: {st}")
    if not (200 <= st < 300):
        print(f"    {res}")
        return None
    time.sleep(3)
    tp.get_page(book["route"])
    return tp.get_page(book["route"]) or {"header": {}}


def build(book, pages):
    parts = []
    for route in book["series"]:
        s = next((p for p in pages if p["route"].rstrip("/") == route.rstrip("/")), None)
        if not s:
            print(f"  ! series not found: {route}")
            continue
        items = chapters_of(s, pages)
        if items:
            parts.append({"title": s["title"], "summary": (s.get("header") or {}).get("summary") or "",
                          "items": items})
    if not parts:
        print("  nothing to build")
        return
    missing = [c["title"] for p in parts for c in p["items"] if not c.get("ready")]
    if missing and os.environ.get("ALLOW_PARTIAL") != "1":
        print(f"  waiting for the written version of {len(missing)} chapter(s); "
              f"the booklet is not built from raw transcripts. Run again later.")
        return

    title = book.get("title") or parts[0]["title"]
    intro = preface(book, parts, pages)
    chapters = [c for p in parts for c in p["items"]]
    for n, c in enumerate(chapters, 1):
        c["number"] = n
    subtitle = LABEL if len(parts) == 1 else "ثلاث سلاسل في كتاب واحد"
    summary = intro or f"حلقات «{title}» مكتوبةً في كتيّب واحد."

    page = ensure_book_page(book, title, subtitle, summary[:300])
    if page is None:
        return
    bh = page.get("header") or {}
    sig = tp.h("".join(c["text"] for c in chapters) + intro + str(len(chapters)) + "prog-2")
    if bh.get("booklet_auto") is False:
        print("  booklet: automatic updates are off (booklet_auto)")
        return
    if not FORCE and bh.get("booklet_hash") == sig and bh.get("booklet_docx"):
        print("  booklet up to date")
        return

    meta = {"title": title, "summary": intro, "kind_label": LABEL if len(parts) == 1 else "برنامج"}
    with tempfile.TemporaryDirectory() as tmp:
        pdf_name = f"{title} - كتيّب.pdf"
        docx_name = f"{title} - كتيّب (Word).docx"
        pdf = os.path.join(tmp, "b.pdf")
        docx = os.path.join(tmp, "b.docx")
        many = parts if len(parts) > 1 else None
        booklet_pdf(meta, chapters, pdf, parts=many)
        booklet_docx(meta, chapters, docx, parts=many)
        subprocess.run(["pdftoppm", "-jpeg", "-r", "110", "-f", "1", "-l", "1", "-singlefile",
                        pdf, os.path.join(tmp, "cover")], check=True)
        ok = tp.upload(book["route"], pdf, pdf_name, "application/pdf")
        ok = tp.upload(book["route"], os.path.join(tmp, "cover.jpg"), "cover.jpg", "image/jpeg") and ok
        ok = tp.upload(book["route"], docx, docx_name,
                       "application/vnd.openxmlformats-officedocument.wordprocessingml.document") and ok
        if ok:
            tp.patch(book["route"], {"booklet_hash": sig, "cover": "cover.jpg",
                                     "booklet_docx": docx_name,
                                     "files": [{"label": "تحميل الكتيّب", "file": pdf_name}]})
            print(f"  + booklet {book['route']} ({len(chapters)} chapters)")

    # link each series to the book, when it has none yet
    for p in book["series"]:
        s = next((x for x in pages if x["route"].rstrip("/") == p.rstrip("/")), None)
        if s and not (s.get("header") or {}).get("book") and len(parts) == 1:
            tp.patch(s["route"], {"book": book["route"]})


def main():
    wanted = [w.strip() for w in os.environ.get("BOOKS", "all").split(",") if w.strip()]
    pages = ys.all_pages()
    for book in BOOKS:
        if wanted and wanted != ["all"] and book["key"] not in wanted:
            continue
        print(f"== {book['key']} -> {book['route']}")
        build(book, pages)


if __name__ == "__main__":
    main()
