#!/usr/bin/env python3
"""Catalog ingestible source files under ~/Desktop/nu/phone into Inbox/phone_sources.db and Inbox/PHONE_SOURCES.md.
Read-only against phone/. Classifies by path and name, hashes, marks duplicates, marks what is already
in the record (hash present in ~/Desktop/nu/MANIFEST.sha256), orders by best known date."""
import os, re, sys, json, sqlite3, hashlib, datetime, collections, time
NU = os.path.expanduser('~/Desktop/nu'); ROOT = NU + '/phone'
DB = NU + '/Inbox/phone_sources.db'; MD = NU + '/Inbox/PHONE_SOURCES.md'
SKIP_DIRS = {'NOT_ryn_memory_api_hack', 'node_modules', 'site-packages', '.git', '__pycache__', 'dist', '.vercel', '.venv', 'venv', 'img_files', '.next', 'build'}
TEXT_EXT = {'.md', '.txt', '.log', '.jsonl', '.json', '.py', '.sh', '.yaml', '.yml', '.csv', '.html', '.sha256', '.ath', '.docx', '.zip', '.tsv', '.doc', '.pdf'}
manifest = set()
for line in open(NU + '/MANIFEST.sha256'):
    h = line.split('  ', 1)[0].strip()
    if len(h) == 64: manifest.add(h)

def sha(p, cap=400 << 20):
    if os.path.getsize(p) > cap: return ''
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

TODAY = datetime.date.today().isoformat()
DATE_RE = [re.compile(r'(20\d{2})[-_]?(\d{2})[-_]?(\d{2})'), re.compile(r'(\d{2})_(\d{2})_(20\d{2})')]
def name_date(name):
    m = DATE_RE[0].search(name)
    if m:
        y, mo, d = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 and f'{y}-{mo}-{d}' <= TODAY: return f'{y}-{mo}-{d}'
    m = DATE_RE[1].search(name)
    if m:
        mo, d, y = m.groups()
        if 1 <= int(mo) <= 12 and 1 <= int(d) <= 31 and f'{y}-{mo}-{d}' <= TODAY: return f'{y}-{mo}-{d}'
    return ''

UUID_RE = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(_clean)?\.jsonl$')
def classify(rel, name, ext):
    low = rel.lower(); n = name.lower()
    if n in ('conversations.json', 'prod-grok-backend.json', 'chat.html', 'gpt_export_raw.json') or re.match(r'conversations-\d+\.(json|zip)$', n) or n.startswith('data-18bd5353') or n.startswith('9b6c3f73') or n.startswith('grok_export') or n == '7d6490b4-6b00-4690-b36d-5098611f41fd.zip':
        return 'export'
    if UUID_RE.match(name) and '/projects/' in low: return 'claude_code_session'
    if re.search(r'quartetdoc|triodoc|duetdoc|quartet_debate|telegram_pre|telegram\.zip|relay_session|relay_conversation|mirrorlog|grok_mirrornode|relay_logs|relay_transcripts|relay_ses|relay_dec|relay_log|claude_and_ryn', low): return 'relay_transcript'
    if low.startswith('documents/markor/'): return 'markor_note'
    if low.startswith('documents/memory/'): return 'memory_note'
    if re.search(r'models_relays/ryn/[^/]+\.(md|txt|yaml)$|sys_preload|preload_', low): return 'ryn_note'
    if re.search(r'cleaned_convos|pass2_canonical|pre_pipeline|convo_splits|chunked_outputs', low) and ext in ('.md','.txt'): return 'conversation_md'
    if re.search(r'_claude_phoenix|grok_selfaudit|grok_native|relay_curator|multivoice|phoenix_recall|v4_output|curator_output|_chunk_\d+\.md|curator_pass\.|curator_\d{8}|fable13/curator|curator/fable13', low): return 'curator_output'
    if re.search(r'signal_|session_handoff|/signal/|signals/', low): return 'signal'
    if n.endswith('skill.md') or n.endswith('.skill.zip') or '/skills/' in low: return 'skill'
    if '/relay/wiki/' in low or '/wiki/' in low: return 'wiki'
    if re.search(r'phoenix_shard|nano_memory|\.ath$|wake_up|soulboot|voiceprint|memory_shard|personality_vectors|voice_pairs|_memory\.(md|jsonl)', low): return 'memory_shard'
    if re.search(r'threadweaver|schemaweaver|chunkweaver|translator_|curator.*\.py|telegram_relay|aethryn_relay|fieldrelay|relay_memory|nano_embed|nano_memory_loader|gaslitai|contamination|sovereign_editor|clx\.py|gptx\.py|grokx\.py|turnspine|chains\.py', low) and ext in ('.py', '.sh'): return 'pipeline_script'
    if re.search(r'manifest|sha256|inventory|checksums|corpus_hashes', low): return 'manifest'
    if re.search(r'work_order|ticket', low): return 'work_order'
    if ext == '.log': return 'log'
    if ext == '.md' and re.search(r'conversation|convo|claude_sovereign|fable13|models_relays/claude|models_relays/grok|models_relays/gpt|claude_export|/raw/', low): return 'conversation_md'
    if re.search(r'/docs/', low) or ext in ('.docx', '.doc', '.pdf'): return 'doc'
    if ext in ('.py', '.sh'): return 'code_other'
    if ext in ('.md', '.txt'): return 'text_other'
    return 'other'
