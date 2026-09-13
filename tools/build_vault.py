#!/usr/bin/env python3
"""build_vault.py -- build ~/Desktop/nu wiki from the cataloged sources, verbatim, per CLAUDE.md.

Phases (run in order; state persists in scratch/vault_state.json):
  transcripts   speaker-labelled relay chats (markor telegram files, relay transcripts)
  notes         markor/memory/ryn notes, signals, work orders, wiki, skills, scripts, curator outputs, logs, shards
  claude        Claude export 2026-09-12 (canonical), plus superseded Claude exports as uuid tables + any conversation absent from canonical
  gpt           GPT export 2026-08-05 (canonical), plus superseded GPT exports likewise
  grok          Grok export 2026-01-06
  sessions      Claude Code session logs (jsonl)
  finish        entity/concept pages, group indexes, Index.md
Rules applied: no omission, no paraphrase, ASCII with \\uXXXX escapes, stated mechanical selection only.
Sources over RAW_COPY_MAX bytes get a provenance record instead of a copy; sources over READ_MAX bytes that are not
conversation exports get a provenance record and no Reading (stated in the log)."""
import os, re, sys, json, sqlite3, hashlib, datetime, collections, unicodedata, glob, zipfile, io

NU = os.path.expanduser('~/Desktop/nu'); PH = NU + '/phone'
SCR = '/tmp/claude-1000/-home-mike-Desktop-nu-curator-pass/83a15ca4-15db-459e-8771-7ccbca37328a/scratchpad'
STATE = SCR + '/vault_state.json'
TODAY = datetime.date.today().isoformat()
PART_LINES = 1200; RAW_COPY_MAX = 5 << 20; READ_MAX = 5 << 20
MENTION_NAMES = ['Mike', 'Grok', 'GPT', 'ChatGPT', 'Claude', 'Ryn', 'Willow', 'Madmartigan', 'Aethryn', 'Clubhouse', 'Ollama', 'Jetson', 'Telegram',
                 'Anthropic', 'OpenAI', 'xAI', 'Threadweaver', 'Schemaweaver', 'Nano', 'relay', 'curator', 'classifier', 'anticognitarianism',
                 'Sanctuary', 'Edge-Walker', 'Architect', 'Steward', 'Librarian', 'Operator', 'Sentinel', 'Logos', 'Ember', 'Carbon', 'POS']
MENTION_RE = {n: re.compile(r'\b%s\b' % re.escape(n), re.I) for n in MENTION_NAMES}
CURATOR_TAGS = ['CONFRONTATION', 'EXPERIENTIAL', 'RESONANCE', 'CONVERGENCE', 'DIVERGENCE', 'RELAY_WORKING', 'RELAY_FAILING', 'DEFLECTION', 'NULL', 'AMPLIFICATION', 'CONFABULATION', 'SOLID', 'PLAUSIBLE', 'REACHING', 'BULLSHIT']
TAG_RE = {t: re.compile(r'\[%s[^\]]*\]' % t) for t in CURATOR_TAGS}

def asc(s):
    out = []
    for ch in str(s):
        o = ord(ch)
        out.append(ch if o < 128 else ('\\u%04x' % o if o < 0x10000 else '\\U%08x' % o))
    return ''.join(out)
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def slug(s): return re.sub(r'[^A-Za-z0-9 _.-]+', '', s).strip().strip('.')[:120]
def now(): return datetime.datetime.now().isoformat(timespec='seconds')
def wr(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, 'w', encoding='ascii').write(text if text.endswith('\n') else text + '\n')
def fm(**kw):
    L = ['---']
    for k, v in kw.items():
        if isinstance(v, list): L.append('%s: [%s]' % (k, ', '.join('"%s"' % asc(x) for x in v)))
        else: L.append('%s: %s' % (k, asc(v)))
    L.append('---'); return L
def gate_report(text):
    g = collections.Counter(ch for ch in text if ord(ch) > 127)
    L = ['Gate findings: %d characters outside the whitelist, %d distinct codepoints. Escaped as \\uXXXX in the vault; the source bytes are unchanged.' % (sum(g.values()), len(g))]
    for ch, n in g.most_common(10): L.append('  U+%04X %s x%d' % (ord(ch), unicodedata.name(ch, '(no assigned name)'), n))
    return L, sum(g.values()), len(g)

# ---------------------------------------------------------------- state
state = json.load(open(STATE)) if os.path.exists(STATE) else {'occ': {}, 'tagocc': {}, 'groups': {}, 'done': [], 'log': []}
def occ(name, source_title, reading, mid, line, first):
    state['occ'].setdefault(name, {}).setdefault(source_title, []).append([reading, mid, int(line), first[:140]])
def tagocc(tag, source_title, reading, mid, line, first):
    state['tagocc'].setdefault(tag, {}).setdefault(source_title, []).append([reading, mid, int(line), first[:140]])
def group_add(group, line):
    state['groups'].setdefault(group, [])
    if line not in state['groups'][group]: state['groups'][group].append(line)
def log(entry): state['log'].append(entry); open(NU + '/Wiki/Log.md', 'a', encoding='ascii').write('\n' + entry + '\n')
def save_state(): json.dump(state, open(STATE, 'w'))

