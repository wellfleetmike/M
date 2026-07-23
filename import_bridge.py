#!/usr/bin/env python3
"""import_bridge.py -- Pull encrypted relay bridge data into local relay systems.

v2: age decryption + dedup ledger.

Reads relay_bridge/memories/<tier>/*.json.age and relay_bridge/messages/*.json.age,
decrypts with your identity file, and imports into relay_memory / relay_comms.
Files your identity cannot decrypt (other tiers) are skipped quietly — that is
the tier boundary working as intended.

A ledger (imported.db, SQLite, sits next to relay_memory.db) records the
content hash of every file already imported, so re-running after every pull
is safe: unchanged files are skipped, changed memories re-upsert, and
messages are never re-delivered.

Usage:
    python3 import_bridge.py /path/to/repo/relay_bridge -i ~/.keys/relay.key
    python3 import_bridge.py ... --memories-only | --messages-only
    python3 import_bridge.py ... --dry-run
"""

import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bridge_crypt

GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
DIM = '\033[90m'
RESET = '\033[0m'


# ---------------------------------------------------------------- ledger

def ledger_connect(path):
    conn = sqlite3.connect(str(path))
    conn.execute('''CREATE TABLE IF NOT EXISTS imported (
        relpath     TEXT NOT NULL,
        sha256      TEXT NOT NULL,
        kind        TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        PRIMARY KEY (relpath, sha256)
    )''')
    return conn


def already_imported(conn, relpath, digest):
    return conn.execute(
        'SELECT 1 FROM imported WHERE relpath=? AND sha256=?',
        (relpath, digest)).fetchone() is not None


def record_import(conn, relpath, digest, kind):
    conn.execute(
        'INSERT OR IGNORE INTO imported VALUES (?,?,?,?)',
        (relpath, digest, kind, datetime.now(timezone.utc).isoformat()))
    conn.commit()


# ---------------------------------------------------------------- decrypt

def try_decrypt(fpath, identity):
    """Decrypt one .age file. Returns dict, or None if not readable by us."""
    data = fpath.read_bytes()
    try:
        plain = bridge_crypt.decrypt(data, identity)
    except Exception:
        return None          # not our tier (or corrupt) — skip
    return json.loads(plain)


def iter_age_files(root):
    yield from sorted(root.rglob('*.json.age'))


# ---------------------------------------------------------------- memories

def import_memories(bridge_dir, identity, ledger, dry_run=False):
    mem_dir = bridge_dir / 'memories'
    if not mem_dir.is_dir():
        print(f'{YELLOW}no memories directory found{RESET}')
        return 0

    try:
        from relay_memory import save
    except ImportError:
        print(f'{RED}relay_memory not importable — is it on PYTHONPATH?{RESET}',
              file=sys.stderr)
        sys.exit(1)

    count = 0
    for fpath in iter_age_files(mem_dir):
        rel = str(fpath.relative_to(bridge_dir))
        digest = hashlib.sha256(fpath.read_bytes()).hexdigest()

        if already_imported(ledger, rel, digest):
            continue

        m = try_decrypt(fpath, identity)
        if m is None:
            if not dry_run:
                record_import(ledger, rel, digest, 'skipped-tier')
            print(f'  {DIM}not our tier:{RESET} {rel}')
            continue

        name = m.get('name', fpath.stem.replace('.json', ''))
        mtype = m.get('type', 'reference')
        tags = [t for t in (m.get('tags') or '').split(',') if t.strip()]

        if dry_run:
            print(f'  {DIM}would import:{RESET} {name} ({mtype})')
        else:
            save(name=name, type=mtype,
                 description=m.get('description', ''),
                 content=m.get('content', ''),
                 tags=tags,
                 source_instance=m.get('source_instance', 'github-bridge'))
            record_import(ledger, rel, digest, 'memory')
            print(f'  {GREEN}imported:{RESET} {name} ({mtype})')
        count += 1

    return count


# ---------------------------------------------------------------- messages

def import_messages(bridge_dir, identity, ledger, dry_run=False):
    msg_dir = bridge_dir / 'messages'
    if not msg_dir.is_dir():
        print(f'{YELLOW}no messages directory found{RESET}')
        return 0

    try:
        from relay_comms import send
    except ImportError:
        print(f'{YELLOW}relay_comms not installed — skipping message import{RESET}')
        return 0

    count = 0
    for fpath in iter_age_files(msg_dir):
        rel = str(fpath.relative_to(bridge_dir))
        digest = hashlib.sha256(fpath.read_bytes()).hexdigest()

        if already_imported(ledger, rel, digest):
            continue          # never re-deliver

        m = try_decrypt(fpath, identity)
        if m is None:
            if not dry_run:
                record_import(ledger, rel, digest, 'skipped-tier')
            print(f'  {DIM}not our tier:{RESET} {rel}')
            continue

        source = m.get('source', 'unknown')
        target = m.get('target', 'operator')

        if dry_run:
            print(f'  {DIM}would relay:{RESET} {source} -> {target} '
                  f'[{m.get("priority", "info")}]')
        else:
            send(target=target, body=m.get('body', ''),
                 priority=m.get('priority', 'info'), source=source)
            record_import(ledger, rel, digest, 'message')
            print(f'  {GREEN}relayed:{RESET} {source} -> {target} '
                  f'[{m.get("priority", "info")}]')
        count += 1

    return count


# ---------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(
        description='Import encrypted relay bridge data into local relay systems')
    p.add_argument('bridge_dir', type=Path,
                   help='Path to the relay_bridge directory in the cloned repo')
    p.add_argument('-i', '--identity', type=Path, required=True,
                   help='age identity file (AGE-SECRET-KEY-...)')
    p.add_argument('--ledger', type=Path, default=None,
                   help='dedup ledger path (default: imported.db beside this script)')
    p.add_argument('--memories-only', action='store_true')
    p.add_argument('--messages-only', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    if not args.bridge_dir.is_dir():
        print(f'{RED}directory not found: {args.bridge_dir}{RESET}', file=sys.stderr)
        sys.exit(1)
    if not args.identity.is_file():
        print(f'{RED}identity file not found: {args.identity}{RESET}', file=sys.stderr)
        sys.exit(1)

    ledger_path = args.ledger or Path(__file__).resolve().parent / 'imported.db'
    ledger = ledger_connect(ledger_path)

    if args.dry_run:
        print(f'{YELLOW}DRY RUN — no changes will be made{RESET}\n')

    mem_count = msg_count = 0
    if not args.messages_only:
        print('importing memories...')
        mem_count = import_memories(args.bridge_dir, args.identity, ledger,
                                    dry_run=args.dry_run)
    if not args.memories_only:
        print('importing messages...')
        msg_count = import_messages(args.bridge_dir, args.identity, ledger,
                                    dry_run=args.dry_run)

    ledger.close()
    print(f'\n{mem_count} memories, {msg_count} messages'
          + (' (dry run)' if args.dry_run else ' imported'))


if __name__ == '__main__':
    main()
