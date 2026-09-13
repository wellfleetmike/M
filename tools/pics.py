#!/usr/bin/env python3
import os, re, json, hashlib, sqlite3, datetime, collections
from zoneinfo import ZoneInfo
from PIL import Image, ExifTags
D=os.path.expanduser('~/Desktop/nu/curator_pass/claude_pics')
MAN=os.path.expanduser('~/Desktop/nu/pics_manifest.jsonl')
MAT=os.path.expanduser('~/Desktop/nu/pics_matched.jsonl')
DB='/home/mike/Desktop/nu/backup/memory/memory.db'   # the copy that holds the messages table
LOCAL=ZoneInfo('America/New_York')
FN_RE=re.compile(r'(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})')
TAGS={v:k for k,v in ExifTags.TAGS.items()}

def exif_date(im):
    ex=im.getexif()
    if not ex: return None
    ifd={}
    try: ifd=ex.get_ifd(0x8769)
    except Exception: pass
    def g(name):
        k=TAGS[name]; return ifd.get(k) or ex.get(k)
    for dt_tag,off_tag in (('DateTimeOriginal','OffsetTimeOriginal'),('DateTimeDigitized','OffsetTimeDigitized'),('DateTime','OffsetTime')):
        v=g(dt_tag)
        if not v or not isinstance(v,str): continue
        try: naive=datetime.datetime.strptime(v.strip()[:19],'%Y:%m:%d %H:%M:%S')
        except ValueError: continue
        off=g(off_tag)
        if off and re.match(r'^[+-]\d{2}:\d{2}$',off.strip()):
            sign=1 if off[0]=='+' else -1; hh,mm=off[1:].split(':')
            tz=datetime.timezone(sign*datetime.timedelta(hours=int(hh),minutes=int(mm)))
            aware=naive.replace(tzinfo=tz)
        else:
            aware=naive.replace(tzinfo=LOCAL)   # no offset tag: assume local (America/New_York)
        return aware.astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    return None

def filename_date(name):
    m=FN_RE.search(name)
    if not m: return None
    try: naive=datetime.datetime(*map(int,m.groups()))
    except ValueError: return None
    return naive.replace(tzinfo=LOCAL).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

recs=[]; errors=[]
for dp,dn,fn in os.walk(D):
    for f in sorted(fn):
        if not f.lower().endswith(('.jpg','.jpeg','.png')): continue
        p=os.path.join(dp,f)
        h=hashlib.sha256(open(p,'rb').read()).hexdigest()
        w=hgt=None; ed=None
        try:
            with Image.open(p) as im:
                w,hgt=im.size; ed=exif_date(im)
        except Exception as e: errors.append((f,str(e)))
        fd=filename_date(f)
        recs.append({"filename":f,"path":p,"sha256":h,"exif_date":ed,"filename_date":fd,"best_date":ed or fd,
                     "size":os.path.getsize(p),"width":w,"height":hgt})
with open(MAN,'w',encoding='utf-8') as fh:
    for r in recs: fh.write(json.dumps(r,ensure_ascii=True)+'\n')

c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
Q="""SELECT conversation_uuid, server_time_iso, sender, substr(body,1,200)
FROM messages
WHERE julianday(server_time_iso) BETWEEN julianday(?, '-30 minutes') AND julianday(?, '+30 minutes')
ORDER BY abs(julianday(server_time_iso) - julianday(?)) LIMIT 3"""
n_zero=n_hit=0
with open(MAT,'w',encoding='utf-8') as fh:
    for r in recs:
        m=[]
        if r['best_date']:
            m=[{"conversation_uuid":a,"server_time_iso":b,"sender":s,"body":t} for a,b,s,t in c.execute(Q,(r['best_date'],r['best_date'],r['best_date']))]
        if m: n_hit+=1
        else: n_zero+=1
        fh.write(json.dumps({**r,"matches":m},ensure_ascii=True)+'\n')

tot=len(recs); ex=sum(1 for r in recs if r['exif_date']); fo=sum(1 for r in recs if not r['exif_date'] and r['filename_date'])
nd=sum(1 for r in recs if not r['best_date'])
print(f"total images found:                 {tot}")
print(f"images with EXIF dates:             {ex}")
print(f"images dated by filename only:      {fo}")
print(f"images with no date at all:         {nd}")
print(f"images with zero matches in memory.db: {n_zero}")
print(f"images with at least one match:     {n_hit}")
print(f"image read errors: {len(errors)} {errors[:3]}")
# sanity
agree=sum(1 for r in recs if r['exif_date'] and r['filename_date'] and abs((datetime.datetime.fromisoformat(r['exif_date'][:-1])-datetime.datetime.fromisoformat(r['filename_date'][:-1])).total_seconds())<=60)
print(f"exif vs filename date agree within 60s: {agree} of {sum(1 for r in recs if r['exif_date'] and r['filename_date'])}")
print("best_date range:", min(r['best_date'] for r in recs if r['best_date']), "..", max(r['best_date'] for r in recs if r['best_date']))
print("wrote", MAN, "and", MAT)
