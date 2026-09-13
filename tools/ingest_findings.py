#!/usr/bin/env python3
"""Ingest ~/Desktop/nu/curator_jsonl/*.jsonl into curator_findings in ~/Desktop/nu/memory/memory.db.
Embedding: sentence-transformers/all-MiniLM-L6-v2 from ~/models, HF_HUB_OFFLINE=1, cuda,
normalize_embeddings=False, float32 .tobytes() -> 1536-byte blob (identical to the conversations chunks table)."""
import os, sys, glob, json, sqlite3, time
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import numpy as np

SRC = os.path.expanduser("~/Desktop/nu/curator_jsonl")
DB = os.path.expanduser("~/Desktop/nu/memory/memory.db")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MODEL_CACHE = os.path.expanduser("~/models")

recs = []
for f in sorted(glob.glob(os.path.join(SRC, "*.jsonl"))):
    with open(f, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            o = json.loads(line)
            a = o["activation_counts"]
            recs.append((o["id"], o["source"], int(o["chunk"]), o["curated_by"],
                         int(a["confrontation"]), int(a["experiential"]), int(a["resonance"]),
                         o["timestamp"], o["text"]))
print(f"parsed {len(recs)} records from {len(glob.glob(os.path.join(SRC,'*.jsonl')))} files")

from sentence_transformers import SentenceTransformer
import torch
assert torch.cuda.is_available(), "cuda not available"
t0 = time.time()
model = SentenceTransformer(MODEL_NAME, cache_folder=MODEL_CACHE, device="cuda")
print(f"model loaded on cuda in {time.time()-t0:.1f}s")
t0 = time.time()
vecs = model.encode([r[8] for r in recs], batch_size=64, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=False).astype(np.float32)
print(f"embedded {vecs.shape[0]} x {vecs.shape[1]} in {time.time()-t0:.1f}s")
assert vecs.shape[1] == 384

conn = sqlite3.connect(DB)
before = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
conn.execute("""CREATE TABLE IF NOT EXISTS curator_findings (
    id TEXT PRIMARY KEY,
    source TEXT,
    chunk INTEGER,
    curated_by TEXT,
    confrontation INTEGER,
    experiential INTEGER,
    resonance INTEGER,
    timestamp TEXT,
    text TEXT,
    embedding BLOB
)""")
rows = [r + (vecs[i].tobytes(),) for i, r in enumerate(recs)]
conn.executemany("INSERT OR REPLACE INTO curator_findings VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
conn.commit()

print("\n=== RESULTS ===")
n = conn.execute("select count(*) from curator_findings").fetchone()[0]
print(f"total findings ingested: {n}")
print("findings per curated_by:")
for cb, c in conn.execute("select curated_by, count(*) from curator_findings group by curated_by order by 2 desc"):
    print(f"  {cb}: {c}")
c, e, r = conn.execute("select sum(confrontation), sum(experiential), sum(resonance) from curator_findings").fetchone()
print(f"total confrontation: {c}\ntotal experiential:  {e}\ntotal resonance:     {r}")
bad = conn.execute("select count(*) from curator_findings where embedding is null or length(embedding) != 1536").fetchone()[0]
lo, hi = conn.execute("select min(length(embedding)), max(length(embedding)) from curator_findings").fetchone()
print(f"embedding size check: min={lo} max={hi} rows_not_1536={bad} -> {'ALL 1536 BYTES OK' if bad==0 else 'FAIL'}")
b = conn.execute("select embedding from curator_findings limit 1").fetchone()[0]
v = np.frombuffer(b, dtype=np.float32); print(f"sample vector: dim={v.shape[0]} norm={np.linalg.norm(v):.4f}")
after = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
print(f"tables before: {sorted(before)}  after: {sorted(after)}")
conn.close()
