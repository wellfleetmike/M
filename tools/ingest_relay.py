#!/usr/bin/env python3
import os, sqlite3, time
os.environ["HF_HUB_OFFLINE"]="1"; os.environ.setdefault("TRANSFORMERS_OFFLINE","1")
import numpy as np
SRC="/home/mike/ball/home/mike/Desktop/shared/relay_memory.db"   # byte-identical to the other two copies
DB=os.path.expanduser("~/Desktop/nu/memory/memory.db")

s=sqlite3.connect(f"file:{SRC}?mode=ro",uri=True); s.row_factory=sqlite3.Row
mems=[dict(r) for r in s.execute("select * from memories order by created_at")]; s.close()
print(f"source: {SRC}\nmemories read: {len(mems)}")

def tier_of(tags):
    for t in (tags or "").split(","):
        t=t.strip()
        if t.startswith("tier:"): return t.split(":",1)[1]
    return "sovereign"   # export_bridge.py default for untagged memories

recs=[]
for m in mems:
    content=f"[{m['type']}] {m['name']}\n{m['description']}\n\n{m['content']}".strip()
    if m["tags"]: content+=f"\n\ntags: {m['tags']}"
    recs.append((m["id"], SRC, content, m["updated_at"], tier_of(m["tags"])))

from sentence_transformers import SentenceTransformer
import torch; assert torch.cuda.is_available()
model=SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", cache_folder=os.path.expanduser("~/models"), device="cuda")
t0=time.time()
vecs=model.encode([r[2] for r in recs], batch_size=64, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=False).astype(np.float32)
print(f"embedded {vecs.shape[0]} x {vecs.shape[1]} on cuda in {time.time()-t0:.1f}s")

c=sqlite3.connect(DB)
before=sorted(r[0] for r in c.execute("select name from sqlite_master where type='table'"))
c.execute("""CREATE TABLE IF NOT EXISTS relay_memories (
    id TEXT PRIMARY KEY, source_file TEXT, content TEXT, timestamp TEXT, tier TEXT, embedding BLOB)""")
with c:
    c.executemany("INSERT INTO relay_memories VALUES (?,?,?,?,?,?)", [r+(vecs[i].tobytes(),) for i,r in enumerate(recs)])
print("\n=== RESULTS ===")
print("relay_memories rows:", c.execute("select count(*) from relay_memories").fetchone()[0])
print("by tier:", c.execute("select tier, count(*) from relay_memories group by 1").fetchall())
print("by memory type:", {t:sum(1 for m in mems if m['type']==t) for t in ('user','feedback','project','reference')})
bad=c.execute("select count(*) from relay_memories where embedding is null or length(embedding)!=1536").fetchone()[0]
lo,hi=c.execute("select min(length(embedding)),max(length(embedding)) from relay_memories").fetchone()
print(f"embedding check: min={lo} max={hi} not_1536={bad} -> {'ALL 1536 BYTES OK' if bad==0 else 'FAIL'}")
print("curator_findings untouched:", c.execute("select count(*) from curator_findings").fetchone()[0], "rows")
print("tables before:",before," after:",sorted(r[0] for r in c.execute("select name from sqlite_master where type='table'")))
c.close()
