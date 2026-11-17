#!/usr/bin/env python3
"""Put Whisper transcripts on the site, write the book-style version, build PDFs and the booklet.

For every series with header.transcribe on (or the routes in SERIES), for each episode that has
.saer/transcripts/<video id>.json:
  1. page content  <- cleaned transcript (layer 1), only when the content is empty or was written
                      by this script before (header.transcript: auto) and not edited since.
  2. header.written <- book-style text from Gemini (layer 2), once. Editable in the admin.
  3. khutba-NN.pdf  <- from header.written (or the content), rebuilt whenever that text changes.
Then a booklet page /books/khutab-<series slug> (created unpublished, status "soon") gets the
series booklet PDF and a cover image, and the series is linked to it (header.book).
Walid publishes the booklet page after review; the per-khutba PDFs show only then.

Env: GRAV_API_URL, GRAV_API_KEY, GEMINI_API_KEY (optional), SERIES (optional), FORCE_PDF=1.
"""
import hashlib, importlib.util, json, os, re, subprocess, sys, tempfile, time, urllib.parse, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
spec = importlib.util.spec_from_file_location("ys", os.path.join(HERE, "youtube-sync.py"))
ys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ys)
from khutba_clean import clean  # noqa: E402
from khutba_write import write  # noqa: E402
from khutba_pdf import booklet_pdf, khutba_pdf  # noqa: E402

TDIR = os.path.join(HERE, "transcripts")
FORCE = os.environ.get("FORCE_PDF") == "1"


def q(route):
    return urllib.parse.quote(route.lstrip("/"), safe="/")


def get_page(route):
    st, res = ys.call("GET", f"/pages/{q(route)}?resource=page")
    return res.get("data") if st == 200 else None


def patch(route, header=None, content=None):
    body = {}
    if header is not None:
        body["header"] = header
    if content is not None:
        body["content"] = content
    st, res = ys.call("PATCH", f"/pages/{q(route)}?resource=page", body)
    if st != 200:
        print(f"  PATCH {route}: {st} {res}")
    return st == 200


