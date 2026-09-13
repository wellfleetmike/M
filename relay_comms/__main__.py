"""Relay Communications -- CLI interface.

Usage:
    python3 -m relay_comms send <target> <body> [-p priority] [-a attachment]
    python3 -m relay_comms receive [-r role] [--consume]
    python3 -m relay_comms ack [-r role] [msg_id | --all]
    python3 -m relay_comms broadcast <body> [-p priority]
    python3 -m relay_comms snap [-l label]
    python3 -m relay_comms watch [-r role] [--no-tts]
    python3 -m relay_comms dashboard [--port 9876]
    python3 -m relay_comms status

Environment:
    RELAY_ROLE  Override role detection (dispatch|librarian|builder|sentinel|grok)
"""

import argparse
import sys
import time

from relay_comms.config import detect_role, INBOX_ROOT, ROLES, ensure_dirs
from relay_comms.core import send, receive, broadcast, snap_screen, acknowledge, acknowledge_all
from relay_comms.tts import speak

# ANSI colors
_C = {
    'info':    '\033[32m',
    'alert':   '\033[33m',
    'urgent':  '\033[31;1m',
    'dim':     '\033[90m',
    'reset':   '\033[0m',
    'bold':    '\033[1m',
    'dispatch':  '\033[36m',
    'librarian': '\033[33m',
    'builder':   '\033[32m',
    'sentinel':  '\033[31m',
    'grok':      '\033[35m',
    'unknown':   '\033[37m',
}


def _fmt_msg(msg, role=None):
    """Format a message for terminal output."""
    ts = msg['timestamp'][11:19]
    src = msg['source']
    tgt = msg['target']
    pri = msg['priority']
    body = msg['body']

    pc = _C.get(pri, '')
    sc = _C.get(src, _C['unknown'])
    tc = _C.get(tgt, _C['unknown'])
    r = _C['reset']
    d = _C['dim']

    line = f"{d}{ts}{r} {sc}{src.upper()}{r}{d}->{r}{tc}{tgt.upper()}{r} {pc}({pri}){r} {body}"
    if msg.get('attachment'):
        line += f"\n       {d}att: {msg['attachment']}{r}"
    return line


def cmd_send(args):
    msg = send(
        target=args.target, body=args.body,
        priority=args.priority, attachment=args.attachment,
    )
    print(f"sent [{msg['priority']}] -> {args.target}")


def cmd_receive(args):
    role = args.role or detect_role()
    messages = receive(role=role, consume=args.consume)
    if not messages:
        print(f"no messages for {role}")
        return

    for msg in messages:
        print(_fmt_msg(msg, role))

    if args.consume:
        print(f"\n{len(messages)} message(s) consumed (deleted)")
    else:
        print(f"\n{len(messages)} message(s) pending -- use 'ack' to acknowledge")


def cmd_ack(args):
    role = args.role or detect_role()
    if args.all:
        count = acknowledge_all(role=role)
        print(f"acknowledged {count} message(s) for {role}")
    elif args.msg_id:
        if acknowledge(args.msg_id, role=role):
            print(f"acknowledged {args.msg_id[:8]}")
        else:
            print(f"message not found: {args.msg_id}")
            sys.exit(1)
    else:
        print("specify --all or a message id")
        sys.exit(1)


def cmd_broadcast(args):
    results = broadcast(body=args.body, priority=args.priority)
    targets = ', '.join(m['target'] for m in results)
    print(f"broadcast [{args.priority}] -> {targets}")


def cmd_snap(args):
    try:
        path = snap_screen(label=args.label)
        print(f"screenshot: {path}")
    except RuntimeError as e:
        print(f"screenshot failed: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_watch(args):
    from relay_comms.watcher import watch
    role = args.role or detect_role()
    use_tts = not args.no_tts
    watch(role=role, tts=use_tts)


def cmd_dashboard(args):
    from relay_comms.dashboard import main as dashboard_main
    dashboard_main(port=args.port)


def cmd_status(args):
    ensure_dirs()
    print("relay inbox status")
    print("-" * 36)
    total = 0
    for role in ROLES:
        inbox = INBOX_ROOT / role
        count = len(list(inbox.glob('*.json')))
        total += count
        indicator = '\033[32m?\033[0m' if count > 0 else '\033[90m?\033[0m'
        print(f"  {indicator} {role:12s} {count:3d} pending")
    print("-" * 36)
    print(f"  total: {total}")


def main():
    parser = argparse.ArgumentParser(prog='relay_comms', description='Relay inter-instance communications')
    sub = parser.add_subparsers(dest='command')

    p_send = sub.add_parser('send', help='Send message to a role')
    p_send.add_argument('target', choices=ROLES)
    p_send.add_argument('body')
    p_send.add_argument('-p', '--priority', default='info', choices=['info', 'alert', 'urgent'])
    p_send.add_argument('-a', '--attachment')

    p_recv = sub.add_parser('receive', help='Read messages from inbox (non-destructive)')
    p_recv.add_argument('-r', '--role')
    p_recv.add_argument('--consume', action='store_true', help='Delete messages after reading (legacy)')

    p_ack = sub.add_parser('ack', help='Acknowledge messages')
    p_ack.add_argument('-r', '--role')
    p_ack.add_argument('msg_id', nargs='?', help='Message ID to acknowledge')
    p_ack.add_argument('--all', action='store_true', help='Acknowledge all pending messages')

    p_bc = sub.add_parser('broadcast', help='Send message to all roles')
    p_bc.add_argument('body')
    p_bc.add_argument('-p', '--priority', default='info', choices=['info', 'alert', 'urgent'])

    p_snap = sub.add_parser('snap', help='Capture screenshot')
    p_snap.add_argument('-l', '--label')

    p_watch = sub.add_parser('watch', help='Watch inbox for messages (TTS for operator)')
    p_watch.add_argument('-r', '--role')
    p_watch.add_argument('--no-tts', action='store_true')

    p_dash = sub.add_parser('dashboard', help='Launch web dashboard')
    p_dash.add_argument('--port', type=int, default=9876)

    sub.add_parser('status', help='Show inbox counts')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    handlers = {
        'send': cmd_send,
        'receive': cmd_receive,
        'ack': cmd_ack,
        'broadcast': cmd_broadcast,
        'snap': cmd_snap,
        'watch': cmd_watch,
        'dashboard': cmd_dashboard,
        'status': cmd_status,
    }
    handlers[args.command](args)


if __name__ == '__main__':
    main()
