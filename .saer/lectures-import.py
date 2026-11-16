#!/usr/bin/env python3
"""One-off import of the Sheikh's khutbas and lessons into /lectures (17 Nov 2026).

Reads the playlist data in .saer/youtube/<id>.json (fetched by the youtube-playlists
workflow) and creates, through the Grav API, only pages that do not exist yet:
  /lectures                     series-list  "الدروس والخطب"
  /lectures/khutab              series (program, item_word khutba)  one series per year + Eid
  /lectures/durus               series (program, item_word lesson)  one series per course of lessons
Each year/lesson series gets youtube_sync on, so later uploads arrive through youtube-sync.py.

Khutba playlists are newest-first on YouTube; they are numbered oldest-first here.
Lesson playlists are ordered by the lesson number found in the title when every video has one.

Env: GRAV_API_URL, GRAV_API_KEY. DRY_RUN=1 prints what would be created.
"""
import json, os, re, sys, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from ytclean import AR_DIG, EXTRA, ORD, TENS, dur, khutba_date, split_title  # noqa: E402

API = os.environ["GRAV_API_URL"].rstrip("/")
KEY = os.environ["GRAV_API_KEY"]
DRY = os.environ.get("DRY_RUN") == "1"
Y = os.path.join(os.path.dirname(__file__), "youtube")

KHUTAB = [  # (slug, title, playlist ids merged in this order)
    ("2026", "خطب الجمعة لعام 2026", ["PLgIzcOU7lAOchGCEb7Oeo2uBB966bSdBm"]),
    ("2025", "خطب الجمعة لعام 2025", ["PLgIzcOU7lAOcxA1nYrySlYve5xOPeRzUD"]),
    ("2024", "خطب الجمعة لعام 2024", ["PLgIzcOU7lAOfm-yfLUr3OuVB15hqVqmvY"]),
    ("2023", "خطب الجمعة لعام 2023", ["PLgIzcOU7lAOdssKwHNJS_SOoLAtJewhNl"]),
    ("2022", "خطب الجمعة لعام 2022", ["PLgIzcOU7lAOdpqXK9AoxQS47bSFah_qVQ"]),
    ("2021", "خطب الجمعة لعام 2021", ["PLgIzcOU7lAOd4zpQzwGtrWzE_XzB5RCh1"]),
    ("2020", "خطب الجمعة لعام 2020", ["PLgIzcOU7lAOcOQbQTMUoKlB6edHgaa-RH"]),
    ("2019", "خطب الجمعة لعام 2019", ["PLgIzcOU7lAOcjURAdHepnj419gG5e8ugS"]),
    ("eid", "خطب العيدين", ["PLgIzcOU7lAOcLY4jKONHtXa-thJPlNF4p", "PLgIzcOU7lAOeDboy5QjMOFpEtvJx3HsEa"]),
]
DURUS = [
    ("ihya-ulum-al-din", "إحياء علوم الدين", "PLgIzcOU7lAOd8EPkemHG6GDbYaJ5MNC6v"),
    ("jaddidu-imanakum", "جددوا إيمانكم (شرح الحكم العطائية)", "PLgIzcOU7lAOeM28hty_CbzPPCkwZSI2zd"),
    ("nur-al-idah", "نور الإيضاح ومراقي الفلاح", "PLgIzcOU7lAOf8TKbTgeY7AQcHjLSAQiWa", ["مراقي الفلاح", "شرح نور الإيضاح في الفقه الحنفي", "نور الايضاح متن مراقي الفلاح"]),
    ("fiqh-al-mutaghayyirat", "فقه المتغيرات", "PLgIzcOU7lAOdwkPckOrSdBrItkhS6zf5t"),
    ("al-sayr-ila-allah", "السير إلى الله بالأسماء الحسنى", "PLgIzcOU7lAOfOxfQaVd-kM8FQatos-4rR"),
    ("al-ulum-al-nabawiyya", "العلوم النبوية", "PLgIzcOU7lAOei8fKrQcnX3swNXTmoFois"),
    ("al-iman-bi-rasulillah", "الإيمان برسول الله ﷺ", "PLgIzcOU7lAOctxezRn0Fjy8XY3RFYslHR", ["الايمان برسول الله صلى الله عليه وسلم"]),
    ("al-sira-wal-ibra", "السيرة النبوية الشريفة والعبرة", "PLdovooy98m04", ["السيرة النبوية الشريفة والعبرة بدقيقة", "السيرة النبوية والعبرة بدقيقة", "السيرة النبوية والعبرة"]),
]


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"X-API-Key": KEY, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read()[:300].decode("utf-8", "replace")}