RELEVANT = {'markor_note', 'memory_note', 'ryn_note', 'export', 'claude_code_session', 'relay_transcript', 'curator_output', 'signal', 'skill', 'wiki', 'memory_shard', 'pipeline_script', 'manifest', 'work_order', 'log', 'conversation_md'}

rows = []; t0 = time.time(); n = 0
for dp, dn, fn in os.walk(ROOT):
    dn[:] = sorted(d for d in dn if d not in SKIP_DIRS)
    for f in sorted(fn):
        ext = os.path.splitext(f)[1].lower()
        if ext not in TEXT_EXT: continue
        p = os.path.join(dp, f); rel = os.path.relpath(p, ROOT)
        try: st = os.stat(p)
        except OSError: continue
        cat = classify(rel, f, ext)
        if cat in ('other',) and ext in ('.json', '.html', '.csv', '.zip', '.yaml', '.yml', '.tsv'): continue
        h = sha(p) if (cat in RELEVANT or st.st_size < 50 << 20) else ''
        nd = name_date(f) or name_date(os.path.basename(dp))
        rows.append(dict(rel=rel, name=f, ext=ext, size=st.st_size, mtime=datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%dT%H:%M:%S'),
                         name_date=nd, sha256=h, category=cat, relevant=int(cat in RELEVANT), in_record=int(bool(h) and h in manifest)))
        n += 1
        if n % 2000 == 0: print(f'  {n} files, {time.time()-t0:.0f}s', file=sys.stderr)
for r in rows: r['best_date'] = r['name_date'] or r['mtime'][:10]
first = {}
for r in sorted(rows, key=lambda r: (r['best_date'], r['rel'])):
    if r['sha256'] and r['sha256'] in first and first[r['sha256']] != r['rel']: r['dup_of'] = first[r['sha256']]
    else:
        r['dup_of'] = ''
        if r['sha256']: first.setdefault(r['sha256'], r['rel'])
for r in rows: r['needed'] = int(r['relevant'] and not r['in_record'] and not r['dup_of'])

if os.path.exists(DB): os.remove(DB)
c = sqlite3.connect(DB)
c.execute('''CREATE TABLE files (rel TEXT PRIMARY KEY, name TEXT, ext TEXT, size INTEGER, mtime TEXT, name_date TEXT, best_date TEXT,
             sha256 TEXT, category TEXT, relevant INTEGER, in_record INTEGER, dup_of TEXT, needed INTEGER)''')
c.executemany('INSERT INTO files VALUES (:rel,:name,:ext,:size,:mtime,:name_date,:best_date,:sha256,:category,:relevant,:in_record,:dup_of,:needed)', rows)
c.execute('CREATE INDEX ix_cat ON files(category)'); c.execute('CREATE INDEX ix_date ON files(best_date)'); c.execute('CREATE INDEX ix_sha ON files(sha256)')
c.execute('CREATE TABLE meta (key TEXT, value TEXT)')
c.executemany('INSERT INTO meta VALUES (?,?)', [('root', ROOT), ('built', datetime.datetime.now().isoformat(timespec='seconds')), ('record_manifest', NU + '/MANIFEST.sha256'), ('record_hashes', str(len(manifest))),
                                              ('note', 'best_date = date parsed from filename or parent dir when present, else file mtime. The phone backup preserves mtimes from the phone, not creation times.')])