def upload(route, path, name, mime):
    """Replace a media file on a page (multipart upload)."""
    import urllib.request
    ys.call("DELETE", f"/pages/{q(route)}/media/{urllib.parse.quote(name)}")
    b = uuid.uuid4().hex
    data = (f"--{b}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\n"
            f"Content-Type: {mime}\r\n\r\n").encode() + open(path, "rb").read() + f"\r\n--{b}--\r\n".encode()
    for i in range(3):
        req = urllib.request.Request(f"{ys.API}/pages/{q(route)}/media", data=data, method="POST", headers={
            "X-API-Key": ys.KEY, "Content-Type": f"multipart/form-data; boundary={b}", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.status < 300
        except Exception as e:  # noqa: BLE001
            print(f"  upload {name}: {e}")
            time.sleep(5)
    return False


def h(text):
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def md_paras(paras):
    return "\n\n".join(paras) + "\n"


def series_list(pages):
    wanted = [s.strip().rstrip("/") for s in os.environ.get("SERIES", "").split(",") if s.strip()]
    for s in pages:
        if s.get("template") != "series":
            continue
        on = ys.truthy(s["header"].get("transcribe"))
        if wanted and wanted != ["all"]:
            on = s["route"].rstrip("/") in wanted
        if on:
            yield s


def do_series(s, pages):
    print(f"== {s['route']}")
    eps = [p for p in ys.children_of(pages, s) if p.get("template") != "series"]
    eps.sort(key=lambda p: (p["header"].get("number") or 999, p["route"]))
    items = []
    for ep in eps:
        vid = ys.video_id(ep["header"].get("youtube", ""))
        tfile = os.path.join(TDIR, f"{vid}.json")
        if not vid or not os.path.exists(tfile):
            print(f"  - {ep['route']}: no transcript yet")
            continue
        page = get_page(ep["route"]) or ep
        hd = page.get("header") or {}
        content = (page.get("content") or "").strip()
        segs = json.load(open(tfile, encoding="utf-8"))["segments"]
        paras = clean(segs)
        cleaned = md_paras(paras)
        new_h = {}

        # 1. cleaned transcript as page content (never over a hand-edited text)
        if not content or (hd.get("transcript") == "auto" and hd.get("transcript_hash") == h(content)):
            if content.strip() != cleaned.strip():
                patch(ep["route"], {"transcript": "auto", "transcript_hash": h(cleaned.strip())}, cleaned)
                print(f"  + transcript {ep['route']} ({len(cleaned)} chars)")
            content = cleaned.strip()

        # 2. book-style version (once)
        written = (hd.get("written") or "").strip()
        if not written:
            r = write(ep["title"], paras)
            if r:
                written = r["text"].strip()
                new_h.update({"written": written, "written_by": r["model"]})
                if not hd.get("summary") and r.get("summary"):
                    new_h["summary"] = r["summary"].strip()
                print(f"  + written {ep['route']} ({len(written)} chars, {r['model']})")
                time.sleep(6)

        text = written or content
        item = {"title": ep["title"], "number": hd.get("number"), "date": hd.get("date"),
                "location": hd.get("location"), "video": vid, "text": text, "series": s["title"]}
        items.append(item)

        # 3. per-khutba PDF, rebuilt when the text changes
        if FORCE or hd.get("pdf_hash") != h(text):
            name = f"khutba-{int(hd.get('number') or len(items)):02d}.pdf"
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, name)
                khutba_pdf(item, out)
                if upload(ep["route"], out, name, "application/pdf"):
                    new_h.update({"pdf_hash": h(text), "download_form": "off",
                                  "files": [{"label": "الخطبة مكتوبة (PDF)", "file": name}]})
                    print(f"  + pdf {ep['route']}/{name}")
        if new_h:
            patch(ep["route"], new_h)

    if items:
        do_booklet(s, items)


def do_booklet(s, items):
    slug = s["route"].rstrip("/").rsplit("/", 1)[-1]
    route = f"/books/khutab-{slug}"
    sig = h("".join(i["text"] for i in items) + str(len(items)))
    book = get_page(route)
    if not book:
        body = {"route": route, "title": s["title"], "template": "book", "order": 50, "content": "",
                "header": {"title": s["title"], "subtitle": "سلسلة خطب جمعة", "author": "محمد سائر الشبعان",
                           "status": "soon", "published": False,
                           "summary": s["header"].get("summary") or f"خطب سلسلة «{s['title']}» مكتوبةً في كتيّب واحد."}}
        st, res = ys.call("POST", "/pages", body)
        print(f"  + booklet page {route}: {st}")
        if not (200 <= st < 300):
            print(f"    {res}")
            return
        time.sleep(3)
        get_page(route)
        book = get_page(route) or {"header": {}}
    if not FORCE and (book.get("header") or {}).get("booklet_hash") == sig:
        print("  booklet up to date")
    else:
        with tempfile.TemporaryDirectory() as tmp:
            name = f"{s['title']} - كتيّب.pdf"
            out = os.path.join(tmp, "b.pdf")
            booklet_pdf({"title": s["title"], "summary": s["header"].get("summary") or ""}, items, out)
            subprocess.run(["pdftoppm", "-jpeg", "-r", "110", "-f", "1", "-l", "1", "-singlefile",
                            out, os.path.join(tmp, "cover")], check=True)
            ok = upload(route, out, name, "application/pdf")
            ok = upload(route, os.path.join(tmp, "cover.jpg"), "cover.jpg", "image/jpeg") and ok
            if ok:
                patch(route, {"booklet_hash": sig, "cover": "cover.jpg",
                              "files": [{"label": "تحميل الكتيّب", "file": name}]})
                print(f"  + booklet {route} ({len(items)} khutbas)")
    if not s["header"].get("book"):
        patch(s["route"], {"book": route})


def main():
    pages = ys.all_pages()
    for s in series_list(pages):
        do_series(s, pages)


if __name__ == "__main__":
    main()
