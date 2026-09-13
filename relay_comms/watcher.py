"""Relay inbox watcher daemon.

Monitors a role's inbox and processes incoming messages.
Non-destructive: reads messages, displays them, then acknowledges.
Speaks messages via espeak-ng when watching the operator inbox.

Run directly:
    python3 -m relay_comms.watcher <role>

Or via CLI:
    python3 -m relay_comms watch --role operator

Or via systemd:
    systemctl start relay-watcher@operator
"""

import sys
import time

from relay_comms.config import detect_role, ensure_dirs, ROLES
from relay_comms.core import receive, acknowledge
from relay_comms.tts import speak

# ANSI
_DIM = '\033[90m'
_RST = '\033[0m'
_PRI = {'info': '\033[32m', 'alert': '\033[33m', 'urgent': '\033[31;1m'}


def watch(role=None, tts=None, interval=0.5):
    """Watch an inbox indefinitely, printing and optionally speaking messages.

    Messages are read non-destructively, displayed, then acknowledged
    (moved to ack/ directory). This prevents message loss from competing
    readers while still keeping the inbox clean.

    Args:
        role:     Role to watch (required for systemd, auto-detect as fallback)
        tts:      Enable TTS (defaults to True for operator, False otherwise)
        interval: Poll interval in seconds
    """
    if role is None:
        role = detect_role()
    if role not in ROLES:
        print(f"Unknown role: {role!r}. Valid: {', '.join(ROLES)}", file=sys.stderr)
        sys.exit(1)

    if tts is None:
        tts = (role == 'operator')

    ensure_dirs()
    print(f"watching: {role} | tts: {'on' if tts else 'off'} | poll: {interval}s", flush=True)
    print("ctrl+c to stop\n", flush=True)

    try:
        while True:
            messages = receive(role=role)
            for msg in messages:
                ts = msg['timestamp'][11:19]
                src = msg['source']
                pri = msg['priority']
                body = msg['body']
                pc = _PRI.get(pri, '')

                print(f"{_DIM}{ts}{_RST} {pc}[{pri}]{_RST} {src} -> {role}: {body}", flush=True)
                if msg.get('attachment'):
                    print(f"  {_DIM}att: {msg['attachment']}{_RST}", flush=True)

                if tts:
                    speak(f"{pri} from {src}: {body}", priority=pri, blocking=True)

                # Acknowledge after display (and TTS if applicable)
                acknowledge(msg, role=role)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == '__main__':
    role_arg = sys.argv[1] if len(sys.argv) > 1 else None
    watch(role=role_arg)
