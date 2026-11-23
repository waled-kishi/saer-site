#!/usr/bin/env python3
"""Layer 2: rewrite a cleaned khutba transcript in written (book) style with Gemini (free tier).

Returns {"summary": str, "text": markdown} or None when GEMINI_API_KEY is missing or every model
fails. Env: GEMINI_API_KEY, GEMINI_MODEL (optional, comma separated, tried in order).
"""
import json, os, sys, time, urllib.error, urllib.request

MODELS = [m.strip() for m in os.environ.get(
    "GEMINI_MODEL",
    # Each model has its own free daily allowance, so when the newest runs out the
    # older ones carry on. The quality guards below reject a weak reply anyway.
    "gemini-flash-latest,gemini-3.8-flash,gemini-2.5-flash,gemini-2.5-flash-lite,gemini-2.0-flash"
).split(",") if m.strip()]

EPISODE_PROMPT = """أنت محرّر عربي متمرّس. أمامك تفريغ حلقة قصيرة من برنامج مرئي للشيخ محمد سائر الشبعان، عنوانها «{title}»، وهي من سلسلة «{series}».
حوّلها إلى فصل من كتيّب: فصحى سليمة رصينة، سهلة، متّصلة الفقرات، يقرأها القارئ بلا أن يشعر أنها كانت كلاماً مسموعاً.

القواعد (إلزامية):
1. لا تُضِف أي فكرة أو معلومة أو شاهد ليس في التفريغ، ولا تحذف فكرة منه. أنت تحرّر الأسلوب فقط.
2. احذف ما هو من طبيعة الإلقاء: السلام والتحية والمقدّمة والختام الثابتين، والنداءات، والتكرار للتوكيد، وعبارات الانتباه، والإحالات إلى الحلقة السابقة أو القادمة.
3. حافظ على عبارات الشيخ المميّزة وأمثلته وقصصه وترتيب أفكاره.
4. الآيات بين ﴿ ﴾ بنصّ المصحف الصحيح، وبعدها [السورة: رقم] إن كنت متأكداً؛ وإلا فاكتبها كما في التفريغ بلا رقم.
5. الأحاديث والأقوال المنقولة بين «» كما وردت، بلا تخريج من عندك.
6. صحّح ما يبدو خطأً واضحاً في التفريغ الآلي بما يقتضيه السياق فقط.
7. إن طال الفصل فقسّمه بعناوين فرعية قصيرة (### عنوان). لا تضع عنواناً رئيسياً. والفصل القصير يُترك بلا عناوين فرعية.
8. الطول قريب من طول التفريغ بعد حذف ما سبق؛ لا تلخّص.

أعد JSON فقط بهذا الشكل:
{{"summary": "جملة واحدة (أقل من 30 كلمة) تلخّص موضوع الحلقة", "text": "النص بصيغة Markdown"}}

التفريغ:
{body}
"""