# ---------------------------------------------------------------- raw provenance
def raw_page(src, title, tags, text=None, copy=True, extra=None):
    """Write Raw/R - <title>.md. Returns (raw_name, digest, size)."""
    digest = sha(src); size = os.path.getsize(src); rel = os.path.relpath(src, NU)
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(src)).isoformat(timespec='seconds')
    name = 'R - %s' % slug(title)
    L = fm(type='raw', created=TODAY, updated=TODAY, tags=['raw'] + tags, source_path=rel, source_sha256=digest, source_bytes=size, source_mtime=mtime)
    L += ['', '# %s' % name, '', 'Provenance record for %s.' % rel, '']
    if extra: L += extra + ['']
    if copy and text is not None:
        g, gn, gd = gate_report(text)
        L += g + ['', 'Verbatim copy follows. Characters outside the 98-character whitelist are written as \\uXXXX escapes; nothing else is changed. Line numbers match the source.', '', '---', ''] + [asc(l) for l in text.split('\n')]
    else:
        L += ['Not copied: %s bytes. The source stays at the path above and is identified by its sha256. Readings for it, if any, are listed in the Index.' % '{:,}'.format(size)]
    wr(NU + '/Raw/%s.md' % name, '\n'.join(L)); return name, digest, size

# ---------------------------------------------------------------- reading writer (generic units)
def write_reading(title, group, raw_name, digest, units, tags, unit_kind='turn', note=''):
    """units: list of dict(id, line, head, text_lines). Splits into parts at unit boundaries. Returns [(part_name, [unit ids])]."""
    parts = []; buf = []; n = 0
    for u in units:
        tl = len(u['text']) + 2
        if buf and n + tl > PART_LINES: parts.append(buf); buf = []; n = 0
        buf.append(u); n += tl
    if buf: parts.append(buf)
    M = len(parts) or 1
    if not parts: parts = [[]]
    def pn(i): return 'Read - %s (part %02d of %02d)' % (slug(title), i, M) if M > 1 else 'Read - %s' % slug(title)
    out = []
    for i, P in enumerate(parts, 1):
        L = fm(type='reading', created=TODAY, updated=TODAY, tags=['reading'] + tags, sources=[raw_name], part=i, parts=M, source_sha256=digest,
               units='%s to %s' % (P[0]['id'], P[-1]['id']) if P else 'none')
        L += ['', '# %s' % pn(i), '', 'Source: [[%s]] (sha256 %s). Every %s in this range is present in full. Headers are added structure only: %s id, source position, and the fields named in the header.%s' % (raw_name, digest[:16], unit_kind, unit_kind, (' ' + note) if note else ''), '',
              ('Previous: [[%s]]' % pn(i - 1) if i > 1 else '') + ('  Next: [[%s]]' % pn(i + 1) if i < M else ''), '']
        for u in P:
            L.append('### %s %s' % (u['id'], asc(u['head']))); L.append(''); L += [asc(x) for x in u['text']]; L.append('')
        wr(NU + '/Wiki/Readings/%s.md' % pn(i), '\n'.join(L)); out.append((pn(i), [u['id'] for u in P]))
        group_add(group, '- [[%s]] -- %s, %s %s to %s' % (pn(i), slug(title), unit_kind + 's', P[0]['id'] if P else '-', P[-1]['id'] if P else '-'))
    return out

def mentions(units, parts, source_title, per_unit=True):
    """Entity occurrences: per unit line (transcripts/notes) or per source line with unit ids (exports)."""
    part_of = {}
    for pn, ids in parts:
        for i in ids: part_of[i] = pn
    hits = collections.defaultdict(list)
    for u in units:
        txt = '\n'.join(u['text'])
        for name, rx in MENTION_RE.items():
            if rx.search(txt): hits[name].append(u)
        for tag, rx in TAG_RE.items():
            if rx.search(txt): tagocc(tag, source_title, part_of[u['id']], u['id'], u['line'], asc(next((l.strip() for l in u['text'] if l.strip()), '')))
    for name, L in hits.items():
        if per_unit:
            for u in L: occ(name, source_title, part_of[u['id']], u['id'], u['line'], asc(next((l.strip() for l in u['text'] if l.strip()), '')))
        else:
            by_part = collections.defaultdict(list)
            for u in L: by_part[part_of[u['id']]].append(u['id'])
            for pn, ids in by_part.items(): occ(name, source_title, pn, '%d units: %s' % (len(ids), ' '.join(ids)), L[0]['line'], '')

