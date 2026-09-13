#!/usr/bin/env python3
"""ingest_transcript.py -- ingest a speaker-labelled relay transcript into the vault, verbatim, per CLAUDE.md.

Usage: ingest_transcript.py <source path> "<Reading title>" [tag,tag]

Writes:
  Raw/R - <basename>.md                      provenance header + full text, non-ASCII escaped as \\uXXXX
  Wiki/Readings/Read - <Title> (part NN of MM).md   every turn, in order, split at turn boundaries
  Wiki/Entities/<Speaker>.md                 one line per turn spoken, cited by part and turn id
  Wiki/Concepts/Relay command <cmd>.md        one line per turn that begins with that /command
  Wiki/Entities/<Name>.md (mentions)          one line per turn whose text contains the name (rule stated on page)
  Wiki/Index.md, Wiki/Log.md                 updated / appended
Nothing is omitted. Nothing is paraphrased. Selection rules are mechanical and stated on each page."""
import os, re, sys, hashlib, datetime, collections, unicodedata

NU = os.path.expanduser('~/Desktop/nu')
SRC = os.path.abspath(sys.argv[1]); TITLE = sys.argv[2]; TAGS = sys.argv[3].split(',') if len(sys.argv) > 3 else []
TODAY = datetime.date.today().isoformat(); NOW = datetime.datetime.now().isoformat(timespec='seconds')
PART_LINES = 1200
SPEAKERS = ['Mike', 'Clubhouse', 'You said', 'ChatGPT said', 'Grok', 'GPT', 'Ryn', 'Claude', 'Local', 'Nano', 'You']
SPEAKER_RE = re.compile(r'^(%s):\s*$' % '|'.join(re.escape(x) for x in SPEAKERS))   # known speaker labels alone on a line
SUB_RE = re.compile(r'^(?:[^\x00-\x7F]\s*)?(Grok|GPT|Local|Ryn|Claude|Nano|Quartet|Trio)\s*:\s*$')  # "<emoji> Grok:" inside a Clubhouse turn
CMD_RE = re.compile(r'^/([a-z_]+)')
MENTION_NAMES = ['Ryn', 'Claude', 'Willow', 'Madmartigan', 'Aethryn', 'Edge-Walker', 'Architect', 'Jetson', 'Ollama', 'Nano', 'Telegram', 'relay']

def asc(s):
    out = []
    for ch in s:
        o = ord(ch)
        out.append(ch if o < 128 else ('\\u%04x' % o if o < 0x10000 else '\\U%08x' % o))
    return ''.join(out)
def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()
def slug(s): return re.sub(r'[^A-Za-z0-9 _-]+', '', s).strip()

raw = open(SRC, encoding='utf-8', errors='replace').read()
lines = raw.split('\n')
digest = sha(SRC); size = os.path.getsize(SRC)
mtime = datetime.datetime.fromtimestamp(os.path.getmtime(SRC)).isoformat(timespec='seconds')
rel = os.path.relpath(SRC, NU)
base = os.path.splitext(os.path.basename(SRC))[0]

# ---- gate report (findings only, never healed)
gate = collections.Counter(ch for ch in raw if ord(ch) > 127)
gate_lines = ['Gate findings: %d characters outside the whitelist, %d distinct codepoints. Escaped as \\uXXXX below; the Raw bytes are unchanged at the source path.' % (sum(gate.values()), len(gate))]
for ch, n in gate.most_common(12): gate_lines.append('  U+%04X %s x%d' % (ord(ch), unicodedata.name(ch, '(no assigned name)'), n))

# ---- turns: a turn starts at a speaker line; text runs to the next speaker line
turns = []   # dict(id, line, speaker, sub, cmd, text_lines)
cur = None
for i, ln in enumerate(lines, 1):
    m = SPEAKER_RE.match(ln)
    if m:
        if cur: turns.append(cur)
        cur = dict(line=i, speaker=m.group(1).strip(), sub='', cmd='', text=[])
        continue
    if cur is None:
        cur = dict(line=i, speaker='(preamble)', sub='', cmd='', text=[])
    sm = SUB_RE.match(ln)
    if sm and cur['speaker'] == 'Clubhouse' and not cur['text']:
        cur['sub'] = sm.group(1); cur['text'].append(ln); continue
    if not cur['text'] and not cur['cmd']:
        cm = CMD_RE.match(ln.strip())
        if cm: cur['cmd'] = cm.group(1)
    cur['text'].append(ln)
if cur: turns.append(cur)
for k, t in enumerate(turns, 1): t['id'] = 'T%04d' % k
turn_lines_total = sum(1 for t in turns for _ in t['text']) + sum(1 for t in turns if t['speaker'] != '(preamble)')
assert turn_lines_total == len(lines), ('line count mismatch', turn_lines_total, len(lines))

