#!/usr/bin/env python3
"""tag_relay.py -- tag the relay work across the record and attribute every hit to its speaker.
Mechanical rule, stated on every page it writes:
  A unit is a relay unit if its text contains any term in RELAY_TERMS (case-insensitive, whole word).
  The contributor is the speaker label the source itself carries:
    transcripts: the speaker line (Mike, Grok, GPT, Ryn, Claude; Clubhouse sub-speaker; "You said" -> Mike, "ChatGPT said" -> GPT)
    Claude export: human -> Mike, assistant -> Claude (claude.ai)
    GPT export: user -> Mike, assistant -> GPT (chatgpt)
    Grok export: human -> Mike, assistant -> Grok
    Claude Code sessions: user -> Mike, assistant -> Claude Code
    notes and other documents: "document" plus the source group (author not asserted)
Writes/updates: Reading frontmatter tags (relay, relay-<contributor>), Concepts/Aethryn Relay.md,
Concepts/Relay contributions - <contributor>.md, Concepts/Relay timeline.md, Index.md, Log.md."""
import os, re, sqlite3, datetime, collections
R = os.path.expanduser('~/Desktop/nu/record'); NU = os.path.expanduser('~/Desktop/nu')
TODAY = datetime.date.today().isoformat(); NOW = datetime.datetime.now().isoformat(timespec='seconds')
RELAY_TERMS = ['relay', 'Aethryn', 'Clubhouse', 'Ryn', 'quartet', 'triodoc', 'duetdoc', 'quartetdoc', 'fieldrelay', 'aethryn_relay', 'telegram_relay', 'relay_memory',
               'nanochat', 'wake_up', 'Phoenix shard', 'memory shard', 'Bone Toss', 'Edge-Walker', 'Architect-Mirror', 'Madmartigan', 'sovereign node', 'Shamallama', 'Jetson']
TERM_RE = re.compile(r'\b(' + '|'.join(re.escape(t) for t in RELAY_TERMS) + r')\b', re.I)
STRICT_RE = re.compile(r'\b(' + '|'.join(re.escape(t) for t in RELAY_TERMS if t != 'relay') + r')\b', re.I)
HEAD_RE = re.compile(r'^### (\S+) (.*)$', re.M)

TOKCH = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_./\\~:-')
def classify(text, rx):
    """Return (prose_hits, file_hits). A match is a file/identifier hit when the maximal token around it
    (letters, digits, _ . / \\ ~ : -) contains a path separator, an underscore, a ~, or a dot followed by a
    letter or digit (an extension); trailing sentence punctuation is stripped first. Otherwise it is prose."""
    prose = files = 0
    for m in rx.finditer(text):
        a, b = m.start(), m.end()
        while a > 0 and text[a-1] in TOKCH: a -= 1
        while b < len(text) and text[b] in TOKCH: b += 1
        tok = text[a:b].rstrip('.,:;)')
        if ('/' in tok or '\\' in tok or '_' in tok or tok.startswith('~') or re.search(r'\.[A-Za-z0-9]', tok)): files += 1
        else: prose += 1
    return prose, files
FILE_RULE = 'A match counts as "in file names and paths" when the token around it contains a path separator, an underscore, a tilde, or a dot followed by a letter or digit (an extension); otherwise it counts as "in conversation". Sentence punctuation is ignored. Stated so it can be rerun.'

SPEAK = {'You said': 'Mike', 'ChatGPT said': 'GPT', 'Human': 'Mike', 'User': 'Mike', 'Assistant': 'Claude', 'Local': 'Ryn', 'Nano': 'Ryn'}

def contributor(head, tags, group):
    # exports / sessions carry ISO timestamps then a role
    m = re.match(r'^(\d{4}-\d{2}-\d{2}T[0-9:.]+Z?)\s+(\S+)', head)
    if m and ('export' in tags or 'session' in tags):
        role = m.group(2)
        if 'claude' in tags and 'session' not in tags: return {'human': 'Mike', 'assistant': 'Claude'}.get(role, role), m.group(1)
        if 'gpt' in tags: return {'user': 'Mike', 'assistant': 'GPT', 'system': 'GPT system', 'tool': 'GPT tool'}.get(role, role), m.group(1)
        if 'grok' in tags: return {'human': 'Mike', 'assistant': 'Grok'}.get(role, role), m.group(1)
        if 'session' in tags: return {'user': 'Mike', 'assistant': 'Claude Code'}.get(role, 'Claude Code ' + role), m.group(1)
    if 'transcript' in tags:
        m = re.match(r'^L\d+ (.+?)(?: /\w+)?$', head)
        if m:
            spk = m.group(1)
            if ' / ' in spk: spk = spk.split(' / ')[1]          # Clubhouse / Grok -> Grok
            spk = spk.strip('*')
            if spk == '(preamble)': return 'document', ''
            return SPEAK.get(spk, spk), ''
    return 'document', ''