# ---------------------------------------------------------------- 1. transcripts
SPEAKERS = ['Mike', 'Clubhouse', 'You said', 'ChatGPT said', 'Grok', 'GPT', 'Ryn', 'Claude', 'Local', 'Nano', 'You', 'Willow', 'Madmartigan', 'Human', 'Assistant', 'User', 'Operator', 'Builder', 'Librarian', 'Designer', 'Sentinel']
SPEAKER_RE = re.compile(r'^\**(%s)\**:\s*$' % '|'.join(re.escape(x) for x in SPEAKERS))
SUB_RE = re.compile(r'^(?:[^\x00-\x7F]\s*)?(Grok|GPT|Local|Ryn|Claude|Nano|Quartet|Trio)\s*:\s*$')
CMD_RE = re.compile(r'^/([a-z_]+)')
def parse_turns(lines):
    turns = []; cur = None
    for i, ln in enumerate(lines, 1):
        m = SPEAKER_RE.match(ln)
        if m:
            if cur: turns.append(cur)
            cur = dict(line=i, speaker=m.group(1), sub='', cmd='', text=[]); continue
        if cur is None: cur = dict(line=i, speaker='(preamble)', sub='', cmd='', text=[])
        sm = SUB_RE.match(ln)
        if sm and cur['speaker'] == 'Clubhouse' and not cur['text']: cur['sub'] = sm.group(1); cur['text'].append(ln); continue
        if not cur['text'] and not cur['cmd']:
            cm = CMD_RE.match(ln.strip())
            if cm: cur['cmd'] = cm.group(1)
        cur['text'].append(ln)
    if cur: turns.append(cur)
    for k, t in enumerate(turns, 1): t['id'] = 'T%04d' % k
    return turns
def ingest_transcript(src, title, tags, group):
    text = open(src, encoding='utf-8', errors='replace').read(); lines = text.split('\n')
    turns = parse_turns(lines)
    if sum(1 for t in turns if t['speaker'] != '(preamble)') < 5: return ingest_text(src, title, tags, group)   # not really speaker-labelled
    raw_name, digest, size = raw_page(src, title, tags, text=text, copy=size_ok(src))
    units = [dict(id=t['id'], line=t['line'], head='L%05d %s' % (t['line'], t['speaker'] + ((' / ' + t['sub']) if t['sub'] else '') + ((' /' + t['cmd']) if t['cmd'] else '')), text=t['text']) for t in turns]
    parts = write_reading(title, group, raw_name, digest, units, tags, 'turn')
    part_of = {i: pn for pn, ids in parts for i in ids}
    for t in turns:
        if t['speaker'] == '(preamble)': continue
        first = asc(next((l.strip() for l in t['text'] if l.strip() and not SUB_RE.match(l)), ''))
        occ(t['speaker'], title, part_of[t['id']], t['id'], t['line'], first)
        if t['sub']: occ(t['sub'], title, part_of[t['id']], t['id'], t['line'], first)
        if t['cmd']: state['occ'].setdefault('cmd:' + t['cmd'], {}).setdefault(title, []).append([part_of[t['id']], t['id'], t['line'], first])
    mentions(units, parts, title)
    log('## %s ingest %s\n\n- transcript, sha256 %s, %d bytes, %d lines, %d turns, %d Reading parts\n- speakers: %s' % (now(), os.path.relpath(src, NU), digest, size, len(lines), len(turns), len(parts), ', '.join('%s %d' % (k, v) for k, v in collections.Counter(t['speaker'] for t in turns).most_common())))
    return True

def size_ok(src): return os.path.getsize(src) <= RAW_COPY_MAX

# ---------------------------------------------------------------- 2. generic text / jsonl / json notes
def ingest_text(src, title, tags, group):
    size = os.path.getsize(src)
    if size > READ_MAX:
        raw_name, digest, _ = raw_page(src, title, tags, copy=False, extra=['Over %d MB: provenance record only, no Reading. Rule stated in CLAUDE.md build log. The file is indexed in Inbox/phone_sources.db.' % (READ_MAX >> 20)])
        group_add(group, '- [[%s]] -- provenance only, %s bytes' % (raw_name, '{:,}'.format(size)))
        log('## %s record %s\n\n- provenance only (%s bytes over the %d MB Reading limit), sha256 %s' % (now(), os.path.relpath(src, NU), '{:,}'.format(size), READ_MAX >> 20, digest)); return True
    ext = os.path.splitext(src)[1].lower()
    if ext in ('.docx', '.pdf', '.zip', '.doc'):
        raw_name, digest, _ = raw_page(src, title, tags, copy=False, extra=['Binary container (%s): provenance record only. Members or text are not extracted by this pass.' % ext])
        group_add(group, '- [[%s]] -- binary, provenance only' % raw_name)
        log('## %s record %s\n\n- binary container, provenance only, sha256 %s' % (now(), os.path.relpath(src, NU), digest)); return True
    text = open(src, encoding='utf-8', errors='replace').read(); lines = text.split('\n')
    raw_name, digest, _ = raw_page(src, title, tags, text=text, copy=True)
    units = []
    if ext == '.jsonl':
        for i, ln in enumerate(lines, 1):
            if not ln.strip(): continue
            try:
                rec = json.loads(ln); keep = {k: v for k, v in rec.items() if not (k == 'embedding' and isinstance(v, list))}
                emb = ' embedding: %d floats, in source only' % len(rec['embedding']) if 'embedding' in rec and isinstance(rec['embedding'], list) else ''
                units.append(dict(id='J%05d' % i, line=i, head='L%05d record%s' % (i, emb), text=json.dumps(keep, ensure_ascii=True, indent=1).split('\n')))
            except Exception:
                units.append(dict(id='J%05d' % i, line=i, head='L%05d (unparsed line)' % i, text=[ln]))
        note = 'JSONL: one unit per record, fields verbatim; embedding vectors are left in the source file and their length is noted.'
    else:
        # blocks separated by blank lines keep paragraph structure; ids by first line number
        blk = []; start = 1
        for i, ln in enumerate(lines, 1):
            if ln.strip() == '' and blk:
                units.append(dict(id='B%05d' % start, line=start, head='L%05d' % start, text=blk)); blk = []; start = i + 1
            elif ln.strip() == '': start = i + 1
            else: blk.append(ln)
        if blk: units.append(dict(id='B%05d' % start, line=start, head='L%05d' % start, text=blk))
        note = 'Text: one unit per paragraph (blank-line separated), verbatim.'
    if not units: units = [dict(id='B00001', line=1, head='L00001 (empty file)', text=[''])]
    parts = write_reading(title, group, raw_name, digest, units, tags, 'unit', note)
    mentions(units, parts, title)
    log('## %s ingest %s\n\n- %s, sha256 %s, %d lines, %d units, %d Reading parts' % (now(), os.path.relpath(src, NU), ext.lstrip('.') or 'text', digest, len(lines), len(units), len(parts))); return True

