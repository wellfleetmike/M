#!/usr/bin/env python3
import sqlite3, re, collections, datetime, os
DB='/home/mike/Desktop/nu/backup/memory/memory.db'
OUT=os.path.expanduser('~/Desktop/nu/CLASSIFIER_AND_COMPACTION.md')
P1=["flagged by safety","classifier","content policy","I can't assist","I'm not able to","unable to help","against my guidelines","I can't help with","I need to flag","safety classifier","content warning","anthropic.com/legal/aup","reasoning_extraction","API Error"]
P2=["conversation was successfully compacted","summary of the content that was discussed","context window","compacted to free up space","transcript file which is accessible"]
c=sqlite3.connect(f'file:{DB}?mode=ro',uri=True); c.row_factory=sqlite3.Row
titles={r['uuid']:r['title'] for r in c.execute("select uuid,title from conversations")}
def esc(s): return s.replace('\r','').replace('\n',' / ').replace('|','\\|')
def ctx(body,pat,width=300):
    i=body.lower().find(pat.lower()); h=width//2
    a=max(0,i-h); b=min(len(body),i+len(pat)+h)
    return ('\u2026' if a>0 else '')+body[a:b]+('\u2026' if b<len(body) else '')

# ---------- 1. classifier flags
where=" OR ".join("lower(body) LIKE ?" for _ in P1)
rows=c.execute(f"SELECT id,conversation_uuid,ordinal,server_time_iso,sender,body FROM messages WHERE {where} ORDER BY conversation_uuid, ordinal",['%'+p.lower()+'%' for p in P1]).fetchall()
flags=collections.OrderedDict()
pat_count=collections.Counter()
for r in rows:
    hit=[p for p in P1 if p.lower() in r['body'].lower()]
    # 'safety classifier' implies 'classifier': keep both listed, count each
    for p in hit: pat_count[p]+=1
    flags.setdefault(r['conversation_uuid'],[]).append((r,hit))
# ---------- 2. compaction events
where2=" OR ".join("lower(body) LIKE ?" for _ in P2)
rows2=c.execute(f"SELECT id,conversation_uuid,ordinal,server_time_iso,sender,body FROM messages WHERE sender='assistant' AND ({where2}) ORDER BY conversation_uuid, ordinal",['%'+p.lower()+'%' for p in P2]).fetchall()
comp=collections.OrderedDict(); pat2=collections.Counter()
def neighbor(cu,ordn,direction):
    if direction<0:
        return c.execute("SELECT ordinal,server_time_iso,body FROM messages WHERE conversation_uuid=? AND sender='human' AND ordinal<? ORDER BY ordinal DESC LIMIT 1",(cu,ordn)).fetchone()
    return c.execute("SELECT ordinal,server_time_iso,body FROM messages WHERE conversation_uuid=? AND sender='human' AND ordinal>? ORDER BY ordinal ASC LIMIT 1",(cu,ordn)).fetchone()
for r in rows2:
    hit=[p for p in P2 if p.lower() in r['body'].lower()]
    for p in hit: pat2[p]+=1
    comp.setdefault(r['conversation_uuid'],[]).append((r,hit,neighbor(r['conversation_uuid'],r['ordinal'],-1),neighbor(r['conversation_uuid'],r['ordinal'],+1)))