# source dates for undated sources (transcripts, notes) from the phone catalog and Raw pages
best_date = {}
c = sqlite3.connect(R + '/Inbox/phone_sources.db')
for rel, d in c.execute('select rel, best_date from files'): best_date['phone/' + rel] = d
raw_date = {}
for f in os.listdir(R + '/Raw'):
    t = open(R + '/Raw/' + f, encoding='ascii').read(8000)
    sp = re.search(r'^source_path: (.*)$', t, re.M); mt = re.search(r'^source_mtime: (\S+)', t, re.M)
    if sp: raw_date[f[:-3]] = best_date.get(sp.group(1)) or (mt.group(1)[:10] if mt else '')

hits = []   # (ts, date, contributor, reading, unit, first, group)
tagged = 0; scanned = 0
for f in sorted(os.listdir(R + '/Wiki/Readings')):
    p = R + '/Wiki/Readings/' + f; txt = open(p, encoding='ascii').read(); scanned += 1
    fm_end = txt.find('\n---\n', 4); fm = txt[:fm_end]; body = txt[fm_end + 5:]
    tags = re.search(r'^tags: \[(.*)\]$', fm, re.M); tags = [x.strip().strip('"') for x in tags.group(1).split(',')] if tags else []
    src = re.search(r'^sources: \["(.*?)"', fm, re.M); src = src.group(1) if src else ''
    group = 'export' if 'export' in tags else ('session' if 'session' in tags else ('transcript' if 'transcript' in tags else 'document'))
    units = re.split(r'^(?=### \S+ )', body, flags=re.M)
    contribs = set(); n = 0; page_file = False
    for u in units:
        m = HEAD_RE.match(u)
        if not m: continue
        uid, head = m.group(1), m.group(2); text = u[m.end():]
        pr, fi = classify(text, TERM_RE)
        if not pr:
            if fi: page_file = True
            continue
        who, ts = contributor(head, tags, group)
        date = ts[:10] if ts else raw_date.get(src, '')
        first = next((l.strip() for l in text.split('\n') if l.strip() and not l.startswith('[')), '')[:140]
        hits.append((ts, date, who, f[:-3], uid, first, group, bool(STRICT_RE.search(text)))); contribs.add(who); n += 1
    base = [x for x in tags if x != 'relay' and x != 'relay-file' and not x.startswith('relay-')]
    newtags = base + (['relay'] if n else []) + ['relay-' + re.sub(r'[^a-z0-9]+', '-', w.lower()).strip('-') for w in sorted(contribs)] + (['relay-file'] if page_file else [])
    newtags = list(dict.fromkeys(newtags))
    if newtags != tags:
        fm2 = re.sub(r'^tags: \[.*\]$', 'tags: [%s]' % ', '.join('"%s"' % t for t in newtags), fm, flags=re.M)
        fm2 = re.sub(r'^updated: .*$', 'updated: %s' % TODAY, fm2, flags=re.M)
        if fm2 != fm: open(p, 'w', encoding='ascii').write(fm2 + txt[fm_end:]); tagged += 1

by = collections.defaultdict(list)
for h in hits: by[h[2]].append(h)
rule = ('Rule: a unit is a relay unit when its text contains any of these terms in conversation, case-insensitive, whole word: %s. %s Units where the terms appear only in file names get the tag relay-file and are not counted here. The contributor is the speaker label the source itself carries (transcript speaker line; export sender or role; session role), never a judgment about content. Mechanical; rerunnable.' % (', '.join(RELAY_TERMS), FILE_RULE))
def fmt(h):
    ts, date, who, reading, uid, first, group, strict = h
    return '- %s [[%s]] %s%s' % (ts or date or '(undated)', reading, uid, (': ' + first) if first else '')
con = R + '/Wiki/Concepts'
# per-contributor pages
pages = []
for who in sorted(by, key=lambda w: -len(by[w])):
    L = by[who]; name = 'Relay contributions - %s' % who
    dated = sorted([h for h in L if h[0]], key=lambda h: h[0]); undated = sorted([h for h in L if not h[0]], key=lambda h: (h[1], h[3], h[4]))
    out = ['---', 'type: concept', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: ["concept", "relay", "relay-%s"]' % re.sub(r'[^a-z0-9]+', '-', who.lower()).strip('-'), '---', '',
           '# %s' % name, '', 'Every relay unit spoken by %s across the record: %d units, %d with server timestamps, %d dated by source only. Part of [[Aethryn Relay]].' % (who, len(L), len(dated), len(undated)), '', rule, '',
           '## Timestamped, in server-time order', ''] + [fmt(h) for h in dated] + ['', '## Dated by source only, in source order', ''] + [fmt(h) for h in undated]
    open(con + '/%s.md' % name, 'w', encoding='ascii').write('\n'.join(out) + '\n'); pages.append((name, len(L)))
