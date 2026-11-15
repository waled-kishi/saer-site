#!/usr/bin/env python3
"""Add new YouTube videos to programmes that have "مزامنة مع يوتيوب" switched on.

For every page with template "series", header.youtube_sync: true and a header.youtube_playlist,
this reads the playlist with yt-dlp and creates an episode page for each video that the
programme does not have yet. Existing episodes are never changed or removed.

Env: GRAV_API_URL (e.g. https://site/api/v1), GRAV_API_KEY. Optional: DRY_RUN=1.
Runs hourly from .github/workflows/youtube-sync.yml.
"""
import json, os, re, subprocess, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(__file__))
from ytclean import EXTRA, dur, split_title  # noqa: E402

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


def main():
    pages = all_pages()
    programmes = [p for p in pages if p.get("template") == "series"
                  and truthy((p.get("header") or {}).get("youtube_sync"))
                  and (p.get("header") or {}).get("youtube_playlist")]
    print(f"{len(programmes)} programme(s) with YouTube sync on")
    created = 0
    for prog in programmes:
        route, h = prog["raw_route"], prog["header"]
        title = h.get("title") or prog.get("title") or route
        pid = playlist_id(h["youtube_playlist"])
        kids = [p for p in pages if p.get("parent_route") == prog["route"] or p.get("raw_route", "").rsplit("/", 1)[0] == route]
        have = {video_id((k.get("header") or {}).get("youtube", "")) for k in kids} - {""}
        orders = [int(m.group(1)) for k in kids if (m := re.match(r"^(\d+)\.", k.get("folder", "")))]
        numbers = [int(n) for k in kids if str(n := (k.get("header") or {}).get("number", "")).isdigit()]
        next_order = max(orders, default=0) + 1
        next_number = max(numbers, default=0) + 1
        print(f"- {title} ({route}): {len(kids)} existing, playlist {pid}")
        data = fetch_playlist(pid)
        if not data:
            continue
        new = []
        for v in data.get("entries") or []:
            if not v or not v.get("id") or v["id"] in have or EXTRA.search(v.get("title") or ""):
                continue
            if (v.get("title") or "").strip() in ("[Private video]", "[Deleted video]"):
                continue
            have.add(v["id"])
            n, t = split_title(v.get("title") or "", title)
            new.append({"id": v["id"], "n": n, "t": t, "dur": dur(v.get("duration"))})
        if all(e["n"] for e in new):
            new.sort(key=lambda e: e["n"])
        for e in new:
            num = e["n"] or next_number
            next_number = max(next_number, num + 1)
            header = {"title": e["t"] or f"الحلقة {num}", "number": num,
                      "youtube": f"https://www.youtube.com/watch?v={e['id']}", "synced_from": "youtube"}
            if e["dur"]:
                header["duration"] = e["dur"]
            body = {"route": f"{route}/ep-{next_order:02d}", "title": header["title"], "template": "episode",
                    "header": header, "content": "", "order": next_order}
            if DRY:
                st = "dry-run"
            else:
                st, res = call("POST", "/pages", body)
                if not (200 <= st < 300):
                    print(f"  ERR {st} {body['route']}: {res}")
                    continue
                created += 1
            print(f"  + {body['route']}  #{num}  {header['title']}  [{st}]")
            next_order += 1
    print(f"done: {created} episode(s) created")


if __name__ == "__main__":
    main()
