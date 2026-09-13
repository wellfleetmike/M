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


con = R + '/Wiki/Concepts'

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

import sys
NAMES = sys.argv[1:] or ['Aethryn', 'Willow', 'Madmartigan', 'Ryn']
for NAME in NAMES:
    tag = re.sub(r'[^a-z0-9]+', '-', NAME.lower()).strip('-')
    NRE = re.compile(r'\b%s\b' % re.escape(NAME), re.I)
    hits = []; tagged = 0; scanned = 0
    for f in sorted(os.listdir(R + '/Wiki/Readings')):
        p = R + '/Wiki/Readings/' + f; txt = open(p, encoding='ascii').read(); scanned += 1
        fm_end = txt.find('\n---\n', 4); fm = txt[:fm_end]; body = txt[fm_end + 5:]
        tags = re.search(r'^tags: \[(.*)\]$', fm, re.M); tags = [x.strip().strip('"') for x in tags.group(1).split(',')] if tags else []
        srcp = re.search(r'^sources: \["(.*?)"', fm, re.M); srcp = srcp.group(1) if srcp else ''
        group = 'export' if 'export' in tags else ('session' if 'session' in tags else ('transcript' if 'transcript' in tags else 'document'))
        n = 0; page_prose = page_file = False
        for u in re.split(r'^(?=### \S+ )', body, flags=re.M):
            m = HEAD_RE.match(u)
            if not m: continue
            uid, hd = m.group(1), m.group(2); text = u[m.end():]
            pr, fi = classify(text, NRE)
            if not (pr or fi): continue
            who, ts = contributor(hd, tags, group); date = ts[:10] if ts else raw_date.get(srcp, '')
            first = next((l.strip() for l in text.split('\n') if l.strip() and not l.startswith('[')), '')[:140]
            hits.append((ts, date, who, f[:-3], uid, first, group, pr, fi)); n += 1
            if pr: page_prose = True
            if fi: page_file = True
        newtags = [x for x in tags if x not in (tag, tag + '-file')]
        if n and page_prose: newtags.append(tag)
        if n and page_file: newtags.append(tag + '-file')
        if newtags != tags:
            fm2 = re.sub(r'^tags: \[.*\]$', 'tags: [%s]' % ', '.join('"%s"' % t for t in newtags), fm, flags=re.M)
            fm2 = re.sub(r'^updated: .*$', 'updated: %s' % TODAY, fm2, flags=re.M)
            open(p, 'w', encoding='ascii').write(fm2 + txt[fm_end:]); tagged += 1
    rule = 'Rule: every unit whose text contains the whole word "%s", case-insensitive. The contributor is the speaker label the source itself carries (transcript speaker line; export sender or role; session role). %s Mechanical; rerunnable.' % (NAME, FILE_RULE)
    conv = [h for h in hits if h[7]]; fil = [h for h in hits if h[8] and not h[7]]
    counts = collections.Counter(h[2] for h in conv); fcounts = collections.Counter(h[2] for h in fil)
    def section(L, title):
        dated = sorted([h for h in L if h[0]], key=lambda h: h[0]); undated = sorted([h for h in L if not h[0]], key=lambda h: (h[1], h[3], h[4]))
        o = ['', '## %s (%d units)' % (title, len(L)), '', '| Contributor | Units |', '|---|---:|'] + ['| %s | %d |' % (w, n) for w, n in collections.Counter(h[2] for h in L).most_common()] + ['', '### Timestamped, server-time order', '']
        cur = ''
        for h in dated:
            if h[0][:7] != cur: cur = h[0][:7]; o += ['', '#### %s' % cur, '']
            o.append('- %s **%s** [[%s]] %s%s' % (h[0], h[2], h[3], h[4], (': ' + h[5]) if h[5] else ''))
        o += ['', '### Dated by source only, source order', ''] + ['- %s **%s** [[%s]] %s%s' % (h[1] or '(undated)', h[2], h[3], h[4], (': ' + h[5]) if h[5] else '') for h in undated]
        return o
    out = ['---', 'type: concept', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: ["concept", "%s", "timeline"]' % tag, '---', '', '# %s timeline' % NAME, '',
           'Every unit in the record that contains the word %s, split into what was said in conversation and what appears only in file names, paths, and identifiers, attributed and in server-time order. %d units in conversation, %d only in file names. Reading pages are tagged `%s` for conversation hits and `%s-file` for file-name hits. The plain occurrence list is [[%s]].' % (NAME, len(conv), len(fil), tag, tag, NAME), '', rule]
    out += section(conv, 'In conversation') + section(fil, 'In file names and paths only')
    dated = sorted([h for h in conv if h[0]], key=lambda h: h[0])
    open(con + '/%s timeline.md' % NAME, 'w', encoding='ascii').write('\n'.join(out) + '\n')
    idx = open(R + '/Wiki/Index.md', encoding='ascii').read()
    line = '- [[%s timeline]]' % NAME
    if line not in idx: idx = idx.replace('\n## Concepts\n\n', '\n## Concepts\n\n' + line + '\n', 1); open(R + '/Wiki/Index.md', 'w', encoding='ascii').write(idx)
    open(R + '/Wiki/Log.md', 'a', encoding='ascii').write('\n## %s tag %s\n\n- %d conversation units tagged `%s`, %d file-name-only units tagged `%s-file`, %d Readings retagged; wrote Concepts/%s timeline with the two sections; first conversation hit: %s\n' % (NOW, NAME, len(conv), tag, len(fil), tag, tagged, NAME, dated[0][0] if dated else 'none'))
    print(NAME, 'conversation', len(conv), 'file-only', len(fil), 'readings retagged', tagged, 'first conversation', dated[0][0] if dated else None, dict(counts.most_common(5)))
