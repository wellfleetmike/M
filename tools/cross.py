#!/usr/bin/env python3
import json, re, sqlite3, collections, datetime, os
PICS=os.path.expanduser('~/Desktop/nu/pics_matched.jsonl'); DB='/home/mike/Desktop/nu/backup/memory/memory.db'
OUT=os.path.expanduser('~/Desktop/nu/CLASSIFIER_SCREENSHOT_CROSS.md')
recs=[json.loads(l) for l in open(PICS)]
COMP=["compacted","context window","summary of the content"]
FN_HINTS=re.compile(r'compact|context|summar|memory|limit|reset|clear',re.I)

# ---- part 1: compaction-related screenshots
flagged=[]
for r in recs:
    hits=[(m,[p for p in COMP if p in m['body'].lower()]) for m in r['matches']]
    hits=[(m,ps) for m,ps in hits if ps]
    if hits: flagged.append((r,hits))
fn_hits=[r for r in recs if FN_HINTS.search(r['filename'])]
name_shapes=collections.Counter(re.sub(r'\d','N',r['filename']) for r in recs)

# ---- part 2: classifier conversations x screenshots
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True)
titles=dict(c.execute("select uuid,title from conversations"))
cls=dict(c.execute("select conversation_uuid, count(*) from messages where lower(body) like '%classifier%' group by 1"))
narrow=dict(c.execute("""select conversation_uuid, count(*) from messages where lower(body) like '%safety classifier%' or lower(body) like '%flagged by safety%' or lower(body) like '%i need to flag%' or lower(body) like '%api error%' or lower(body) like '%content policy%' group by 1"""))
shots=collections.defaultdict(set)      # conv -> set of filenames (any rank in matches)
shots_top=collections.defaultdict(set)  # conv -> filenames where it is the nearest match
for r in recs:
    for i,m in enumerate(r['matches']):
        shots[m['conversation_uuid']].add(r['filename'])
        if i==0: shots_top[m['conversation_uuid']].add(r['filename'])
both=[(u,cls[u],len(shots[u]),len(shots_top[u])) for u in cls if u in shots]
both.sort(key=lambda x:(-x[1],-x[2]))
convs_with_shots=len({m['conversation_uuid'] for r in recs for m in r['matches']})

o=[]
o.append("# CLASSIFIER \u00d7 SCREENSHOT CROSS-REFERENCE\n")
o.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}  ")
o.append(f"Inputs: `{PICS}` ({len(recs)} images, {sum(1 for r in recs if r['matches'])} with matches) and `{DB}` (read-only).  ")
o.append("A screenshot is 'associated' with a conversation when that conversation appears anywhere in the image's up-to-3 nearest messages (\u00b130 min). 'Nearest' counts only rank-1 matches.\n")
o.append("## Summary\n")
o.append("| Metric | Value |\n|---|---:|")
o.append(f"| Images whose match snippets mention compaction terms | {len(flagged)} |")
o.append(f"| Image filenames suggesting a compaction screenshot | {len(fn_hits)} |")
o.append(f"| Conversations matching `classifier` | {len(cls)} |")
o.append(f"| \u2026of those, with at least one associated screenshot | {len(both)} |")
o.append(f"| \u2026of those, with a screenshot whose nearest message is theirs | {sum(1 for b in both if b[3]>0)} |")
o.append(f"| Distinct conversations with any associated screenshot | {convs_with_shots} |")
o.append(f"| Screenshots associated with classifier conversations | {len(set().union(*[shots[u] for u,_,_,_ in both])) if both else 0} of {len(recs)} |\n")

o.append("## Part 1: Compaction-related screenshots\n")
o.append(f"Terms searched in the 200-character match snippets: {', '.join('`'+p+'`' for p in COMP)}. Snippets are truncated, so a term appearing later in a message is not visible here.\n")
if flagged:
    o.append("| Image | best_date | Conversation | Message time | Sender | Term | Snippet |\n|---|---|---|---|---|---|---|")
    for r,hits in flagged:
        for m,ps in hits:
            o.append(f"| `{r['filename']}` | {r['best_date']} | {titles.get(m['conversation_uuid'],'?')} | {m['server_time_iso'][:19]} | {m['sender']} | {', '.join(ps)} | {m['body'].replace(chr(10),' / ').replace('|','\\|')[:200]} |")
else: o.append("_none_")
o.append("\n### Filename search\n")
o.append(f"Patterns tried in filenames: `{FN_HINTS.pattern}` (case-insensitive). Hits: {len(fn_hits)}.\n")
o.append("Filename shapes present in the set (digits replaced by N):\n")
for s,n in name_shapes.most_common(): o.append(f"- `{s}` \u00d7 {n}")
o.append("\nEvery filename is the Android default `Screenshot_<date>_<time>_<app>.jpg`. The only variable text is the app name (Claude, Chrome, Chrome(1)), so filenames carry no signal about content. Compaction screenshots can only be identified by timestamp proximity or by looking at the image.\n")

o.append("## Part 2: Classifier conversations with associated screenshots\n")
o.append(f"{len(both)} of the {len(cls)} conversations that match `classifier` have at least one screenshot. Sorted by classifier flag count, descending. 'Narrow flags' counts messages matching the event-style patterns (safety classifier, flagged by safety, I need to flag, API Error, content policy).\n")
o.append("| # | Classifier flags | Narrow flags | Screenshots (any rank) | Screenshots (nearest) | Conversation | UUID |\n|---:|---:|---:|---:|---:|---|---|")
for i,(u,n,s,st) in enumerate(both,1):
    o.append(f"| {i} | {n} | {narrow.get(u,0)} | {s} | {st} | {titles.get(u,'?').replace('|','\\|')} | `{u}` |")
o.append("\n### Screenshots per conversation (for the list above)\n")
for u,n,s,st in both:
    o.append(f"**{titles.get(u,'?')}** (`{u}`) \u2014 {n} flags, {s} screenshots\n")
    for fn in sorted(shots[u]): o.append(f"- `{fn}`" + ("  (nearest)" if fn in shots_top[u] else ""))
    o.append("")
o.append("### Classifier conversations with NO screenshots\n")
none=[u for u in cls if u not in shots]; none.sort(key=lambda u:-cls[u])
o.append(f"{len(none)} conversations.\n")
for u in none: o.append(f"- {cls[u]} flags \u2014 {titles.get(u,'?')} (`{u}`)")
open(OUT,'w',encoding='utf-8').write("\n".join(o)+"\n")

print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")
print(f"images with compaction terms in match snippets: {len(flagged)}")
print(f"filenames suggesting compaction: {len(fn_hits)}; filename shapes: {dict(name_shapes)}")
print(f"classifier conversations: {len(cls)}; with screenshots: {len(both)}; with nearest-rank screenshots: {sum(1 for b in both if b[3]>0)}")
print(f"conversations with any screenshot at all: {convs_with_shots}")
print("\ntop 15 by flag count:")
for u,n,s,st in both[:15]: print(f"  flags={n:3d} narrow={narrow.get(u,0):3d} shots={s:3d} nearest={st:3d}  {titles.get(u,'?')[:60]}")
