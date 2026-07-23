#!/usr/bin/env python3
"""export_bridge.py -- Export local relay_memory into the encrypted GitHub bridge.

Writes each memory as an age-encrypted JSON file under
relay_bridge/memories/<tier>/<name>.json.age, encrypted to every public key
in relay_bridge/recipients/<tier>.txt. Plaintext never touches the repo.

The memory's tier comes from its tags: a tag 'tier:session' puts it in the
session tier; no tier tag means the default tier (sovereign).

Usage:
    python3 export_bridge.py /path/to/bridge_repo/relay_bridge
    python3 export_bridge.py ... --tier-default sovereign
    python3 export_bridge.py ... --only name1 name2
    python3 export_bridge.py ... --dry-run

After export: cd into the repo, git add/commit/push.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bridge_crypt

GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
DIM = '\033[90m'
RESET = '\033[0m'


def memory_tier(mem, default):
    for t in (mem.get('tags') or '').split(','):
        t = t.strip()
        if t.startswith('tier:'):
            return t.split(':', 1)[1]
    return default


def main():
    p = argparse.ArgumentParser(description='Export relay_memory to encrypted bridge')
    p.add_argument('bridge_dir', type=Path)
    p.add_argument('--tier-default', default='sovereign',
                   help='tier for memories without a tier: tag (default: sovereign)')
    p.add_argument('--only', nargs='*', help='export only these memory names')
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()

    try:
        from relay_memory import list_all
    except ImportError:
        print(f'{RED}relay_memory not importable — is it on PYTHONPATH?{RESET}',
              file=sys.stderr)
        sys.exit(1)

    rec_dir = args.bridge_dir / 'recipients'
    if not rec_dir.is_dir():
        print(f'{RED}no recipients/ dir in {args.bridge_dir} — create '
              f'recipients/<tier>.txt with age public keys first{RESET}',
              file=sys.stderr)
        sys.exit(1)

    tiers = {}  # tier name -> recipient list
    for f in rec_dir.glob('*.txt'):
        tiers[f.stem] = bridge_crypt.read_recipients(f)
    if not tiers:
        print(f'{RED}no recipient files in {rec_dir}{RESET}', file=sys.stderr)
        sys.exit(1)

    print(f'tiers: ' + ', '.join(f'{t} ({len(r)} keys)' for t, r in tiers.items()))
    if args.dry_run:
        print(f'{YELLOW}DRY RUN — nothing will be written{RESET}\n')

    memories = list_all()
    if args.only:
        wanted = set(args.only)
        memories = [m for m in memories if m['name'] in wanted]
        missing = wanted - {m['name'] for m in memories}
        for name in sorted(missing):
            print(f'  {YELLOW}not found:{RESET} {name}')

    count = skipped = 0
    for m in memories:
        tier = memory_tier(m, args.tier_default)
        if tier not in tiers:
            print(f'  {RED}skip:{RESET} {m["name"]} — unknown tier {tier!r} '
                  f'(no recipients/{tier}.txt)')
            skipped += 1
            continue

        out_dir = args.bridge_dir / 'memories' / tier
        out_path = out_dir / f'{m["name"]}.json.age'
        payload = json.dumps(m, indent=2, sort_keys=True).encode()

        if args.dry_run:
            print(f'  {DIM}would write:{RESET} {out_path.relative_to(args.bridge_dir)}'
                  f' ({len(payload)} bytes plaintext)')
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(bridge_crypt.encrypt(payload, tiers[tier]))
            print(f'  {GREEN}wrote:{RESET} {out_path.relative_to(args.bridge_dir)}')
        count += 1

    print(f'\n{count} exported, {skipped} skipped'
          + (' (dry run)' if args.dry_run else ''))
    if not args.dry_run and count:
        print(f'{DIM}next: git -C {args.bridge_dir.parent} add -A '
              f'&& git commit && git push{RESET}')


if __name__ == '__main__':
    main()
