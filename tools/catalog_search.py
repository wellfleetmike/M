#!/usr/bin/env python3
import os, sqlite3, datetime, collections
CAT = os.path.expanduser("~/Desktop/nu/curator_pass/indexed_drives/catalog.db")
LOCAL = os.path.expanduser("~/Desktop/nu/curator_jsonl")
OUT = os.path.expanduser("~/Desktop/nu/MISSING_CURATOR_FILES.md")

WHERE = """filename LIKE '%claude_phoenix.jsonl'
   OR filename LIKE '%grok_selfaudit.jsonl'
   OR filename LIKE '%grok_native.jsonl'
   OR filename LIKE '%relay_curator.jsonl'
   OR filename LIKE '%multivoice.jsonl'
   OR filename LIKE '%phoenix_recall%'
   OR filename LIKE '%curator%jsonl'"""

c = sqlite3.connect(f"file:{CAT}?mode=ro", uri=True)
raw = c.execute(f"SELECT filename, size, volume, relpath FROM files WHERE {WHERE} ORDER BY filename, size, volume, relpath").fetchall()
# archive_members: same filename column; drive plays the role of volume
arch = c.execute(f"SELECT filename, size, drive, relpath FROM archive_members WHERE {WHERE} ORDER BY filename, size, drive, relpath").fetchall()
# zip_members: 'name' is the member path; match on basename
zips = c.execute("""SELECT zm.name, zm.size, zf.zip_path FROM zip_members zm JOIN zip_files zf ON zf.id=zm.zip_id
  WHERE zm.name LIKE '%claude_phoenix.jsonl' OR zm.name LIKE '%grok_selfaudit.jsonl' OR zm.name LIKE '%grok_native.jsonl'
     OR zm.name LIKE '%relay_curator.jsonl' OR zm.name LIKE '%multivoice.jsonl' OR zm.name LIKE '%phoenix_recall%' OR zm.name LIKE '%curator%jsonl'""").fetchall()

def dedup(rows):
    seen = collections.OrderedDict()
    for fn, sz, vol, rp in rows:
        seen.setdefault((fn, sz), []).append((vol, rp))
    return seen

files_d = dedup(raw)
arch_d = dedup(arch)

local = {fn: os.path.getsize(os.path.join(LOCAL, fn)) for fn in os.listdir(LOCAL)}

print(f"files table raw hits: {len(raw)}  deduped (filename,size): {len(files_d)}")
print(f"archive_members raw hits: {len(arch)}  deduped: {len(arch_d)}")
print(f"zip_members hits: {len(zips)}")
print("\nfilename | size | volume | relpath")
for (fn, sz), locs in files_d.items():
    for vol, rp in locs:
        print(f"{fn} | {sz} | {vol} | {rp}")

def status(fn, sz):
    if fn not in local: return "MISSING"
    return "present (same size)" if local[fn] == sz else f"present, DIFFERENT size (local {local[fn]})"

out = []
out.append("# MISSING CURATOR FILES\n")
out.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}  ")
out.append(f"Catalog: `{CAT}` (opened read-only)  ")
out.append(f"Compared against: `{LOCAL}` ({len(local)} files)  ")
out.append("Query: `files` table where\n")
out.append("```sql\n" + WHERE + "\n```\n")
out.append(f"Raw hits in `files`: {len(raw)}. Deduplicated by (filename, size): {len(files_d)}.\n")

missing = [(k, v) for k, v in files_d.items() if k[0] not in local]
diff = [(k, v) for k, v in files_d.items() if k[0] in local and local[k[0]] != k[1]]
present = [(k, v) for k, v in files_d.items() if k[0] in local and local[k[0]] == k[1]]

out.append("## Summary\n")
out.append("| Status | Distinct (filename, size) |")
out.append("|---|---:|")
out.append(f"| NOT in curator_jsonl | {len(missing)} |")
out.append(f"| In curator_jsonl, different size | {len(diff)} |")
out.append(f"| In curator_jsonl, same size | {len(present)} |")
out.append("")

def table(title, items, note=None):
    out.append(f"## {title}\n")
    if note: out.append(note + "\n")
    if not items:
        out.append("_none_\n"); return
    out.append("| Filename | Size | Drive (volume) | Relpath |")
    out.append("|---|---:|---|---|")
    for (fn, sz), locs in items:
        for vol, rp in locs:
            out.append(f"| `{fn}` | {sz} | {vol} | `{rp}` |")
    out.append("")

table("NOT in curator_jsonl (need to be pulled)", missing,
      "Every drive location for each distinct (filename, size) is listed so you can see which volume holds it.")
table("In curator_jsonl but a DIFFERENT size exists on a drive", diff,
      "Same filename is already local, but a copy with a different byte size is catalogued. Local size shown in the Notes below.")
if diff:
    out.append("Local sizes for the above:\n")
    for (fn, sz), _ in diff: out.append(f"- `{fn}`: local {local[fn]} bytes vs catalogued {sz}")
    out.append("")
table("Already in curator_jsonl (same size)", present)

# by-drive rollup of missing
out.append("## Missing files by drive\n")
byvol = collections.Counter()
for (fn, sz), locs in missing:
    for vol, _ in {v: 1 for v, _ in locs}.items() if False else locs:
        pass
seen = set()
for (fn, sz), locs in missing:
    for vol, _ in locs:
        if (fn, sz, vol) not in seen:
            seen.add((fn, sz, vol)); byvol[vol] += 1
if byvol:
    out.append("| Drive | Missing (filename,size) pairs present there |")
    out.append("|---|---:|")
    for vol, n in byvol.most_common(): out.append(f"| {vol} | {n} |")
else:
    out.append("_none_")
out.append("")

out.append("## Supplementary: matches inside archives\n")
out.append(f"`archive_members` (tar contents indexed per drive): {len(arch)} raw hits, {len(arch_d)} distinct (filename, size). These are inside tar archives, not loose files.\n")
if arch_d:
    out.append("| Filename | Size | Drive | Member relpath | In curator_jsonl? |")
    out.append("|---|---:|---|---|---|")
    for (fn, sz), locs in arch_d.items():
        for vol, rp in locs:
            out.append(f"| `{fn}` | {sz} | {vol} | `{rp}` | {status(fn, sz)} |")
    out.append("")
out.append(f"`zip_members`: {len(zips)} hits.\n")
if zips:
    out.append("| Member name | Size | Zip path | In curator_jsonl? |")
    out.append("|---|---:|---|---|")
    for name, sz, zp in zips:
        out.append(f"| `{name}` | {sz} | `{zp}` | {status(os.path.basename(name), sz)} |")
    out.append("")

open(OUT, "w", encoding="utf-8").write("\n".join(out) + "\n")
print(f"\nwrote {OUT}")
print(f"missing={len(missing)} diff_size={len(diff)} present={len(present)}")
print("missing by drive:", dict(byvol))
