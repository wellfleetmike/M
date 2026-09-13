# UNPACK -- restoring the record on a fresh box

This repo is the durable memory. The box gets reformatted; GitHub keeps the
commit log. Everything needed to stand the work back up is here or is named
here by path and sha256.

## 1. Clone

    mkdir -p ~/Desktop/nu && cd ~/Desktop/nu
    git clone https://github.com/wellfleetmike/M.git M

## 2. Restore the shared layer state

    cd ~/Desktop/nu/M
    PYTHONPATH=. python3 - <<'PY'
    import json, sys
    sys.path.insert(0, '.')
    from relay_memory import save
    for m in json.load(open('state/relay_memory_export_2026-09-13.json')):
        save(name=m['name'], type=m['type'], description=m['description'],
             content=m['content'], tags=[t for t in m['tags'].split(',') if t],
             source_instance=m['source_instance'])
    PY
    PYTHONPATH=. python3 -m relay_memory list

relay_memory.db is gitignored on purpose; the JSON export in state/ is the
committed copy. Re-export after every session:

    PYTHONPATH=. python3 -c "import sqlite3,json;c=sqlite3.connect('relay_memory.db');c.row_factory=sqlite3.Row;json.dump([dict(r) for r in c.execute('select * from memories order by created_at')],open('state/relay_memory_export_$(date +%F).json','w'),indent=1,ensure_ascii=True)"

## 3. Seats

    cp -r seats/dispatch  ~/Desktop/nu/dispatch      # Dispatch seat, boot Claude Code there
    mkdir -p ~/Desktop/nu/record && cp seats/librarian/CLAUDE.md ~/Desktop/nu/record/CLAUDE.md

Read state/HANDOFF_2026-09-13.md before doing anything else. It is the map.

## 4. The vault (two ways)

Fast: unpack the tarball made with bundle.py (kept off-repo, on a drive):

    tar xzf record_YYYYMMDD_HHMMSS.tar.gz -C ~/Desktop/nu/   # produces ~/Desktop/nu/record/
    sha256sum -c record_YYYYMMDD_HHMMSS.manifest.txt          # from inside ~/Desktop/nu

Slow, from sources: put the sources back at the paths in state/HANDOFF (phone/,
convo/, curator/, curator_pass/, backup/memory/memory.db, memory/memory.db),
then run tools/ in the order given in tools/README.md.

## 5. Comms

    cd ~/Desktop/nu/M && PYTHONPATH=. python3 -m relay_comms status

Inboxes, logs, and snaps are created on first use and never committed.

## 6. Obsidian

Open ~/Desktop/nu/record as the vault. Never ~/Desktop/nu. Plugins are in
record/.obsidian/plugins inside the tarball; turn Restricted mode off.