def existing_routes():
    routes, page = set(), 1
    while True:
        st, res = call("GET", f"/pages?per_page=100&page={page}")
        routes |= {p["raw_route"] for p in res.get("data", [])}
        if page >= res.get("meta", {}).get("pagination", {}).get("total_pages", 1):
            return routes
        page += 1


TENS2 = dict(TENS, **{"العشرين": 20, "الثلاثين": 30, "الأربعين": 40, "الاربعين": 40, "الأربعون": 40,
                        "الخمسين": 50, "الخمسون": 50, "الستين": 60, "الستون": 60, "السبعين": 70, "السبعون": 70,
                        "الثمانين": 80, "الثمانون": 80, "التسعين": 90, "التسعون": 90, "المئة": 100, "المائة": 100})
MARK = r"(?:الدرس|الجزء|الحلقة|المجلس)"


def norm(x):
    x = re.sub(r"[ًٌٍَُِّْـ]", "", x)
    x = x.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ﷺ", "").replace("صلى الله عليه وسلم", "")
    return re.sub(r"\s+", " ", x).strip()


ORDN = {norm(k): v for k, v in ORD.items()}
TENSN = {norm(k): v for k, v in TENS2.items()}
ORDN.update({"الواحد": 1, "واحد": 1})
CARDN = {norm(k): v for k, v in {"واحد": 1, "اثنان": 2, "اثنين": 2, "ثلاثة": 3, "أربعة": 4, "خمسة": 5, "ستة": 6,
                                  "سبعة": 7, "ثمانية": 8, "تسعة": 9, "عشرة": 10, "مئة": 100, "مائة": 100}.items()}


def ordinal_words(words):
    n = 0
    for w in words:
        w = norm(w.strip("()-|:،"))
        y = w[1:] if w.startswith("و") and (w[1:] in TENSN or w[1:] in ORDN or w[1:] in CARDN) else w
        if y in ORDN:
            n += ORDN[y]
        elif y in TENSN:
            n += TENSN[y]
        elif y in ("عشرة", "عشر"):
            n += 10
        elif y in CARDN:
            n += CARDN[y]
        elif w == "و" and n:
            continue
        elif n:
            break
        else:
            return None
    return n or None


def lesson_number(raw):
    t = re.sub(r"#\S+", "", raw.translate(AR_DIG))
    m = re.search(MARK + r"\s*\(?\s*(\d{1,3})", t)
    if m:
        return int(m.group(1))
    m = re.search(MARK + r"\s+(?:رقم\s+)?((?:\S+\s*){1,5})", t)
    if m and (n := ordinal_words(m.group(1).split())):
        return n
    m = re.search(r"\((\d{1,3})\)", t) or re.search(r"بدقيقة\s+(\d{1,3})\b", t) \
        or re.search(r"وسلم\s+(\d{1,3})\b", t) or re.search(r"\b(\d{1,3})\s*$", t.strip())
    return int(m.group(1)) if m else None


def clean_lesson_title(raw, series_title, n, aliases=()):
    t = raw.translate(AR_DIG)
    t = re.sub(r"#\S+", "", t)
    t = re.sub(r"\s+l\s+", " | ", t)
    names = sorted({norm(x) for x in (series_title, series_title.split(" (")[0], *aliases)}, key=len, reverse=True)
    keep = []
    for seg in re.split(r"\s*\|\s*|\s+-\s+", t):
        seg = seg.strip(' "«»')
        for nm in names:
            hit = next((i for i in range(len(seg), 0, -1) if norm(seg[:i]) == nm), None)
            if hit:
                seg = seg[hit:].strip()
                break
        seg = re.sub(r"^(?:بدقيقة\s*)?\(?\s*\d{1,3}\s*\)?\s*", "", seg)
        seg = re.sub(r"^" + MARK + r"\s*\(?\s*\d{1,3}\s*\)?", "", seg).strip()
        words = seg.split()
        if words and re.fullmatch(MARK, words[0]):
            k = 1
            while k < len(words) and ordinal_words(words[1:k + 1]):
                k += 1
            if k > 1:
                words = words[k:]
            seg = " ".join(words)
        seg = re.sub(r"^وال[أا]خير[ةه]?\s*", "", seg).strip(" —-|")
        seg = seg.lstrip(")").rstrip("(").strip()
        if seg.count("(") > seg.count(")"):
            seg += ")"
        if seg and norm(seg) not in names and not re.fullmatch(r"\d{1,3}", seg):
            keep.append(seg)
    return " — ".join(keep)


def videos(pid):
    path = os.path.join(Y, f"{pid}.json")
    if not os.path.exists(path):
        print(f"  !! no data for {pid}")
        return []
    out = []
    for v in json.load(open(path))["videos"]:
        title = (v.get("title") or "").strip()
        if not v.get("id") or title in ("", "[Private video]", "[Deleted video]") or EXTRA.search(title) or title.startswith("مقتطف"):
            continue
        out.append(v)
    return out


