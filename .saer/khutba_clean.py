#!/usr/bin/env python3
"""Layer 1: turn Whisper segments into a clean, readable transcript, without rewording.

- Paragraphs from the speaker's pauses (and a length cap).
- Drops the fixed opening (up to "أما بعد"), the closing ("أقول قولي هذا…" to the end:
  second khutba and du'a), and vocatives ("يا إخواني", "أيها الأحبة"…).
The phrase lists live in khutba-phrases.txt so they can be edited without touching code.

Usage as a module: clean(segments) -> list of paragraphs. CLI: khutba_clean.py <transcript.json>
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load_phrases():
    groups, cur = {}, None
    for line in open(os.path.join(HERE, "khutba-phrases.txt"), encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            cur = groups.setdefault(line[1:-1], [])
        elif cur is not None:
            cur.append(line)
    return groups


AR_NORM = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي"})
DIAC = re.compile(r"[ً-ْٰـ]")


def norm(s):
    return DIAC.sub("", s).translate(AR_NORM)


def loose(phrase):
    """Regex for a phrase that ignores diacritics, hamza forms, taa marbuta and spacing."""
    out = []
    for ch in norm(phrase):
        if ch == " ":
            out.append(r"\s+")
        elif ch == "ا":
            out.append("[اأإآ]")
        elif ch == "ه":
            out.append("[هة]")
        elif ch == "ي":
            out.append("[يى]")
        else:
            out.append(re.escape(ch))
        out.append(r"[ً-ْٰـ]*")
    return "".join(out)


def paragraphs(segments, gap=1.2, soft=420, hard=950):
    paras, cur, last_end = [], "", None
    for s in segments:
        t = s["t"].strip()
        if not t:
            continue
        pause = (s["s"] - last_end) if last_end is not None else 0
        if cur and ((pause >= gap and len(cur) >= soft) or len(cur) >= hard):
            paras.append(cur.strip())
            cur = ""
        cur += (" " if cur else "") + t
        last_end = s["e"]
    if cur.strip():
        paras.append(cur.strip())
    return paras


def tidy(p):
    p = re.sub(r"\s+([،,.؟?!:؛])", r"\1", p)
    p = re.sub(r"([،؛:])(?=\S)", r"\1 ", p)
    p = p.replace(",", "،").replace("?", "؟").replace(";", "؛")
    p = re.sub(r"(،\s*){2,}", "، ", p)
    p = re.sub(r"^\s*[،.]\s*", "", p)
    p = re.sub(r"\s{2,}", " ", p).strip()
    if p and p[-1] not in ".؟!:»﴾﴿)":
        p += "."
    return p


def clean(segments, phrases=None):
    ph = phrases or load_phrases()
    text_paras = paragraphs(segments)
    full = "\n\n".join(text_paras)

    # Opening: cut everything up to the first "أما بعد" if it is near the start.
    for p in ph.get("opening-end", []):
        m = re.search(loose(p), full)
        if m and m.start() < len(full) * 0.25:
            full = full[m.end():].lstrip(" ،,:.\n")
            break
    # Closing: cut from "أقول قولي هذا" (or similar) to the end if it is in the last part.
    for p in ph.get("closing-start", []):
        m = None
        for m in re.finditer(loose(p), full):
            pass
        if m and m.start() > len(full) * 0.55:
            full = full[:m.start()].rstrip(" ،,\n")
            break
    # Fixed formulas anywhere (whole phrase removed).
    for p in sorted(ph.get("remove", []), key=len, reverse=True):
        full = re.sub(loose(p) + r"\s*[،,.:]?\s*", " ", full)
    # Vocatives: "يا إخواني"، "أيها الأحبة الكرام"…
    for p in sorted(ph.get("vocative", []), key=len, reverse=True):
        full = re.sub(r"(^|[\s،,.:؟])(?:ف?يا\s+)?" + loose(p) + r"(\s+(ال)?كرام)?\s*[،,!]?", r"\1", full)
    paras = [tidy(p) for p in full.split("\n\n")]
    return [p for p in paras if len(p) > 1]


if __name__ == "__main__":
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    print("\n\n".join(clean(d["segments"])))