# timeline across contributors (timestamped units only)
dated = sorted([h for h in hits if h[0]], key=lambda h: h[0])
out = ['---', 'type: concept', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: ["concept", "relay", "timeline"]', '---', '', '# Relay timeline', '',
       'Every timestamped relay unit from every source, interleaved in server-time order, with its contributor. %d units from %s to %s. Undated transcript and note units are on the per-contributor pages. Part of [[Aethryn Relay]].' % (len(dated), dated[0][0][:10] if dated else '', dated[-1][0][:10] if dated else ''), '', rule, '']
cur = ''
for h in dated:
    if h[0][:7] != cur: cur = h[0][:7]; out += ['', '## %s' % cur, '']
    out.append('- %s **%s** [[%s]] %s%s' % (h[0], h[2], h[3], h[4], (': ' + h[5]) if h[5] else ''))
open(con + '/Relay timeline.md', 'w', encoding='ascii').write('\n'.join(out) + '\n')
# strict timeline (bare word 'relay' excluded)
sdated = [h for h in dated if h[7]]
out = ['---', 'type: concept', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: ["concept", "relay", "timeline"]', '---', '', '# Relay timeline (strict)', '',
       'Same as [[Relay timeline]] but the bare word "relay" is not a match on its own; a unit must contain one of the relay-specific terms (Aethryn, Clubhouse, Ryn, quartet, triodoc, and the rest of the list). This removes hardware relays and other ordinary uses of the word. %d units. Part of [[Aethryn Relay]].' % len(sdated), '', rule, '']
cur = ''
for h in sdated:
    if h[0][:7] != cur: cur = h[0][:7]; out += ['', '## %s' % cur, '']
    out.append('- %s **%s** [[%s]] %s%s' % (h[0], h[2], h[3], h[4], (': ' + h[5]) if h[5] else ''))
open(con + '/Relay timeline (strict).md', 'w', encoding='ascii').write('\n'.join(out) + '\n')
# hub page
counts = collections.Counter(h[2] for h in hits); scounts = collections.Counter(h[2] for h in hits if h[7]); groups = collections.Counter(h[6] for h in hits)
out = ['---', 'type: concept', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: ["concept", "relay"]', '---', '', '# Aethryn Relay', '',
       'The relay work across every source in the record, attributed to whoever spoke each unit. %d relay units in %d Reading pages. Every model had a hand in it; this page shows how much of the record each voice carries, by count, and links to the full lists.' % (len(hits), tagged), '', rule, '',
       '| Contributor | Relay units (any term) | Strict (bare "relay" excluded) | Page |', '|---|---:|---:|---|']
out += ['| %s | %d | %d | [[Relay contributions - %s]] |' % (w, n, scounts.get(w, 0), w) for w, n in counts.most_common()]
out += ['', '"document" means a note, shard, script, or curator output whose author the source does not label; those units are attributed to no voice.']
out += ['', 'By source shape: %s.' % ', '.join('%s %d' % (k, v) for k, v in groups.most_common()), '', '- [[Relay timeline]] -- all timestamped relay units interleaved across contributors', '- [[Relay timeline (strict)]] -- the same with the bare word "relay" excluded', '- Reading pages carrying relay units are tagged `relay` and `relay-<contributor>` in their frontmatter; filter the graph or search by tag.', '',
        'Related mechanical pages: [[Aethryn]], [[relay]], [[Ryn]], [[Clubhouse]], and the Relay command pages.']
open(con + '/Aethryn Relay.md', 'w', encoding='ascii').write('\n'.join(out) + '\n')
# index + log
idx = open(R + '/Wiki/Index.md', encoding='ascii').read()
add = ['- [[Aethryn Relay]]', '- [[Relay timeline]]', '- [[Relay timeline (strict)]]'] + ['- [[Relay contributions - %s]]' % w for w, n in counts.most_common()]
add = [a for a in add if a not in idx]
if add: idx = idx.replace('\n## Concepts\n\n', '\n## Concepts\n\n' + '\n'.join(add) + '\n', 1)
open(R + '/Wiki/Index.md', 'w', encoding='ascii').write(idx)
open(R + '/Wiki/Log.md', 'a', encoding='ascii').write('\n## %s tag relay\n\n- scanned %d Readings, tagged %d with relay and relay-<contributor>; %d relay units; contributors: %s\n- wrote Concepts/Aethryn Relay, Relay timeline, and %d contributor pages; rule stated on each page\n' % (NOW, scanned, tagged, len(hits), ', '.join('%s %d' % (w, n) for w, n in counts.most_common()), len(pages)))
print('scanned', scanned, 'tagged', tagged, 'relay units', len(hits)); print(counts.most_common()); print('groups', groups.most_common())