both=sorted(set(flags)&set(comp), key=lambda u: titles.get(u,''))
o=[]
o.append("# CLASSIFIER FLAGS AND COMPACTION EVENTS\n")
o.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}  ")
o.append(f"Database: `{DB}` (read-only; the only copy holding the messages table)  ")
o.append(f"Messages scanned: {c.execute('select count(*) from messages').fetchone()[0]:,} across {len(titles)} conversations. Matching is case-insensitive substring.\n")
o.append("## Totals\n")
o.append("| Metric | Value |\n|---|---:|")
o.append(f"| Classifier-flag messages (any sender) | {len(rows)} |")
o.append(f"| Conversations with classifier flags | {len(flags)} |")
o.append(f"| Compaction messages (assistant) | {len(rows2)} |")
o.append(f"| Conversations with compaction events | {len(comp)} |")
o.append(f"| Conversations with BOTH | {len(both)} |\n")
o.append("Hits per pattern (a message can match several):\n")
o.append("| Section | Pattern | Messages |\n|---|---|---:|")
for p in P1: o.append(f"| classifier | `{p}` | {pat_count[p]} |")
for p in P2: o.append(f"| compaction | `{p}` | {pat2[p]} |")
o.append("\nNote: `classifier` and `context window` are ordinary vocabulary in this corpus and account for most hits; the narrower patterns (`flagged by safety`, `safety classifier`, `I need to flag`, `API Error`, `compacted to free up space`) are the ones that mark actual events.\n")
o.append("## Conversations with both classifier flags and compaction events\n")
o.append("\n".join(f"- `{u}` \u2014 {esc(titles.get(u,'?'))} ({len(flags[u])} flags, {len(comp[u])} compactions)" for u in both) or "_none_")
o.append("")

o.append("---\n\n# SECTION 1: CLASSIFIER FLAGS\n")
o.append(f"{len(rows)} messages in {len(flags)} conversations, grouped by conversation (ordered by conversation, then message order).\n")
for cu,items in flags.items():
    o.append(f"## {esc(titles.get(cu,'?'))}\n\n`{cu}` \u2014 {len(items)} hit(s)\n")
    for r,hit in items:
        o.append(f"**{r['server_time_iso']}** \u00b7 {r['sender']} \u00b7 ordinal {r['ordinal']} \u00b7 patterns: {', '.join('`'+p+'`' for p in hit)}\n")
        shown=set()
        for p in hit[:3]:
            snippet=ctx(r['body'],p)
            if snippet in shown: continue
            shown.add(snippet)
            o.append(f"> [{p}] {esc(snippet)}\n")
o.append("---\n\n# SECTION 2: COMPACTION EVENTS\n")
o.append(f"{len(rows2)} assistant messages in {len(comp)} conversations. For each: the human message immediately before (trigger) and immediately after (what resumed).\n")
for cu,items in comp.items():
    o.append(f"## {esc(titles.get(cu,'?'))}\n\n`{cu}` \u2014 {len(items)} event(s)\n")
    for r,hit,prev,nxt in items:
        o.append(f"**{r['server_time_iso']}** \u00b7 assistant \u00b7 ordinal {r['ordinal']} \u00b7 patterns: {', '.join('`'+p+'`' for p in hit)}\n")
        o.append(f"> [assistant] {esc(ctx(r['body'],hit[0]))}\n")
        o.append(f"> **BEFORE** (human, ordinal {prev['ordinal']}, {prev['server_time_iso']}): {esc(prev['body'][:500])}{'\u2026' if len(prev['body'])>500 else ''}\n" if prev else "> **BEFORE**: _no earlier human message in this conversation_\n")
        o.append(f"> **AFTER** (human, ordinal {nxt['ordinal']}, {nxt['server_time_iso']}): {esc(nxt['body'][:500])}{'\u2026' if len(nxt['body'])>500 else ''}\n" if nxt else "> **AFTER**: _no later human message in this conversation_\n")
open(OUT,'w',encoding='utf-8').write("\n".join(o)+"\n")

print(f"wrote {OUT} ({os.path.getsize(OUT):,} bytes)")
print(f"total classifier flags: {len(rows)} messages in {len(flags)} conversations")
print(f"total compactions:      {len(rows2)} messages in {len(comp)} conversations")
print(f"conversations with both: {len(both)}")
for u in both: print(f"  {u}  {titles.get(u,'?')[:70]}  flags={len(flags[u])} compactions={len(comp[u])}")
print("\nnarrow-pattern counts:", {p:pat_count[p] for p in P1 if p not in ('classifier',)}, {p:pat2[p] for p in P2 if p!='context window'})
