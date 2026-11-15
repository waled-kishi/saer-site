import json, re, os, yaml
Y='/home/claude/saer-site/.saer/youtube'
OUT='/home/claude/saer-site/.saer/content-seed/02.programs'
progs = [  # (playlist id, slug) in the order Walid listed them
 ('PLgIzcOU7lAOdQDyJkt4HiYVOiK9pKw0mc','al-mawid-allah'),
 ('PLgIzcOU7lAOdpKMGMORo0pA8A-S9sFGIG','ala-al-aatab'),
 ('PLgIzcOU7lAOdf4YXEFL8mvILjSSLj0GZ2','shifaa'),
 ('PLgIzcOU7lAOeVY2aj-E7leAds2a1C3RZ3','habbet-waai'),
 ('PLgIzcOU7lAOfdOKP_bD0tAa9FtnDOHN36','bekhtisar'),
 ('PLgIzcOU7lAOeF7WkTx6ujfBRLsYznSx9A','kayfa-akoon'),
 ('PLgIzcOU7lAOeufnC8kvG0sh_5BMBan-QC','laysh'),
 ('PLgIzcOU7lAOdGHdDqQHq-RAGBhYgcuZyR','asrar-al-quran'),
 ('PLgIzcOU7lAOde6NNuWByNcdRvPVd__NYr','waai-al-asrar'),
 ('PLgIzcOU7lAOd3Txvuci_lYHygyXHn1eVC','insan'),
 ('PLgIzcOU7lAOezL7BQp8S9RovIrBcR-VLj','qissa-wa-ibra'),
 ('PLgIzcOU7lAOdnerNZUzjo-A9jWQic0_0I','al-lahza-al-helwa'),
]
units={'الأولى':1,'الاولى':1,'الأول':1,'الحادية':1,'الحادي':1,'الثانية':2,'الثاني':2,'الثالثة':3,'الثالث':3,'الرابعة':4,'الرابع':4,'الخامسة':5,'الخامس':5,'السادسة':6,'السادس':6,'السابعة':7,'السابع':7,'الثامنة':8,'الثامن':8,'التاسعة':9,'التاسع':9,'العاشرة':10,'العاشر':10}
tens={'العشرون':20,'العشرين':20,'الثلاثون':30,'الثلاثين':30}
AR_DIG=str.maketrans('٠١٢٣٤٥٦٧٨٩','0123456789')
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
    segs=[x.strip(' "«»') for x in re.split(r'\s+[|]\s+|\s*\|\s*|\s+-\s+',t) if x.strip(' "«»')]
    pn={prog, prog.rstrip('؟?'), 'برنامج '+prog, 'برنامج '+prog.rstrip('؟?'), prog.replace('برنامج ','')}
    pn|={p.split('...')[0] for p in list(pn)}
    num=None; keep=[]
    for x in segs:
        if x in pn: continue
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
def number(t): return None
def clean(t,prog): return t
def dur(s):
    if not s: return ''
    s=int(s); return f'{s//3600}:{s%3600//60:02d}:{s%60:02d}' if s>=3600 else f'{s//60}:{s%60:02d}'
report=[]
for i,(pid,slug) in enumerate(progs, start=2):
    d=json.load(open(f'{Y}/{pid}.json'))
    title=d['title'].strip()
    desc=(d.get('description') or '').strip().split('\n')[0].strip()
    seen=set(); eps=[]; trailers=[]
    for v in d['videos']:
        if not v.get('id') or v['id'] in seen: continue
        seen.add(v['id'])
        raw=v.get('title') or ''
        if re.search(r'تشويق|برومو|promo|اعلان|إعلان|تتر|أنشودة|شرح عن',raw,re.I): trailers.append(v); continue
        n,tt=split_title(raw,title)
        eps.append({'id':v['id'],'raw':raw,'n':n,'t':tt,'dur':dur(v.get('duration'))})
    nums=[e['n'] for e in eps if e['n']]
    sorted_mode = len(nums)>=max(2,len(eps)*0.6)
    if sorted_mode:
        eps.sort(key=lambda e:(e['n'] is None, e['n'] or 0))
    else:
        for k,e in enumerate(eps, start=1): e['n']=k
    for k,e in enumerate(eps, start=1):
        if not e['t']: e['t']=f'الحلقة {e["n"] or k}'
    pdir=f'{OUT}/{i:02d}.{slug}'
    os.makedirs(pdir,exist_ok=True)
    h={'title':title,'kind':'series','summary':desc or None,'youtube_playlist':f'https://www.youtube.com/playlist?list={pid}'}
    if trailers: h['trailer']=f'https://www.youtube.com/watch?v={trailers[0]["id"]}'
    h={k:v for k,v in h.items() if v}
    open(f'{pdir}/series.md','w',encoding='utf-8').write('---\n'+yaml.safe_dump(h,allow_unicode=True,sort_keys=False,width=1000)+'---\n')
    for k,e in enumerate(eps, start=1):
        eh={'title':e['t'],'number':e['n'] or k,'youtube':f'https://www.youtube.com/watch?v={e["id"]}'}
        if e['dur']: eh['duration']=e['dur']
        ed=f'{pdir}/{k:02d}.ep-{k:02d}'; os.makedirs(ed,exist_ok=True)
        open(f'{ed}/episode.md','w',encoding='utf-8').write('---\n'+yaml.safe_dump(eh,allow_unicode=True,sort_keys=False,width=1000)+'---\n')
    report.append((title,len(eps),len(trailers),[ (e['n'],e['t']) for e in eps[:3]], [(e['n'],e['t']) for e in eps[-2:]]))
for r in report: print(r[0],'| eps',r[1],'| trailers',r[2]); print('   first',r[3]); print('   last',r[4])
