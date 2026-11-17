#!/usr/bin/env python3
"""List the khutbas/episodes that still need a Whisper transcript.

A series is picked when header.transcribe is on (switch "فرّغ هذه السلسلة" in the admin), or when
its route is given in SERIES (workflow_dispatch input, comma separated; "all" = every series that
has the switch on). A video is skipped when .saer/transcripts/<video id>.json already exists.

Prints a JSON list for the GitHub Actions matrix: [{"id": ..., "route": ...}, ...] (max 200).
Env: GRAV_API_URL, GRAV_API_KEY, SERIES (optional).
"""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location("ys", os.path.join(HERE, "youtube-sync.py"))
ys = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ys)

wanted = [s.strip().rstrip("/") for s in os.environ.get("SERIES", "").split(",") if s.strip()]
pages = ys.all_pages()
done = {f[:-5] for f in os.listdir(os.path.join(HERE, "transcripts"))} if os.path.isdir(
    os.path.join(HERE, "transcripts")) else set()

out = []
for s in pages:
    if s.get("template") != "series":
        continue
    on = ys.truthy(s["header"].get("transcribe"))
    if wanted and wanted != ["all"]:
        on = s["route"].rstrip("/") in wanted
    if not on:
        continue
    for p in ys.children_of(pages, s):
        vid = ys.video_id(p["header"].get("youtube", ""))
        if vid and vid not in done and p.get("template") != "series":
            out.append({"id": vid, "route": p["route"]})
            done.add(vid)
print(json.dumps(out[:200]))
print(f"{len(out)} to transcribe", file=sys.stderr)