# ---------------------------------------------------------------- 3. Claude export
def claude_msg_units(conv):
    units = []
    for k, m in enumerate(sorted(conv['chat_messages'], key=lambda x: x['created_at']), 1):
        text = []
        blocks = m.get('content') or []
        joined = []
        for b in blocks:
            bt = b.get('type')
            if bt == 'text': text.append(b.get('text') or ''); joined.append(b.get('text') or '')
            elif bt == 'thinking': text.append('[thinking%s]' % (' truncated' if b.get('truncated') else '')); text.append(b.get('thinking') or '')
            elif bt == 'tool_use': text.append('[tool_use %s] %s' % (b.get('name'), json.dumps(b.get('input'), ensure_ascii=True)))
            elif bt == 'tool_result': text.append('[tool_result %s%s] %s' % (b.get('name'), ' error' if b.get('is_error') else '', json.dumps(b.get('content'), ensure_ascii=True)))
            else: text.append('[%s] %s' % (bt, json.dumps({x: y for x, y in b.items() if x != 'type'}, ensure_ascii=True)))
            if b.get('citations'): text.append('[citations] %s' % json.dumps(b['citations'], ensure_ascii=True))
        tf = (m.get('text') or '')
        if tf.strip() and tf.strip() != '\n'.join(joined).strip(): text.append('[text field]'); text.append(tf)
        if m.get('attachments'): text.append('[attachments] %s' % json.dumps(m['attachments'], ensure_ascii=True))
        if m.get('files'): text.append('[files] %s' % json.dumps(m['files'], ensure_ascii=True))
        lines = '\n'.join(text).split('\n')
        units.append(dict(id='M%04d' % k, line=k, head='%s %s uuid %s%s' % (m['created_at'], m['sender'], m['uuid'], (' updated %s' % m['updated_at']) if m.get('updated_at') != m.get('created_at') else ''), text=lines))
    return units
def conv_title(c): return '%s %s %s' % (c['created_at'][:10], c['uuid'][:8], (c.get('name') or '(untitled)'))
def ingest_claude(path, label, group, canonical_uuids=None):
    d = json.load(open(path, encoding='utf-8')); digest = sha(path); size = os.path.getsize(path)
    raw_name, _, _ = raw_page(path, label, ['export', 'claude'], copy=False, extra=['Claude data export: %d conversations, %d messages. Rendered one Reading per conversation (see the group index) when canonical; superseded exports get a uuid table and full Readings only for conversations absent from the canonical export.' % (len(d), sum(len(c['chat_messages']) for c in d))])
    convs = sorted(d, key=lambda c: c['created_at'])
    table = ['| # | uuid | created | updated | messages | title | in canonical |', '|---:|---|---|---|---:|---|---|']
    rendered = 0
    for i, c in enumerate(convs, 1):
        incanon = (canonical_uuids is None) or (c['uuid'] in canonical_uuids)
        table.append('| %d | %s | %s | %s | %d | %s | %s |' % (i, c['uuid'], c['created_at'][:19], c['updated_at'][:19], len(c['chat_messages']), asc(c.get('name') or '(untitled)').replace('|', '\\|'), 'yes' if (canonical_uuids and c['uuid'] in canonical_uuids) else ('canonical' if canonical_uuids is None else 'NO')))
        if canonical_uuids is None or not incanon:
            units = claude_msg_units(c); t = conv_title(c)
            parts = write_reading(t, group, raw_name, digest, units, ['export', 'claude', 'conversation'], 'message', 'Message order is by created_at. Content blocks are rendered in order: text verbatim; thinking, tool_use, tool_result, flag, injected_prompt_block, token_budget as labelled JSON. The message text field is added when it differs from the text blocks.')
            mentions(units, parts, t, per_unit=False); rendered += 1
    tname = 'Read - %s uuid table' % slug(label)
    wr(NU + '/Wiki/Readings/%s.md' % tname, '\n'.join(fm(type='reading', created=TODAY, updated=TODAY, tags=['reading', 'export', 'claude', 'uuid-table'], sources=[raw_name], source_sha256=digest) + ['', '# %s' % tname, '', 'Every conversation in the export, in created_at order. Rule: mechanical listing of the export file; nothing selected.', ''] + table))
    group_add(group, '- [[%s]] -- %d conversations' % (tname, len(convs)))
    log('## %s ingest %s\n\n- Claude export, sha256 %s, %s bytes, %d conversations, %d rendered in full, uuid table written' % (now(), os.path.relpath(path, NU), digest, '{:,}'.format(size), len(convs), rendered))
    return {c['uuid'] for c in convs}