def create(route, title, template, header, order, content=""):
    body = {"route": route, "title": title, "template": template, "order": order,
            "header": {"title": title, **header}, "content": content}
    if DRY:
        return True
    st, res = call("POST", "/pages", body)
    if not 200 <= st < 300:
        print(f"  ERR {st} {route}: {res}")
        return False
    return True


def main():
    have = existing_routes()
    made = 0

    def ensure(route, title, template, header, order):
        nonlocal made
        if route in have:
            return
        if create(route, title, template, header, order):
            made += 1
            have.add(route)
            print(f"+ {route}  [{template}]  {title}")

    ensure("/lectures", "الدروس والخطب", "series-list",
           {"menu": "الدروس والخطب", "summary": "خطب الجمعة والعيدين والدروس الشرعية للشيخ محمد سائر الشبعان."}, 5)
    ensure("/lectures/khutab", "خطب الجمعة", "series",
           {"kind": "program", "item_word": "khutba", "series_heading": "حسب السنة",
            "summary": "خطب الجمعة والعيدين مرتّبة حسب السنة."}, 1)
    ensure("/lectures/durus", "الدروس الشرعية", "series",
           {"kind": "program", "item_word": "lesson", "series_heading": "سلاسل الدروس",
            "summary": "دروس في الفقه والتزكية والعقيدة والسيرة."}, 2)

    # Khutbas: one series per year, numbered oldest-first.
    for i, (slug, title, pids) in enumerate(KHUTAB, start=1):
        route = f"/lectures/khutab/{slug}"
        ensure(route, title, "series", {"kind": "series", "item_word": "khutba", "youtube_sync": True,
                                        "youtube_playlist": f"https://www.youtube.com/playlist?list={pids[0]}"}, i)
        seen, items = set(), []
        for pid in pids:
            for v in reversed(videos(pid)):
                if v["id"] not in seen:
                    seen.add(v["id"])
                    items.append(v)
        for n, v in enumerate(items, start=1):
            _, t = split_title(v["title"], title)
            parts = [x for x in t.split(" — ") if x]
            place = [x for x in parts if re.match(r"^(?:الخطبة في\s+)?جامع\s", x)]
            t = " — ".join(x for x in parts if x not in place)
            header = {"number": n, "youtube": f"https://www.youtube.com/watch?v={v['id']}", "synced_from": "youtube"}
            if place:
                header["location"] = re.sub(r"^الخطبة في\s+", "", place[0])
            if d := khutba_date(v["title"]):
                header["date"] = d + " 12:00"
            if du := dur(v.get("duration")):
                header["duration"] = du
            ep = f"{route}/ep-{n:02d}"
            if ep not in have and create(ep, t or f"الخطبة {n}", "episode", header, n):
                made += 1
                have.add(ep)
        print(f"  {route}: {len(items)} khutbas")

    # Lessons: one series per course, ordered by lesson number when every title has one.
    for i, (slug, title, pid, *al) in enumerate(DURUS, start=1):
        aliases = al[0] if al else []
        route = f"/lectures/durus/{slug}"
        ensure(route, title, "series", {"kind": "series", "item_word": "lesson", "youtube_sync": True,
                                        "youtube_playlist": f"https://www.youtube.com/playlist?list={pid}"}, i)
        items = [(lesson_number(v["title"]), v) for v in videos(pid)]
        if items and all(n for n, _ in items) and len({n for n, _ in items}) == len(items):
            items.sort(key=lambda x: x[0])
            ordered = items
        else:
            nums = [n for n, _ in items if n]
            if len(nums) >= 2 and nums[0] > nums[-1]:
                items.reverse()
            ordered = [(None, v) for _, v in items]
        for k, (n, v) in enumerate(ordered, start=1):
            num = n or k
            t = clean_lesson_title(v["title"], title, num, aliases)
            header = {"number": num, "youtube": f"https://www.youtube.com/watch?v={v['id']}", "synced_from": "youtube"}
            if du := dur(v.get("duration")):
                header["duration"] = du
            ep = f"{route}/ep-{k:02d}"
            if DRY and (k <= 3 or k == len(ordered) or os.environ.get('SHOW_ALL')):
                print(f"    {k:3d} #{num:<3} {t or '(الدرس ' + str(num) + ')'}   <- {v['title'][:70]}")
            if ep not in have and create(ep, t or f"الدرس {num}", "episode", header, k):
                made += 1
                have.add(ep)
        print(f"  {route}: {len(ordered)} lessons ({'by number' if ordered and ordered[0][0] else 'playlist order'})")
    print(f"done: {made} page(s) {'would be ' if DRY else ''}created")


if __name__ == "__main__":
    main()
