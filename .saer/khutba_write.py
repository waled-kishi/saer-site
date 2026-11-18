#!/usr/bin/env python3
"""Layer 2: rewrite a cleaned khutba transcript in written (book) style with Gemini (free tier).

Returns {"summary": str, "text": markdown} or None when GEMINI_API_KEY is missing or every model
fails. Env: GEMINI_API_KEY, GEMINI_MODEL (optional, comma separated, tried in order).
"""
import json, os, sys, time, urllib.error, urllib.request

MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL", "gemini-flash-latest,gemini-3.8-flash").split(",") if m.strip()]

PROMPT = """أنت محرّر عربي متمرّس. أمامك تفريغ آلي لخطبة جمعة ألقاها الشيخ محمد سائر الشبعان بعنوان «{title}».
حوّلها إلى نصّ مكتوب بأسلوب كتاب: فصحى سليمة رصينة، سهلة، متّصلة الفقرات.

القواعد (إلزامية):
1. لا تُضِف أي فكرة أو معلومة أو شاهد ليس في التفريغ، ولا تحذف فكرة منه. أنت تحرّر الأسلوب فقط.
2. احذف ما هو من طبيعة الإلقاء: النداءات (يا إخوة، أيها الأحبة…)، التكرار للتوكيد، عبارات الانتباه (انتبهوا، ركّزوا معي)، الاستطرادات الصوتية، المقدّمة والختام الثابتين والدعاء.
3. حافظ على عبارات الشيخ المميّزة وأمثلته وقصصه وترتيب أفكاره.
4. الآيات: اكتبها بين قوسين مزخرفين ﴿ ﴾ بنصّ المصحف الصحيح، وبعدها اسم السورة ورقم الآية بين معقوفين مثل [الرعد: 11]، إن كنت متأكداً منها. إن لم تتأكد فاكتبها كما في التفريغ بين ﴿ ﴾ بلا رقم.
5. الأحاديث والأقوال المنقولة بين «»، كما وردت، بلا تخريج من عندك.
6. صحّح ما يبدو خطأً واضحاً في التفريغ الآلي (كلمة مسموعة خطأً) بما يقتضيه السياق فقط.
7. قسّم النص بعناوين فرعية قصيرة (### عنوان) كل بضع فقرات بحسب انتقال الأفكار. لا تضع عنواناً رئيسياً.
8. الطول قريب من طول التفريغ بعد حذف ما سبق؛ لا تلخّص.

أعد JSON فقط بهذا الشكل:
{{"summary": "جملة واحدة (أقل من 30 كلمة) تلخّص موضوع الخطبة", "text": "النص بصيغة Markdown"}}

التفريغ:
{body}
"""


MIN_RATIO = 0.55  # a reply much shorter than the transcript is a summary, not an edit: reject it


def call(model, key, prompt, src_len=0):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json",
                                 "maxOutputTokens": 32768}}
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    with urllib.request.urlopen(req, timeout=300) as r:
        d = json.loads(r.read())
    txt = "".join(p.get("text", "") for p in d["candidates"][0]["content"]["parts"])
    out = json.loads(txt)
    if not out.get("text") or len(out["text"]) < 200:
        raise ValueError("empty text")
    if src_len and len(out["text"]) < MIN_RATIO * src_len:
        raise ValueError(f"too short ({len(out['text'])} of {src_len} chars)")
    return out


def write(title, paragraphs):
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("  (no GEMINI_API_KEY: skipping written version)")
        return None
    body = "\n\n".join(paragraphs)
    prompt = PROMPT.format(title=title, body=body)
    for model in MODELS:
        for attempt in range(4):
            try:
                out = call(model, key, prompt, len(body))
                out["model"] = model
                return out
            except urllib.error.HTTPError as e:
                msg = e.read()[:200].decode("utf-8", "replace")
                print(f"  {model}: HTTP {e.code} {msg}")
                if e.code == 429 and "quota" in msg.lower():
                    break  # daily free quota used up: the daily run tries again tomorrow
                if e.code in (429, 500, 503):  # busy: wait and try the same model again
                    time.sleep(40 * (attempt + 1))
                    continue
                break
            except Exception as e:  # noqa: BLE001
                print(f"  {model}: {e}")
                time.sleep(5)
    return None


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from khutba_clean import clean
    d = json.load(open(sys.argv[1], encoding="utf-8"))
    r = write(sys.argv[2] if len(sys.argv) > 2 else "", clean(d["segments"]))
    print(json.dumps(r, ensure_ascii=False, indent=1) if r else "failed")
