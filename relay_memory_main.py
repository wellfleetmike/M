"""Relay Memory -- CLI interface.

Usage:
    python3 -m relay_memory save --name X --type Y --description Z --content C [--tags a,b] [--source S]
    python3 -m relay_memory query "search term"
    python3 -m relay_memory get <name>
    python3 -m relay_memory list [--type user]
    python3 -m relay_memory delete <name>
    python3 -m relay_memory stats
"""

import argparse
import sys

from relay_memory.core import save, query, get, update, delete, list_all, stats

# ANSI
DIM = '\033[90m'
BOLD = '\033[1m'
GREEN = '\033[32m'
YELLOW = '\033[33m'
CYAN = '\033[36m'
RED = '\033[31m'
RESET = '\033[0m'

TYPE_COLOR = {
    'user': CYAN,
    'feedback': YELLOW,
    'project': GREEN,
    'reference': '\033[35m',
}


def cmd_save(args):
    tags = [t.strip() for t in args.tags.split(',')] if args.tags else []
    mem = save(
        name=args.name, type=args.type,
        description=args.description,
        content=args.content,
        tags=tags, source_instance=args.source or '',
    )
    print(f"{GREEN}saved{RESET} {mem['name']} ({mem['type']})")


def cmd_query(args):
    results = query(args.search_term)
    if not results:
        print('no matches')
        return
    for r in results:
        tc = TYPE_COLOR.get(r['type'], '')
        print(f"  {tc}{r['type']:10s}{RESET} {BOLD}{r['name']}{RESET}")
        print(f"           {DIM}{r['description']}{RESET}")
    print(f"\n{len(results)} result(s)")


def cmd_get(args):
    mem = get(args.name)
    if not mem:
        print(f"not found: {args.name}")
        sys.exit(1)
    tc = TYPE_COLOR.get(mem['type'], '')
    print(f"{BOLD}{mem['name']}{RESET} {tc}[{mem['type']}]{RESET}")
    print(f"{DIM}{mem['description']}{RESET}")
    if mem['tags']:
        print(f"{DIM}tags: {mem['tags']}{RESET}")
    print(f"{DIM}created: {mem['created_at'][:19]}  updated: {mem['updated_at'][:19]}{RESET}")
    if mem['source_instance']:
        print(f"{DIM}source: {mem['source_instance']}{RESET}")
    print()
    print(mem['content'])


def cmd_list(args):
    memories = list_all(type=args.type)
    if not memories:
        print('no memories' + (f' of type {args.type}' if args.type else ''))
        return

    current_type = None
    for m in memories:
        if m['type'] != current_type:
            current_type = m['type']
            tc = TYPE_COLOR.get(current_type, '')
            print(f"\n{tc}{BOLD}{current_type.upper()}{RESET}")

        print(f"  {m['name']:45s} {DIM}{m['description'][:60]}{RESET}")

    print(f"\n{len(memories)} total")


def cmd_delete(args):
    if delete(args.name):
        print(f"{RED}deleted{RESET} {args.name}")
    else:
        print(f"not found: {args.name}")
        sys.exit(1)


def cmd_stats(args):
    s = stats()
    total = 0
    print(f"\n{BOLD}relay_memory{RESET}")
    print("-" * 30)
    for t in ('user', 'feedback', 'project', 'reference'):
        count = s.get(t, 0)
        total += count
        tc = TYPE_COLOR.get(t, '')
        print(f"  {tc}{t:12s}{RESET} {count:4d}")
    print("-" * 30)
    print(f"  {'total':12s} {total:4d}")


def main():
    parser = argparse.ArgumentParser(
        prog='relay_memory',
        description='Relay persistent memory store'
    )
    sub = parser.add_subparsers(dest='command')

    p_save = sub.add_parser('save', help='Create or update a memory')
    p_save.add_argument('--name', required=True)
    p_save.add_argument('--type', required=True,
                        choices=['user', 'feedback', 'project', 'reference'])
    p_save.add_argument('--description', required=True)
    p_save.add_argument('--content', required=True)
    p_save.add_argument('--tags', default='')
    p_save.add_argument('--source', default='')

    p_query = sub.add_parser('query', help='Full-text search')
    p_query.add_argument('search_term')

    p_get = sub.add_parser('get', help='Exact lookup by name')
    p_get.add_argument('name')

    p_list = sub.add_parser('list', help='List all memories')
    p_list.add_argument('--type',
                        choices=['user', 'feedback', 'project', 'reference'])

    p_del = sub.add_parser('delete', help='Delete a memory')
    p_del.add_argument('name')

    sub.add_parser('stats', help='Show counts by type')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handlers = {
        'save': cmd_save,
        'query': cmd_query,
        'get': cmd_get,
        'list': cmd_list,
        'delete': cmd_delete,
        'stats': cmd_stats,
    }
    handlers[args.command](args)


if __name__ == '__main__':
    main()
