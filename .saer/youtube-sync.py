#!/usr/bin/env python3
"""Add new YouTube videos to programmes that have "مزامنة مع يوتيوب" switched on.

For every page with template "series", header.youtube_sync: true and a header.youtube_playlist,
this reads the playlist with yt-dlp and creates an episode page for each video that is not on
the site yet (anywhere). A video whose title matches another series' header.youtube_title_match
goes to that series instead. Series with header.sync_last run last (catch-all lists, such as
khutbas by year). Existing episodes are never changed or removed.

Env: GRAV_API_URL (e.g. https://site/api/v1), GRAV_API_KEY. Optional: DRY_RUN=1.
Runs hourly from .github/workflows/youtube-sync.yml.
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from ytclean import EXTRA, dur, khutba_date, split_title  # noqa: E402

API = os.environ["GRAV_API_URL"].rstrip("/")
KEY = os.environ["GRAV_API_KEY"]
DRY = os.environ.get("DRY_RUN") == "1"


def call(method, path, body=None, tries=4):
    for i in range(tries):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "X-API-Key": KEY, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, {"error": e.read()[:300].decode("utf-8", "replace")}
        except (urllib.error.URLError, TimeoutError, ValueError):
            pass
        time.sleep(5 * (i + 1))
    return -1, {"error": "unreachable"}


def all_pages():
    pages, page = [], 1
    while True:
        st, res = call("GET", f"/pages?per_page=100&page={page}")
        if st != 200:
            sys.exit(f"Cannot list pages: {st} {res}")
        pages += res.get("data", [])
        if page >= res.get("meta", {}).get("pagination", {}).get("total_pages", 1):
            return pages
        page += 1


def video_id(value):
    m = re.search(r"(?:youtu\.be/|v=|embed/|shorts/|live/)([A-Za-z0-9_-]{11})", value or "")
    return m.group(1) if m else ""


def playlist_id(value):
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", value or "")
    return m.group(1) if m else (value or "").strip()


def fetch_playlist(pid):
    out = subprocess.run(["yt-dlp", "--flat-playlist", "-J", "--extractor-args", "youtube:lang=ar",
                          f"https://www.youtube.com/playlist?list={pid}"],
                         capture_output=True, text=True, timeout=600)
    if out.returncode != 0:
        print(f"  yt-dlp failed: {out.stderr.strip()[-300:]}")
        return None
    return json.loads(out.stdout)


def truthy(v):
    return v is True or str(v).lower() in ("1", "true", "yes", "on")


def children_of(pages, prog):
    route = prog["raw_route"]
    return [p for p in pages if p.get("parent_route") == prog["route"] or p.get("raw_route", "").rsplit("/", 1)[0] == route]


def main():
    pages = all_pages()
    series = [p for p in pages if p.get("template") == "series"]
    programmes = [p for p in series
                  if truthy((p.get("header") or {}).get("youtube_sync"))
                  and (p.get("header") or {}).get("youtube_playlist")]
    # Series that take videos by title from any synced playlist (e.g. a named khutba series that
    # has no playlist of its own). A matching video goes there instead of the playlist's series.
    routers = []
    for p in series:
        rx = (p.get("header") or {}).get("youtube_title_match")
        if rx:
            try:
                routers.append((re.compile(rx), p))
            except re.error:
                print(f"bad youtube_title_match on {p['raw_route']}: {rx}")
    # Catch-all series (khutbas by year) run last, so a video that also sits in a named series'
    # playlist lands there first.
    programmes.sort(key=lambda p: truthy((p.get("header") or {}).get("sync_last")))
    # A video already anywhere on the site is never added again.
    site_ids = {video_id((p.get("header") or {}).get("youtube", "")) for p in pages} - {""}
    state = {}  # route -> [next_order, next_number]

    def slot(prog):
        r = prog["raw_route"]
        if r not in state:
            kids = children_of(pages, prog)
            orders = [int(m.group(1)) for k in kids if (m := re.match(r"^(\d+)\.", k.get("folder", "")))]
            numbers = [int(n) for k in kids if str(n := (k.get("header") or {}).get("number", "")).isdigit()]
            state[r] = [max(orders, default=0) + 1, max(numbers, default=0) + 1]
        return state[r]

    print(f"{len(programmes)} series with YouTube sync on, {len(routers)} routed by title")
    created = 0
    for prog in programmes:
        h = prog["header"]
        title = h.get("title") or prog.get("title") or prog["raw_route"]
        pid = playlist_id(h["youtube_playlist"])
        print(f"- {title} ({prog['raw_route']}): playlist {pid}")
        data = fetch_playlist(pid)
        if not data:
            continue
        new = []
        for v in data.get("entries") or []:
            if not v or not v.get("id") or v["id"] in site_ids or EXTRA.search(v.get("title") or ""):
                continue
            if (v.get("title") or "").strip() in ("", "[Private video]", "[Deleted video]"):
                continue
            site_ids.add(v["id"])
            target = next((r for rx, r in routers if rx.search(v.get("title") or "")), prog)
            ttitle = (target.get("header") or {}).get("title") or target.get("title") or title
            n, t = split_title(v.get("title") or "", ttitle)
            new.append({"id": v["id"], "n": n, "t": t, "dur": dur(v.get("duration")), "target": target,
                        "date": khutba_date(v.get("title") or "")})
        # YouTube lists may run newest-first; add the oldest first so numbers follow time.
        if all(e["n"] for e in new):
            new.sort(key=lambda e: e["n"])
        elif len([e for e in new if e["date"]]) == len(new) and new:
            new.sort(key=lambda e: e["date"])
        for e in new:
            target = e["target"]
            route = target["raw_route"]
            order, number = slot(target)
            num = e["n"] if (e["n"] and target is prog) else number
            word = {"khutba": "الخطبة", "lesson": "الدرس", "lecture": "المحاضرة"}.get(
                (target.get("header") or {}).get("item_word") or (prog.get("header") or {}).get("item_word"), "الحلقة")
            header = {"title": e["t"] or f"{word} {num}", "number": num,
                      "youtube": f"https://www.youtube.com/watch?v={e['id']}", "synced_from": "youtube"}
            if e["dur"]:
                header["duration"] = e["dur"]
            if e["date"]:
                header["date"] = e["date"] + " 12:00"
            body = {"route": f"{route}/ep-{order:02d}", "title": header["title"], "template": "episode",
                    "header": header, "content": "", "order": order}
            if DRY:
                st = "dry-run"
            else:
                st, res = call("POST", "/pages", body)
                if not (200 <= st < 300):
                    print(f"  ERR {st} {body['route']}: {res}")
                    continue
                created += 1
            print(f"  + {body['route']}  #{num}  {header['title']}  [{st}]")
            state[route] = [order + 1, max(number, num) + 1]
    print(f"done: {created} episode(s) created")


if __name__ == "__main__":
    main()