CHAPTER_PROMPT = """أنت محرّر عربي متمرّس. أمامك تفريغ حلقة مرئية للشيخ محمد سائر الشبعان، عنوانها «{title}»، من سلسلة «{series}». المطلوب تحويلها إلى **فصل** من كتيّب مكتوب، فالكتيّب ليس فيه حلقات بل فصول، وكل فصل متّصل بما قبله.

{previous}
المطلوب: إعادة صياغة كاملة من أسلوب الإلقاء إلى أسلوب القراءة: فصحى نظيفة أنيقة سليمة، فقرات متّصلة، يقرؤها القارئ ولا يحسّ أنها كانت كلاماً مسموعاً.

القواعد (إلزامية):
1. المضمون كما هو: لا تُضِف فكرة أو معلومة أو شاهداً ليس في التفريغ، ولا تحذف فكرة منه، ولا تلخّص. تتغيّر الصياغة فقط، من الإلقاء إلى الكتابة.
2. احتفظ بالمصطلحات العلمية والفكرية التي ذكرها الشيخ كما هي، وبأمثلته وقصصه وتشبيهاته، وبنبرته وطريقته في الشرح وترتيب أفكاره.
3. احذف كل ما هو من طبيعة الإلقاء المسموع: «السلام عليكم» وأي تحية أو ترحيب في البداية، والتوديع في الختام، والنداءات للمشاهدين، وعبارات الانتباه والتوكيد المتكرّر، وكل إشارة إلى «الحلقة» أو «البرنامج» أو «الفيديو» أو «المشاهدين» أو «اشتركوا».
4. الفصل يبدأ مباشرةً بالموضوع. وإن كان قبله فصل فاجعل مطلعه يصل بما سبق بجملة أو جملتين طبيعيتين (من غير أن تعيد ما قيل في الفصل السابق، ومن غير كلمة «حلقة»)، فتتّصل الفصول كأنها كتاب واحد.
5. الآيات بين ﴿ ﴾ بنصّ المصحف الصحيح، وبعدها [السورة: رقم] إن كنت متأكداً؛ وإلا فاكتبها كما في التفريغ بلا رقم. والأحاديث والأقوال المنقولة بين «» كما وردت بلا تخريج من عندك.
6. صحّح ما يبدو خطأً واضحاً في التفريغ الآلي بما يقتضيه السياق فقط. وما لا يُفهم موضعه من التفريغ فلا تخمّنه: اكتب حوله [؟] ليُراجَع.
7. إن طال الفصل فقسّمه بعناوين فرعية قصيرة (### عنوان). لا تضع عنواناً رئيسياً للفصل. والفصل القصير يُترك بلا عناوين فرعية.
8. الطول قريب من طول التفريغ بعد حذف ما سبق.

أعد JSON فقط بهذا الشكل:
{{"summary": "جملة واحدة (أقل من 30 كلمة) تلخّص موضوع الفصل", "text": "النص بصيغة Markdown"}}

التفريغ:
{body}
"""

PREFACE_PROMPT = """أنت محرّر عربي متمرّس. أمامك عناوين فصول كتيّب للشيخ محمد سائر الشبعان بعنوان «{title}»، مع ملخّص كل فصل.
اكتب مقدّمة قصيرة للكتيّب (من 80 إلى 140 كلمة) تعرّف بموضوعه وتربط فصوله برباط واحد، بالفصحى، بلا مبالغة وبلا وعود، وبلا ذكر أنها مأخوذة من فيديو أو برنامج.
لا تُضِف معلومات عن الشيخ أو عن السلسلة ليست في العناوين والملخّصات.

أعد JSON فقط: {{"text": "المقدّمة"}}

الفصول:
{body}
"""

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


# a chapter must not keep the spoken opening; such a reply is rejected and tried again
BANNED = ("السلام عليكم", "سلام عليكم", "أهلاً بكم", "أهلا بكم", "مرحباً بكم", "في هذه الحلقة", "في الحلقة", "الحلقة السابقة", "الحلقة القادمة", "اشتركوا", "المشاهد")

MIN_RATIO = 0.55  # a reply much shorter than the transcript is a summary, not an edit: reject it


def call(model, key, prompt, src_len=0, min_ratio=MIN_RATIO, banned=()):
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
    if not out.get("text") or len(out["text"]) < 120:
        raise ValueError("empty text")
    for b in banned:
        if b in out["text"]:
            raise ValueError(f"spoken phrase left in the text: {b}")
    if src_len and min_ratio and len(out["text"]) < min_ratio * src_len:
        raise ValueError(f"too short ({len(out['text'])} of {src_len} chars)")
    return out


def write(title, paragraphs, kind="khutba", series="", min_ratio=None, previous=""):
    """kind: khutba | episode | preface. Returns {"summary", "text", "model"} or None."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        print("  (no GEMINI_API_KEY: skipping written version)")
        return None
    body = "\n\n".join(paragraphs)
    if kind == "chapter":
        prev = ""
        if previous:
            prev = ("الفصل الذي قبله (للوصل فقط، ولا تنقل منه شيئاً):\n" + previous + "\n")
        prompt = CHAPTER_PROMPT.format(title=title, series=series, previous=prev, body=body)
    elif kind == "episode":
        prompt = EPISODE_PROMPT.format(title=title, series=series, body=body)
    elif kind == "preface":
        prompt = PREFACE_PROMPT.format(title=title, body=body)
    else:
        prompt = PROMPT.format(title=title, body=body)
    for model in MODELS:
        for attempt in range(4):
            try:
                ratio = MIN_RATIO if min_ratio is None else min_ratio
                out = call(model, key, prompt, len(body), ratio, BANNED if kind == "chapter" else ())
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