# ---- Raw page
os.makedirs(NU + '/Raw', exist_ok=True)
raw_name = 'R - %s.md' % base
raw_page = ['---', 'type: raw', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: [raw, transcript%s]' % (''.join(', ' + t for t in TAGS)),
            'source_path: %s' % rel, 'source_sha256: %s' % digest, 'source_bytes: %d' % size, 'source_lines: %d' % len(lines), 'source_mtime: %s' % mtime,
            'turns: %d' % len(turns), '---', '', '# R - %s' % base, '',
            'Verbatim copy of the source. Characters outside the 98-character whitelist are written as \\uXXXX escapes; nothing else is changed. Line numbers in the Readings refer to this file and to the source, which are line-for-line identical.', '']
raw_page += gate_lines + ['', '---', ''] + [asc(l) for l in lines]
open(NU + '/Raw/' + raw_name, 'w', encoding='ascii').write('\n'.join(raw_page) + '\n')

# ---- Reading parts, split at turn boundaries near PART_LINES
os.makedirs(NU + '/Wiki/Readings', exist_ok=True)
parts = []; buf = []; n = 0
for t in turns:
    tl = len(t['text']) + 2
    if buf and n + tl > PART_LINES: parts.append(buf); buf = []; n = 0
    buf.append(t); n += tl
if buf: parts.append(buf)
M = len(parts)
def part_name(i): return 'Read - %s (part %02d of %02d)' % (TITLE, i, M)
raw_link = '[[%s]]' % raw_name[:-3]
for i, P in enumerate(parts, 1):
    pg = ['---', 'type: reading', 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: [reading, transcript%s]' % (''.join(', ' + t for t in TAGS)),
          'sources: ["%s"]' % raw_name[:-3], 'part: %d' % i, 'parts: %d' % M, 'turns: %s to %s' % (P[0]['id'], P[-1]['id']),
          'lines: %d to %d' % (P[0]['line'], P[-1]['line'] + len(P[-1]['text'])), 'source_sha256: %s' % digest, '---', '',
          '# %s' % part_name(i), '',
          'Source: %s (sha256 %s), lines %d to %d, turns %s to %s. Every turn in this range is present in full. Turn headers are added structure: turn id, source line number, speaker, and the /command that opens the turn when there is one.' % (raw_link, digest[:16], P[0]['line'], P[-1]['line'] + len(P[-1]['text']), P[0]['id'], P[-1]['id']), '',
          ('Previous: [[%s]]' % part_name(i - 1) if i > 1 else '') + ('  Next: [[%s]]' % part_name(i + 1) if i < M else ''), '']
    for t in P:
        hdr = '### %s L%05d %s' % (t['id'], t['line'], t['speaker'] + ((' / ' + t['sub']) if t['sub'] else '') + ((' /' + t['cmd']) if t['cmd'] else ''))
        pg.append(hdr); pg.append(''); pg += [asc(l) for l in t['text']]; pg.append('')
    open(NU + '/Wiki/Readings/%s.md' % part_name(i), 'w', encoding='ascii').write('\n'.join(pg) + '\n')
part_of = {}
for i, P in enumerate(parts, 1):
    for t in P: part_of[t['id']] = i

# ---- Entity pages for speakers; Concept pages for commands; mention pages
def cite(t):
    first = next((asc(l.strip()) for l in t['text'] if l.strip() and not SUB_RE.match(l)), '')
    return '- [[%s]] %s L%05d: %s' % (part_name(part_of[t['id']]), t['id'], t['line'], first[:140])
def write_page(path, fm_type, name, rule, entries, tags):
    exists = os.path.exists(path)
    if exists:
        old = open(path, encoding='ascii').read()
        old = re.sub(r'^updated: .*$', 'updated: %s' % TODAY, old, flags=re.M)
        block = ['', '## Occurrences in %s' % TITLE, '', rule, ''] + entries
        open(path, 'w', encoding='ascii').write(old.rstrip('\n') + '\n' + '\n'.join(block) + '\n')
    else:
        pg = ['---', 'type: %s' % fm_type, 'created: %s' % TODAY, 'updated: %s' % TODAY, 'tags: [%s]' % ', '.join(tags), 'sources: ["%s"]' % raw_name[:-3], '---', '',
              '# %s' % name, '', 'This page lists every place %s appears in the record, one line per occurrence, cited by Reading part, turn id, and source line. It is a list of citations, not a description.' % name, '',
              '## Occurrences in %s' % TITLE, '', rule, ''] + entries
        open(path, 'w', encoding='ascii').write('\n'.join(pg) + '\n')
    return exists
