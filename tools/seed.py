#!/usr/bin/env python3
"""Seed (create or update) pages on a Grav 2 site from content-seed/ through the Grav API.

Usage: GRAV_API_URL=https://site/api/v1 GRAV_API_KEY=... python3 tools/seed.py [content-seed]

Folder names like "02.programs" become route "/programs" with order 2.
The page template is the .md file name (series.md -> template "series").
Existing pages are updated (header replaced, content set); missing ones are created.
"""
import json, os, re, sys, urllib.request, urllib.error

API = os.environ["GRAV_API_URL"].rstrip("/")
KEY = os.environ["GRAV_API_KEY"]
ROOT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "..", "content-seed")

try:
    import yaml  # PyYAML
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method,
                                 headers={"X-API-Key": KEY, "Content-Type": "application/json",
                                          "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def parse(md_path):
    text = open(md_path, encoding="utf-8").read()
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    header = yaml.safe_load(m.group(1)) or {} if m else {}
    content = m.group(2) if m else text
    return header, content.strip() + ("\n" if content.strip() else "")


def walk(folder, parent_route=""):
    for name in sorted(os.listdir(folder)):
        full = os.path.join(folder, name)
        if not os.path.isdir(full):
            continue
        m = re.match(r"^(\d+)\.(.+)$", name)
        order, slug = (int(m.group(1)), m.group(2)) if m else (None, name)
        route = "/" + slug if not parent_route else parent_route + "/" + slug
        mds = [f for f in os.listdir(full) if f.endswith(".md")]
        if mds:
            template = mds[0][:-3]
            header, content = parse(os.path.join(full, mds[0]))
            yield route, order, template, header, content
        yield from walk(full, route)


def main():
    existing = {}
    st, res = call("GET", "/pages?limit=500")
    for p in res.get("data", []):
        existing[p["raw_route"]] = p
    for route, order, template, header, content in walk(ROOT):
        title = header.get("title", route.rsplit("/", 1)[-1])
        api_route = "/home" if route == "/home" else route
        if api_route in existing:
            body = {"title": title, "template": template, "header": header,
                    "header_mode": "replace", "content": content}
            st, res = call("PATCH", "/pages" + api_route, body)
            action = "update"
        else:
            body = {"route": api_route, "title": title, "template": template,
                    "header": header, "content": content}
            if order is not None:
                body["order"] = order
            st, res = call("POST", "/pages", body)
            action = "create"
        ok = 200 <= st < 300
        print(f"{'ok ' if ok else 'ERR'} {action:6} {api_route} [{template}] {'' if ok else json.dumps(res, ensure_ascii=False)[:300]}")


if __name__ == "__main__":
    main()