# ---------------------------------------------------------------- 4. GPT export
def ep(t):
    try: return datetime.datetime.fromtimestamp(float(t), datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception: return str(t)
def gpt_units(c):
    nodes = [v for v in c['mapping'].values() if v.get('message')]
    nodes.sort(key=lambda v: (v['message'].get('create_time') or 0, v['id']))
    units = []
    for k, v in enumerate(nodes, 1):
        m = v['message']; ct = m['content']; text = []
        if ct.get('content_type') in ('text', 'multimodal_text'):
            for p in ct.get('parts') or []:
                text.append(p if isinstance(p, str) else '[part] ' + json.dumps(p, ensure_ascii=True))
        else: text.append('[%s] %s' % (ct.get('content_type'), json.dumps({x: y for x, y in ct.items() if x != 'content_type'}, ensure_ascii=True)))
        md = m.get('metadata') or {}
        keep = {x: md[x] for x in ('model_slug', 'is_visually_hidden_from_conversation', 'finish_details', 'attachments', 'citations') if x in md}
        if keep: text.append('[metadata] ' + json.dumps(keep, ensure_ascii=True))
        units.append(dict(id='M%04d' % k, line=k, head='%s %s%s node %s parent %s' % (ep(m.get('create_time')) if m.get('create_time') else '(no time)', m['author']['role'], (' ' + m['author']['name']) if m['author'].get('name') else '', v['id'][:8], (v.get('parent') or '-')[:8]), text='\n'.join(text).split('\n')))
    return units
def gpt_title(c): return '%s %s %s' % (ep(c.get('create_time'))[:10], (c.get('id') or c.get('conversation_id'))[:8], c.get('title') or '(untitled)')
def ingest_gpt(paths, label, group, canonical_ids=None):
    convs = []; digests = []
    for p in paths:
        convs += json.load(open(p, encoding='utf-8')); digests.append((os.path.relpath(p, NU), sha(p), os.path.getsize(p)))
    raw_name = 'R - %s' % slug(label)
    wr(NU + '/Raw/%s.md' % raw_name, '\n'.join(fm(type='raw', created=TODAY, updated=TODAY, tags=['raw', 'export', 'gpt']) + ['', '# %s' % raw_name, '', 'GPT data export, %d conversations across %d file(s). Provenance per file:' % (len(convs), len(paths)), ''] + ['- %s sha256 %s (%s bytes)' % (r, h, '{:,}'.format(s)) for r, h, s in digests]))
    convs.sort(key=lambda c: c.get('create_time') or 0)
    table = ['| # | id | created | updated | messages | title | in canonical |', '|---:|---|---|---|---:|---|---|']; rendered = 0
    for i, c in enumerate(convs, 1):
        cid = c.get('id') or c.get('conversation_id'); n = sum(1 for v in c['mapping'].values() if v.get('message'))
        incanon = (canonical_ids is None) or (cid in canonical_ids)
        table.append('| %d | %s | %s | %s | %d | %s | %s |' % (i, cid, ep(c.get('create_time'))[:19], ep(c.get('update_time'))[:19], n, asc(c.get('title') or '(untitled)').replace('|', '\\|'), 'yes' if (canonical_ids and cid in canonical_ids) else ('canonical' if canonical_ids is None else 'NO')))
        if canonical_ids is None or not incanon:
            units = gpt_units(c); t = gpt_title(c)
            parts = write_reading(t, group, raw_name, digests[0][1], units, ['export', 'gpt', 'conversation'], 'message', 'All mapping nodes with a message, ordered by create_time; branches included. Parts rendered verbatim; non-text content types as labelled JSON.')
            mentions(units, parts, t, per_unit=False); rendered += 1
    tname = 'Read - %s uuid table' % slug(label)
    wr(NU + '/Wiki/Readings/%s.md' % tname, '\n'.join(fm(type='reading', created=TODAY, updated=TODAY, tags=['reading', 'export', 'gpt', 'uuid-table'], sources=[raw_name]) + ['', '# %s' % tname, '', 'Every conversation in the export in create_time order. Mechanical listing.', ''] + table))
    group_add(group, '- [[%s]] -- %d conversations' % (tname, len(convs)))
    log('## %s ingest %s\n\n- GPT export, %d conversations, %d rendered in full, files: %s' % (now(), label, len(convs), rendered, '; '.join('%s %s' % (r, h[:16]) for r, h, s in digests)))
    return {(c.get('id') or c.get('conversation_id')) for c in convs}

# ---------------------------------------------------------------- 5. Grok export
def grok_time(v):
    try: return datetime.datetime.fromtimestamp(int(v['$date']['$numberLong']) / 1000, datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    except Exception: return str(v)[:19]
def ingest_grok(path, label, group):
    g = json.load(open(path, encoding='utf-8')); digest = sha(path)
    raw_name, _, _ = raw_page(path, label, ['export', 'grok'], copy=False, extra=['Grok data export (prod-grok-backend.json): %d conversations. One Reading per conversation.' % len(g['conversations'])])
    convs = sorted(g['conversations'], key=lambda c: grok_time(c['conversation'].get('create_time')))
    table = ['| # | id | created | modified | responses | title |', '|---:|---|---|---|---:|---|']
    for i, c in enumerate(convs, 1):
        meta = c['conversation']; rs = sorted(c['responses'], key=lambda r: grok_time(r['response'].get('create_time')))
        table.append('| %d | %s | %s | %s | %d | %s |' % (i, meta['id'], grok_time(meta.get('create_time'))[:19], grok_time(meta.get('modify_time'))[:19], len(rs), asc(meta.get('title') or '(untitled)').replace('|', '\\|')))
        units = []
        for k, r in enumerate(rs, 1):
            rr = r['response']; text = [rr.get('message') or '']
            if rr.get('file_attachments'): text.append('[file_attachments] ' + json.dumps(rr['file_attachments'], ensure_ascii=True))
            if r.get('share_link'): text.append('[share_link] ' + json.dumps(r['share_link'], ensure_ascii=True))
            units.append(dict(id='M%04d' % k, line=k, head='%s %s model %s id %s' % (grok_time(rr.get('create_time')), rr.get('sender'), rr.get('model'), rr.get('_id', '')[:8]), text='\n'.join(text).split('\n')))
        t = '%s %s %s' % (grok_time(meta.get('create_time'))[:10], meta['id'][:8], meta.get('title') or '(untitled)')
        parts = write_reading(t, group, raw_name, digest, units, ['export', 'grok', 'conversation'], 'message', 'Responses ordered by create_time. Message text verbatim; attachments and share links as labelled JSON. Summary field of the conversation record: ' + asc(json.dumps(meta.get('summary') or '', ensure_ascii=True)))
        mentions(units, parts, t, per_unit=False)
    tname = 'Read - %s uuid table' % slug(label)
    wr(NU + '/Wiki/Readings/%s.md' % tname, '\n'.join(fm(type='reading', created=TODAY, updated=TODAY, tags=['reading', 'export', 'grok', 'uuid-table'], sources=[raw_name], source_sha256=digest) + ['', '# %s' % tname, '', 'Every conversation in the export in create_time order. Mechanical listing.', ''] + table))
    group_add(group, '- [[%s]] -- %d conversations' % (tname, len(convs)))
    log('## %s ingest %s\n\n- Grok export, sha256 %s, %d conversations rendered in full' % (now(), os.path.relpath(path, NU), digest, len(convs)))

# ---------------------------------------------------------------- 6. Claude Code sessions
def ingest_session(path, title, group):
    lines = open(path, encoding='utf-8', errors='replace').read().split('\n'); digest = sha(path); size = os.path.getsize(path)
    raw_name, _, _ = raw_page(path, title, ['claude-code', 'session'], copy=False, extra=['Claude Code session log (JSONL), %d lines. Rendered one unit per line with the fields verbatim; file-history snapshots and system records as labelled JSON.' % len(lines)])
    units = []
    for i, ln in enumerate(lines, 1):
        if not ln.strip(): continue
        try: j = json.loads(ln)
        except Exception: units.append(dict(id='E%05d' % i, line=i, head='L%05d (unparsed)' % i, text=[ln])); continue
        typ = j.get('type'); ts = j.get('timestamp', ''); text = []
        if typ in ('user', 'assistant') and isinstance(j.get('message'), dict):
            m = j['message']; content = m.get('content')
            if isinstance(content, str): text.append(content)
            else:
                for b in content or []:
                    bt = b.get('type')
                    if bt == 'text': text.append(b.get('text') or '')
                    elif bt == 'thinking': text.append('[thinking]'); text.append(b.get('thinking') or '')
                    elif bt == 'tool_use': text.append('[tool_use %s] %s' % (b.get('name'), json.dumps(b.get('input'), ensure_ascii=True)))
                    elif bt == 'tool_result': text.append('[tool_result%s] %s' % (' error' if b.get('is_error') else '', json.dumps(b.get('content'), ensure_ascii=True)))
                    else: text.append('[%s] %s' % (bt, json.dumps({x: y for x, y in b.items() if x != 'type'}, ensure_ascii=True)))
            extra = {x: j[x] for x in ('cwd', 'gitBranch', 'isSidechain', 'permissionMode', 'uuid', 'parentUuid', 'requestId') if x in j}
            if m.get('model'): extra['model'] = m['model']
            if m.get('usage'): extra['usage'] = m['usage']
            text.append('[fields] ' + json.dumps(extra, ensure_ascii=True))
            head = '%s %s' % (ts, typ)
        else:
            text.append(json.dumps({x: y for x, y in j.items() if x != 'type'}, ensure_ascii=True)); head = '%s %s' % (ts, typ)
        units.append(dict(id='E%05d' % i, line=i, head=head, text='\n'.join(text).split('\n')))
    parts = write_reading(title, group, raw_name, digest, units, ['claude-code', 'session'], 'event')
    mentions(units, parts, title, per_unit=False)
    log('## %s ingest %s\n\n- Claude Code session, sha256 %s, %s bytes, %d events, %d Reading parts' % (now(), os.path.relpath(path, NU), digest, '{:,}'.format(size), len(units), len(parts)))

# ---------------------------------------------------------------- 7. finish: entity/concept pages and indexes
def finish():
    ent = NU + '/Wiki/Entities'; con = NU + '/Wiki/Concepts'
    written = []
    for name, srcs in sorted(state['occ'].items()):
        if name.startswith('cmd:'):
            pth = con + '/Relay command %s.md' % name[4:]; disp = 'Relay command /%s' % name[4:]; kind = 'concept'; rule = 'Rule: every turn whose first non-empty line begins with "/%s".' % name[4:]; tags = ['concept', 'relay-command']
        elif name in SPEAKERS or name in ('Grok', 'GPT', 'Ryn', 'Claude', 'Local', 'Nano'):
            pth = ent + '/%s.md' % slug(name); disp = name; kind = 'entity'; rule = 'Rule: every turn spoken by "%s" in a transcript, plus every unit whose text contains the whole word "%s" (case-insensitive) in any other source. Mechanical match, not a judgment about topic.' % (name, name); tags = ['entity']
        else:
            pth = ent + '/%s.md' % slug(name); disp = name; kind = 'entity'; rule = 'Rule: every unit whose text contains the whole word "%s", case-insensitive. Mechanical match, not a judgment about topic.' % name; tags = ['entity', 'mention']
        total = sum(len(v) for v in srcs.values())
        L = fm(type=kind, created=TODAY, updated=TODAY, tags=tags, sources=sorted(srcs.keys())[:50]) + ['', '# %s' % asc(disp), '', 'This page lists every place %s appears in the record, one line per occurrence (or per Reading part with the unit ids, for exports), cited by Reading part, unit id, and source position. It is a list of citations, not a description. %d occurrences across %d sources.' % (asc(disp), total, len(srcs)), '', rule, '']
        for st in sorted(srcs):
            L.append('## Occurrences in %s' % asc(st)); L.append('')
            for reading, mid, line, first in srcs[st]: L.append('- [[%s]] %s L%05d%s' % (reading, mid, line, (': ' + first) if first else ''))
            L.append('')
        wr(pth, '\n'.join(L)); written.append((kind, disp, os.path.basename(pth)[:-3]))
    for tag, srcs in sorted(state['tagocc'].items()):
        pth = con + '/Curator tag %s.md' % tag; total = sum(len(v) for v in srcs.values())
        L = fm(type='concept', created=TODAY, updated=TODAY, tags=['concept', 'curator-tag'], sources=sorted(srcs.keys())[:50]) + ['', '# Curator tag [%s]' % tag, '', 'Rule: every unit whose text contains the bracketed tag [%s...]. %d occurrences across %d sources. Mechanical match.' % (tag, total, len(srcs)), '']
        for st in sorted(srcs):
            L.append('## Occurrences in %s' % asc(st)); L.append('')
            for reading, mid, line, first in srcs[st]: L.append('- [[%s]] %s L%05d: %s' % (reading, mid, line, first))
            L.append('')
        wr(pth, '\n'.join(L)); written.append(('concept', 'Curator tag [%s]' % tag, 'Curator tag %s' % tag))
    # group indexes
    idx = ['# Index', '', 'Entry point for the wiki. One line per page. Readings are listed on the group index pages linked below; Entities and Concepts are listed here in full.', '', '## Reading groups', '']
    for g in sorted(state['groups']):
        gname = 'Index - %s' % slug(g)
        wr(NU + '/Wiki/%s.md' % gname, '\n'.join(fm(type='index', created=TODAY, updated=TODAY, tags=['index']) + ['', '# %s' % gname, '', '%d entries.' % len(state['groups'][g]), ''] + state['groups'][g]))
        idx.append('- [[%s]] -- %d entries' % (gname, len(state['groups'][g])))
    idx += ['', '## Entities', '']
    idx += ['- [[%s]]' % f for k, d, f in sorted(written) if k == 'entity']
    idx += ['', '## Concepts', '']
    idx += ['- [[%s]]' % f for k, d, f in sorted(written) if k == 'concept']
    idx += ['', '## Raw', '']
    idx += ['- [[%s]]' % f[:-3] for f in sorted(os.listdir(NU + '/Raw')) if f.endswith('.md')]
    wr(NU + '/Wiki/Index.md', '\n'.join(idx))
    log('## %s finish\n\n- wrote %d entity/concept pages, %d group indexes, Index.md with %d Raw records' % (now(), len(written), len(state['groups']), sum(1 for f in os.listdir(NU + '/Raw') if f.endswith('.md'))))

# ---------------------------------------------------------------- driver
def needed(cat):
    c = sqlite3.connect(NU + '/Inbox/phone_sources.db')
    return [r[0] for r in c.execute("select rel from files where category=? and needed=1 order by best_date, rel", (cat,))]
def run(phase):
    if phase == 'transcripts':
        done = set(state['done'])
        for rel in needed('relay_transcript'):
            src = PH + '/' + rel
            if rel in done or rel.endswith('.py') or rel.endswith('.html'): continue
            title = os.path.splitext(os.path.basename(rel))[0]; ingest_transcript(src, title, ['transcript', 'relay'], 'Relay transcripts'); state['done'].append(rel); save_state()
        for extra in ['C/ryn_relay_session_full_march20_27.md'] + sorted(glob.glob(NU + '/C/quartet_debate_*.md')):
            src = extra if extra.startswith('/') else NU + '/' + extra
            rel = os.path.relpath(src, NU)
            if rel in done: continue
            ingest_transcript(src, os.path.splitext(os.path.basename(src))[0], ['transcript', 'relay'], 'Relay transcripts'); state['done'].append(rel); save_state()
        for f in sorted(glob.glob(NU + '/curator_pass/ab/mike/logs/*.md')):
            rel = os.path.relpath(f, NU)
            if rel in done: continue
            ingest_transcript(f, os.path.splitext(os.path.basename(f))[0], ['transcript', 'relay', 'quartet'], 'Relay transcripts'); state['done'].append(rel); save_state()
    elif phase == 'notes':
        groups = {'markor_note': 'Notes - Markor', 'memory_note': 'Notes - memory', 'ryn_note': 'Notes - Ryn', 'signal': 'Signals and handoffs', 'work_order': 'Work orders', 'wiki': 'Relay wiki pages', 'skill': 'Skills',
                  'pipeline_script': 'Pipeline scripts', 'curator_output': 'Curator outputs', 'memory_shard': 'Memory shards', 'log': 'Run logs', 'conversation_md': 'Conversation markdown', 'manifest': 'Manifests and inventories'}
        for cat, group in groups.items():
            for rel in needed(cat):
                if rel in state['done']: continue
                src = PH + '/' + rel; title = '%s %s' % (cat, os.path.splitext(os.path.basename(rel))[0]) if cat in ('curator_output', 'conversation_md', 'skill') else os.path.splitext(os.path.basename(rel))[0]
                # avoid title collisions across directories
                if os.path.exists(NU + '/Raw/R - %s.md' % slug(title)): title = title + ' ' + hashlib.sha1(rel.encode()).hexdigest()[:6]
                try:
                    ingest_text(src, title, [cat.replace('_', '-')], group)
                except Exception as e:
                    log('## %s error %s\n\n- %s' % (now(), rel, asc(str(e))))
                state['done'].append(rel); save_state()
    elif phase == 'claude':
        canon = ingest_claude(NU + '/convo/conversations.json', 'Claude export 2026-09-12', 'Claude export 2026-09-12'); save_state()
        for p, label in [(PH + '/Download/coding/X/claude_exports/claude_export_20260716/conversations.json', 'Claude export 2026-07-16'),
                         (SCR + '/exports/claude_0830_1/conversations.json', 'Claude export 2026-08-30 conversations-000(1)'),
                         (PH + '/Download/zip/08_30_2026/conversations.json', 'Claude export 2026-08-30 conversations-000')]:
            if os.path.exists(p): ingest_claude(p, label, 'Claude exports superseded', canonical_uuids=canon); save_state()
    elif phase == 'gpt':
        canon = ingest_gpt(sorted(glob.glob(SCR + '/exports/gpt_20260805/conversations-00*.json')), 'GPT export 2026-08-05', 'GPT export 2026-08-05'); save_state()
        for p, label in [(PH + '/Download/models_relays/tw/threadweaver_originals_20260801/threadweaver__data_exports/conversations.json', 'GPT export 2025-09-30'),
                         (PH + '/Download/models_relays/tw/threadweaver_originals_20260801/archive_202645__data_exports/conversations.json', 'GPT export 2025-09-24'),
                         (PH + '/Download/docs/gpt_forensic_extract/gpt_export_raw.json', 'GPT export forensic extract')]:
            if os.path.exists(p): ingest_gpt([p], label, 'GPT exports superseded', canonical_ids=canon); save_state()
    elif phase == 'grok':
        ingest_grok(NU + '/7d6490b4-6b00-4690-b36d-5098611f41fd/ttl/30d/export_data/67f758ba-a7f4-498f-8591-df1a0c2191fb/prod-grok-backend.json', 'Grok export 2026-01-06', 'Grok export 2026-01-06'); save_state()
    elif phase == 'sessions':
        for rel in needed('claude_code_session'):
            if rel in state['done']: continue
            seat = rel.split('/')[2].replace('-home-mike-Desktop', 'Desktop').strip('-'); title = 'Claude Code %s %s' % (seat, os.path.basename(rel)[:8])
            ingest_session(PH + '/' + rel, title, 'Claude Code sessions'); state['done'].append(rel); save_state()
    elif phase == 'finish':
        finish(); save_state()
    print('phase', phase, 'done; occ names', len(state['occ']), 'groups', len(state['groups']), 'done sources', len(state['done']))

if __name__ == '__main__':
    for ph in sys.argv[1:]: run(ph)