os.makedirs(NU + '/Wiki/Entities', exist_ok=True); os.makedirs(NU + '/Wiki/Concepts', exist_ok=True)
touched = []
by_speaker = collections.defaultdict(list)
for t in turns:
    if t['speaker'] == '(preamble)': continue
    by_speaker[t['speaker']].append(t)
    if t['sub']: by_speaker[t['sub']].append(t)
for spk, L in by_speaker.items():
    p = NU + '/Wiki/Entities/%s.md' % slug(spk)
    rule = 'Rule: every turn in the transcript whose speaker line is "%s:" (or whose Clubhouse turn opens with the %s sub-speaker line). %d turns. First non-empty line of each turn is shown; the full turn is on the cited Reading part.' % (spk, spk, len(L))
    write_page(p, 'entity', spk, rule, [cite(t) for t in L], ['entity', 'speaker']); touched.append('Entities/%s' % slug(spk))
by_cmd = collections.defaultdict(list)
for t in turns:
    if t['cmd']: by_cmd[t['cmd']].append(t)
for cmd, L in by_cmd.items():
    p = NU + '/Wiki/Concepts/Relay command %s.md' % cmd
    rule = 'Rule: every turn whose first non-empty line begins with "/%s". %d turns.' % (cmd, len(L))
    write_page(p, 'concept', 'Relay command /%s' % cmd, rule, [cite(t) for t in L], ['concept', 'relay-command']); touched.append('Concepts/Relay command %s' % cmd)
for name in MENTION_NAMES:
    L = [t for t in turns if any(re.search(r'\b%s\b' % re.escape(name), l, re.I) for l in t['text'])]
    if not L: continue
    p = NU + '/Wiki/Entities/%s.md' % slug(name)
    rule = 'Rule: every turn whose text contains the whole word "%s", case-insensitive. %d turns. This is a mechanical name match, not a judgment about what the turn is about.' % (name, len(L))
    write_page(p, 'entity', name, rule, [cite(t) for t in L], ['entity', 'mention']); touched.append('Entities/%s' % slug(name))

# ---- Index and Log
idx_path = NU + '/Wiki/Index.md'; idx = open(idx_path, encoding='ascii').read() if os.path.exists(idx_path) else '# Index\n\n## Entities\n\n## Concepts\n\n## Readings\n'
def add_to_section(text, section, line):
    if line in text: return text
    parts_ = text.split('\n## ')
    for k, sec in enumerate(parts_):
        if sec.startswith(section):
            body = sec.rstrip('\n') + '\n' + line + '\n'
            parts_[k] = body; return '\n## '.join(parts_)
    return text.rstrip('\n') + '\n\n## %s\n%s\n' % (section, line)
for i in range(1, M + 1):
    idx = add_to_section(idx, 'Readings', '- [[%s]] -- %s, turns %s to %s, lines %d to %d' % (part_name(i), TITLE, parts[i-1][0]['id'], parts[i-1][-1]['id'], parts[i-1][0]['line'], parts[i-1][-1]['line'] + len(parts[i-1][-1]['text'])))
idx = add_to_section(idx, 'Readings', '- [[%s]] -- raw source, %d lines, sha256 %s' % (raw_name[:-3], len(lines), digest[:16]))
for tpath in touched:
    sec, nm = tpath.split('/', 1)
    idx = add_to_section(idx, sec, '- [[%s]]' % nm)
open(idx_path, 'w', encoding='ascii').write(idx)
log_path = NU + '/Wiki/Log.md'
entry = ['', '## %s ingest %s' % (NOW, rel), '', '- source sha256 %s, %d bytes, %d lines, %d turns' % (digest, size, len(lines), len(turns)),
         '- gate: %d non-whitelist characters, %d distinct, escaped in Raw and Readings, source untouched' % (sum(gate.values()), len(gate)),
         '- wrote Raw/%s' % raw_name, '- wrote %d Reading parts: %s .. %s' % (M, part_name(1), part_name(M)),
         '- pages touched: %s' % ', '.join(touched), '- seat: online (Claude Code), rulebook CLAUDE.md as of %s' % TODAY]
open(log_path, 'a', encoding='ascii').write('\n'.join(entry) + '\n')

print('turns', len(turns), 'parts', M, 'raw lines', len(lines), 'gate chars', sum(gate.values()))
print('speakers:', {k: len(v) for k, v in by_speaker.items()})
print('commands:', dict(collections.Counter(t['cmd'] for t in turns if t['cmd']).most_common(12)))
print('pages touched:', len(touched))
