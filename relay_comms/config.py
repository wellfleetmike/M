"""Relay Communications -- paths, roles, and environment detection."""

import os
from pathlib import Path

RELAY_ROOT = Path(__file__).resolve().parent.parent   # the M repo root; memory, inboxes, logs, snaps all live here
INBOX_ROOT = RELAY_ROOT / 'inboxes'
SNAP_DIR = RELAY_ROOT / 'snaps'
RELAY_LOG = RELAY_ROOT / 'relay.log'
MESSAGE_LOG = RELAY_ROOT / 'messages.jsonl'
ACK_DIRNAME = 'ack'

ROLES = ['dispatch', 'librarian', 'builder', 'sentinel', 'grok']

# Seat directories under ~/Desktop/nu. Mike is the operator and has no seat; he is the bridge.
SEAT_DIRS = {'dispatch': 'dispatch', 'librarian': 'record', 'builder': 'builder', 'sentinel': 'sentinel', 'grok': 'grok'}


def detect_role():
    """Detect current instance role from RELAY_ROLE env var or working directory.

    Checks:
      1. RELAY_ROLE environment variable
      2. Seat directory under ~/Desktop/nu/ in the current working directory path (see SEAT_DIRS)
    Returns 'unknown' if detection fails.
    """
    env_role = os.environ.get('RELAY_ROLE', '').lower().strip()
    if env_role in ROLES:
        return env_role

    cwd = str(Path.cwd())
    relay_base = str(Path.home() / 'Desktop' / 'nu')
    if cwd.startswith(relay_base):
        relative = cwd[len(relay_base):].strip('/')
        first_dir = relative.split('/')[0] if relative else ''
        for role, d in SEAT_DIRS.items():
            if first_dir == d:
                return role

    return 'unknown'


def ensure_dirs():
    """Create all inbox directories, ack subdirectories, and snap directory."""
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    for role in ROLES:
        (INBOX_ROOT / role).mkdir(parents=True, exist_ok=True)
        (INBOX_ROOT / role / ACK_DIRNAME).mkdir(parents=True, exist_ok=True)