c.commit()

# ---- markdown reference
cats = collections.OrderedDict()
for r in rows: cats.setdefault(r['category'], []).append(r)
order = ['export', 'claude_code_session', 'relay_transcript', 'markor_note', 'memory_note', 'ryn_note', 'conversation_md', 'curator_output', 'memory_shard', 'signal', 'wiki', 'skill', 'pipeline_script', 'work_order', 'manifest', 'log', 'doc', 'text_other', 'code_other', 'other']
def hb(n): return f'{n/1048576:.1f} MB' if n >= 1048576 else f'{n/1024:.0f} KB'
out = ['# PHONE SOURCES -- what is there, what is needed, where it is', '',
       f'Built {datetime.datetime.now().isoformat(timespec="seconds")} from ~/Desktop/nu/phone (read-only). Database: Inbox/phone_sources.db, table files.',
       'Excluded by Mike\'s instruction 2026-09-13: any directory named NOT_ryn_memory_api_hack.',
       'Scope: text and document files (md, txt, log, jsonl, json, py, sh, yaml, csv, html, sha256, ath, docx, pdf, zip), skipping node_modules, site-packages, .git, venvs, and the grafana image tree.',
       '"In record" means the sha256 already appears in ~/Desktop/nu/MANIFEST.sha256, which covers curator/, curator_pass/, and backup/. "Dup" means an identical file appears earlier in this same listing.',
       '"Needed" = relevant category, not in record, first copy. Dates: parsed from the filename or parent directory when present, else the file mtime carried over from the phone.', '']
out.append('## Summary by category'); out.append('')
out.append('| Category | Files | Unique | In record | Needed | Bytes |'); out.append('|---|---:|---:|---:|---:|---:|')
for cat in order:
    L = cats.get(cat, [])
    if not L: continue
    out.append(f'| {cat} | {len(L)} | {sum(1 for r in L if not r["dup_of"])} | {sum(r["in_record"] for r in L)} | {sum(r["needed"] for r in L)} | {hb(sum(r["size"] for r in L))} |')
out.append(f'| total | {len(rows)} | {sum(1 for r in rows if not r["dup_of"])} | {sum(r["in_record"] for r in rows)} | {sum(r["needed"] for r in rows)} | {hb(sum(r["size"] for r in rows))} |'); out.append('')
out.append('## Needed files by category, ordered by date'); out.append('')
out.append('Only files marked needed are listed here. Duplicates and files already in the record are in the database.'); out.append('')
for cat in order:
    L = [r for r in cats.get(cat, []) if r['needed']]
    if not L or cat in ('doc', 'text_other', 'code_other', 'other'): continue
    out.append(f'### {cat} ({len(L)} needed)'); out.append('')
    out.append('| Date | Size | sha256 | Path |'); out.append('|---|---:|---|---|')
    for r in sorted(L, key=lambda r: (r['best_date'], r['rel'])):
        out.append(f'| {r["best_date"]} | {hb(r["size"])} | {r["sha256"][:12]} | `{r["rel"]}` |')
    out.append('')
out.append('## Timeline of needed sources (all categories, by date)'); out.append('')
out.append('| Date | Category | Size | Path |'); out.append('|---|---|---:|---|')
for r in sorted([r for r in rows if r['needed'] and r['category'] not in ('doc', 'text_other', 'code_other', 'other')], key=lambda r: (r['best_date'], r['rel'])):
    out.append(f'| {r["best_date"]} | {r["category"]} | {hb(r["size"])} | `{r["rel"]}` |')
out.append('')
open(MD, 'w', encoding='ascii', errors='replace').write('\n'.join(out) + '\n')
print(f'files cataloged: {len(rows)}  unique: {sum(1 for r in rows if not r["dup_of"])}  in_record: {sum(r["in_record"] for r in rows)}  needed: {sum(r["needed"] for r in rows)}')
for cat in order:
    L = cats.get(cat, [])
    if L: print(f'  {cat:20s} files={len(L):5d} unique={sum(1 for r in L if not r["dup_of"]):5d} in_record={sum(r["in_record"] for r in L):5d} needed={sum(r["needed"] for r in L):5d}  {hb(sum(r["size"] for r in L))}')
print('wrote', DB, 'and', MD, f'({os.path.getsize(MD):,} bytes)')
