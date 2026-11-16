"""Title cleaning for YouTube playlist entries (shared by youtube-to-seed.py and youtube-sync.py)."""
import re
AR_DIG=str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')
EXTRA=re.compile(r'مقتطف|تشويق|برومو|promo|اعلان|إعلان|تتر|أنشودة|شرح عن', re.I)
ORD={'الأولى':1,'الاولى':1,'الأول':1,'الحادية':1,'الحادي':1,'الثانية':2,'الثاني':2,'الثالثة':3,'الثالث':3,'الرابعة':4,'الرابع':4,'الخامسة':5,'الخامس':5,'السادسة':6,'السادس':6,'السابعة':7,'السابع':7,'الثامنة':8,'الثامن':8,'التاسعة':9,'التاسع':9,'العاشرة':10,'العاشر':10}
TENS={'العشرون':20,'العشرين':20,'الثلاثون':30,'الثلاثين':30,'الأربعون':40}
NOISE=re.compile(r'#(اكسبلور|سائر\S*|سوريا|explore)\b',re.I)
def ordinal(seg):
    w=seg.replace('الحلقة','').split()
    n=0
    for x in w:
        y=x[1:] if x.startswith('و') and x[1:] in TENS else x
        if y in ORD: n+=ORD[y]
        elif y in TENS: n+=TENS[y]
        elif y in ('عشرة','عشر'): n+=10
    return n or None
def is_ep_seg(seg):
    return bool(re.match(r'^الحلقة\b',seg))
def seg_number(seg):
    m=re.search(r'الحلقة\s*\(?\s*(\d+)\s*\)?',seg)
    if m: return int(m.group(1))
    return ordinal(seg)
def split_title(raw, prog):
    t=raw.translate(AR_DIG)
    t=NOISE.sub('',t)
    segs=[x.strip(' "«»') for x in re.split(r'\s+[|]\s+|\s*\|\s*|\s+-\s+|\s+/(?:\s*/)*\s+',t) if x.strip(' "«»')]
    pn={prog, prog.rstrip('؟?'), 'برنامج '+prog, 'برنامج '+prog.rstrip('؟?'), prog.replace('برنامج ','')}
    pn|={p.split('...')[0] for p in list(pn)}
    num=None; keep=[]
    for x in segs:
        if x in pn: continue
        x=re.sub(r'(خطبة\s+(ال)?جمعة|خطبة العيد)?\s*\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}','',x).strip(' |-')
        if not x or re.fullmatch(r'خطبة\s+(ال)?جمعة|خطبة العيد', x): continue
        if re.fullmatch(r'\d{1,2}\s*/\s*\d{1,2}\s*/\s*\d{2,4}', x): continue
        if is_ep_seg(x):
            num=num or seg_number(x)
            rest=re.sub(r'^الحلقة\s*\(?\s*\d+\s*\)?\s*(والأخيرة)?','',x).strip()
            if rest and ordinal(x) is None: keep.append(rest)
            continue
        m=re.fullmatch(r'\|?\s*(\d{1,3})\s*\|?',x)
        if m: num=num or int(m.group(1)); continue
        m=re.match(r'^\((\d{1,3})\)\s*(.*)$',x)
        if m: num=num or int(m.group(1)); x=m.group(2)
        if x.startswith('#'):
            x=x.lstrip('#').replace('_',' ')
        x=re.sub(r'\s*#\S+(\s+\S+)?(\s+\d+)?\s*$','',x).strip() if re.search(r'#\S+(\s+\S+)?\s+\d+\s*$',x) else re.sub(r'\s*#\S+(\s+\d+)?\s*$','',x).strip()
        if x: keep.append(x)
    title=' — '.join(keep)
    if num is None:
        m=re.search(r'(\d{1,3})\s*$',raw.translate(AR_DIG))
        if m and '#' in raw: num=int(m.group(1))
    return num, title
def khutba_date(raw):
    """dd/mm/yyyy in a title -> 'yyyy-mm-dd', else ''."""
    m=re.search(r'(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4}|\d{2})\b', raw.translate(AR_DIG))
    if not m: return ''
    d,mo,y=int(m.group(1)),int(m.group(2)),int(m.group(3))
    y=y+2000 if y<100 else y
    return f'{y:04d}-{mo:02d}-{d:02d}' if 1<=d<=31 and 1<=mo<=12 and 2000<y<2100 else ''
def dur(s):
    if not s: return ''
    s=int(s); return f'{s//3600}:{s%3600//60:02d}:{s%60:02d}' if s>=3600 else f'{s//60}:{s%60:02d}'
