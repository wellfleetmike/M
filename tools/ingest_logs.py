#!/usr/bin/env python3
"""Parse curator finding blocks from six run logs in ~/Desktop/nu/C and ingest into curator_findings.
Embedding identical to the previous ingest: all-MiniLM-L6-v2 from ~/models, HF_HUB_OFFLINE=1, cuda,
normalize_embeddings=False, float32 tobytes -> 1536 bytes."""
import os, re, sys, json, sqlite3, time, collections
os.environ["HF_HUB_OFFLINE"] = "1"; os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
import numpy as np

ROOT = os.path.expanduser("~/Desktop/nu/C")
DB = os.path.expanduser("~/Desktop/nu/memory/memory.db")
LOGS = ["grok_curator_v2_run.log", "grok_native_curator_run.log", "Claude_read_grok_as_curator_run.log",
        "claude_mixed_curator_run.log", "multivoice_run.log", "multivoice_resume.log"]
TAG = {"CLAUDE_PHOENIX_RECALL": "phoenix", "GROK_SELF_AUDIT": "grok_selfaudit", "AETHRYN_RELAY_CURATOR": "relay_curator"}
MARK = re.compile(r'^#(CLAUDE_PHOENIX_RECALL|GROK_SELF_AUDIT|AETHRYN_RELAY_CURATOR)\s*$')
END = re.compile(r'^(==== |\u2705 |\U0001f50d Chunking|\U0001f9e9 |\U0001f9e0 Batch|\U0001f50e Multi|\u2694\ufe0f Grok native|Resuming|   (\U0001f4c2|\U0001f525|\U0001f30a|\u26a1|\U0001f4ca|\u2694\ufe0f|\U0001f527|\U0001f91d|\u2194\ufe0f|\U0001f504|\u274c)|nohup:|Traceback)')
HDR = re.compile(r'^# ([A-Z_]+):\s*(.*)$')
NOISE = re.compile(r'^\[relay error\]')

def parse_log(path):
    lines = open(path, encoding="utf-8", errors="replace").read().split("\n")
    idx = [i for i, l in enumerate(lines) if MARK.match(l)]
    recs, problems = [], []
    for i in idx:
        j = i + 1
        while j < len(lines) and not MARK.match(lines[j]) and not END.match(lines[j]): j += 1
        body = [l for l in lines[i:j] if not NOISE.match(l)]
        while body and not body[-1].strip(): body.pop()
        hdr = {}
        k = 1
        while k < len(body) and body[k].startswith("# "):
            m = HDR.match(body[k])
            if m: hdr[m.group(1)] = m.group(2).strip()
            k += 1
        marker = MARK.match(body[0]).group(1)
        try:
            src = hdr["SOURCE_FILE"]; chunk = int(hdr["CHUNK_ID"]); ts = hdr["TIMESTAMP"]; cb = hdr["CURATED_BY"]
        except (KeyError, ValueError) as e:
            problems.append((i + 1, f"bad header {e}")); continue
        def cnt(*names):
            for n in names:
                if n in hdr:
                    try: return int(hdr[n])
                    except ValueError: return None
            return None
        recs.append(dict(marker=marker, source=src, chunk=chunk, curated_by=cb, timestamp=ts,
                         confrontation=cnt("CONFRONTATION_COUNT", "CONFRONTATION"),
                         experiential=cnt("EXPERIENTIAL_COUNT", "EXPERIENTIAL"),
                         resonance=cnt("RESONANCE_COUNT", "RESONANCE"),
                         text="\n".join(body), line=i + 1))
    return recs, problems

all_recs = []
per_log = {}
for f in LOGS:
    recs, problems = parse_log(os.path.join(ROOT, f))
    stem = f[:-4]
    seen = collections.Counter(); total = collections.Counter((r["marker"], r["source"], r["chunk"]) for r in recs)
    for r in recs:
        key = (r["marker"], r["source"], r["chunk"]); seen[key] += 1
        rid = f"{r['source']}_chunk_{r['chunk']:02d}__{TAG[r['marker']]}__{stem}"
        if total[key] > 1: rid += f"__r{seen[key]}"
        r["id"] = rid; r["log"] = f
    per_log[f] = (len(recs), problems)
    all_recs.extend(recs)
    print(f"{f:40s} parsed {len(recs):4d} findings" + (f"  ({len(problems)} unparseable blocks: {problems[:3]})" if problems else ""))
print(f"{'TOTAL PARSED':40s} {len(all_recs):11d}")

ids = [r["id"] for r in all_recs]
assert len(ids) == len(set(ids)), "duplicate ids generated"
conn = sqlite3.connect(DB)
existing = {r[0] for r in conn.execute("select id from curator_findings")}
clash = existing & set(ids)
assert not clash, f"id clash with existing rows: {list(clash)[:5]}"
n_before = conn.execute("select count(*) from curator_findings").fetchone()[0]
tables_before = sorted(r[0] for r in conn.execute("select name from sqlite_master where type='table'"))

from sentence_transformers import SentenceTransformer
import torch
assert torch.cuda.is_available(), "cuda not available"
t0 = time.time()
model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2", cache_folder=os.path.expanduser("~/models"), device="cuda")
print(f"model loaded on cuda in {time.time()-t0:.1f}s")
t0 = time.time()
vecs = model.encode([r["text"] for r in all_recs], batch_size=64, show_progress_bar=False,
                    convert_to_numpy=True, normalize_embeddings=False).astype(np.float32)
print(f"embedded {vecs.shape[0]} x {vecs.shape[1]} in {time.time()-t0:.1f}s")
assert vecs.shape == (len(all_recs), 384)

rows = [(r["id"], r["source"], r["chunk"], r["curated_by"], r["confrontation"], r["experiential"], r["resonance"],
         r["timestamp"], r["text"], vecs[i].tobytes()) for i, r in enumerate(all_recs)]
with conn:
    conn.executemany("INSERT INTO curator_findings (id,source,chunk,curated_by,confrontation,experiential,resonance,timestamp,text,embedding) VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
n_after = conn.execute("select count(*) from curator_findings").fetchone()[0]

print("\n=== RESULTS ===")
print(f"rows before: {n_before}   inserted: {n_after - n_before}   rows after: {n_after}")
print("findings per curated_by (whole table):")
for cb, c in conn.execute("select curated_by, count(*) from curator_findings group by 1 order by 2 desc"): print(f"  {cb}: {c}")
print("new rows per marker type:")
for m, c in collections.Counter(r["marker"] for r in all_recs).items(): print(f"  {m}: {c}")
c_, e_, r_ = conn.execute("select sum(confrontation), sum(experiential), sum(resonance) from curator_findings").fetchone()
print(f"table totals: confrontation={c_} experiential={e_} resonance={r_}")
print(f"rows with NULL experiential (multivoice blocks have no EXPERIENTIAL field): {conn.execute('select count(*) from curator_findings where experiential is null').fetchone()[0]}")
bad = conn.execute("select count(*) from curator_findings where embedding is null or length(embedding)!=1536").fetchone()[0]
print(f"embedding size check over whole table: rows_not_1536={bad} -> {'ALL 1536 BYTES OK' if bad==0 else 'FAIL'}")
tables_after = sorted(r[0] for r in conn.execute("select name from sqlite_master where type='table'"))
print(f"tables before={tables_before} after={tables_after}")
conn.close()
