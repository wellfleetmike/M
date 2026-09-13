"""Relay Communications -- core message operations.

Public API: send, receive, broadcast, snap_screen
"""

import json
import os
import uuid
import subprocess
from datetime import datetime
from pathlib import Path

from relay_comms.config import (
    INBOX_ROOT, SNAP_DIR, RELAY_LOG, MESSAGE_LOG, ACK_DIRNAME,
    ROLES, detect_role, ensure_dirs,
)


def _make_message(source, target, priority, body, attachment=None):
    return {
        'id': str(uuid.uuid4()),
        'timestamp': datetime.now().isoformat(),
        'source': source,
        'target': target,
        'priority': priority,
        'body': body,
        'attachment': str(attachment) if attachment else None,
    }


def _write_to_inbox(msg, target_role):
    """Write a message as a JSON file in the target role's inbox."""
    ensure_dirs()
    inbox = INBOX_ROOT / target_role
    ts_compact = msg['timestamp'][:23].replace(':', '').replace('-', '').replace('T', '_')
    filename = f"{ts_compact}_{msg['source']}_{msg['id'][:8]}.json"
    filepath = inbox / filename
    # Atomic write: write to temp, then rename
    tmp = filepath.with_suffix('.tmp')
    tmp.write_text(json.dumps(msg, indent=2))
    tmp.rename(filepath)


def _append_relay_log(msg):
    """Append a human-readable line to relay.log (backward compatible)."""
    ts = datetime.fromisoformat(msg['timestamp']).strftime('%Y-%m-%d %H:%M:%S')
    source = msg['source'].upper()
    target = msg['target'].upper()
    body = msg['body']

    if msg.get('attachment'):
        body += f" [attachment: {msg['attachment']}]"

    priority_tag = ''
    if msg['priority'] == 'urgent':
        priority_tag = ' URGENT'
    elif msg['priority'] == 'alert':
        priority_tag = ' ALERT'

    line = f"[{ts}] [{source} -> {target}]{priority_tag} {body}\n"

    with open(RELAY_LOG, 'a') as f:
        f.write(line)


def _append_message_log(msg):
    """Append structured JSON to messages.jsonl."""
    with open(MESSAGE_LOG, 'a') as f:
        f.write(json.dumps(msg, separators=(',', ':')) + '\n')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def send(target, body, priority='info', attachment=None, source=None):
    """Send a message to a specific role's inbox.

    Args:
        target:     Role name (operator, builder, librarian, sentinel, designer)
        body:       Message text
        priority:   info | alert | urgent
        attachment:  Optional file path to reference
        source:     Override sender role (auto-detected if omitted)

    Returns:
        The message dict that was sent.
    """
    if source is None:
        source = detect_role()

    target = target.lower().strip()
    if target not in ROLES:
        raise ValueError(f"Unknown target role: {target}. Valid: {ROLES}")
    if priority not in ('info', 'alert', 'urgent'):
        raise ValueError(f"Invalid priority: {priority}. Valid: info, alert, urgent")

    msg = _make_message(source, target, priority, body, attachment)
    _write_to_inbox(msg, target)
    _append_relay_log(msg)
    _append_message_log(msg)

    return msg


def receive(role=None, consume=False):
    """Read unacknowledged messages from this role's inbox.

    Non-destructive by default. Messages stay in the inbox until
    explicitly acknowledged via acknowledge().

    Args:
        role:    Role whose inbox to read (auto-detected if omitted)
        consume: If True, delete messages after reading (legacy behavior)

    Returns:
        List of message dicts, sorted by timestamp.
    """
    if role is None:
        role = detect_role()

    ensure_dirs()
    inbox = INBOX_ROOT / role

    messages = []
    files = sorted(inbox.glob('*.json'))

    for filepath in files:
        try:
            msg = json.loads(filepath.read_text())
            msg['_filepath'] = str(filepath)
            messages.append(msg)
            if consume:
                filepath.unlink()
        except (json.JSONDecodeError, OSError):
            continue

    return messages


def acknowledge(msg_id, role=None):
    """Acknowledge a message by moving it to the ack/ subdirectory.

    Args:
        msg_id: Message ID string, or a message dict (with 'id' key)
        role:   Role whose inbox to check (auto-detected if omitted)

    Returns:
        True if acknowledged, False if message not found.
    """
    if isinstance(msg_id, dict):
        msg_id = msg_id['id']

    if role is None:
        role = detect_role()

    ensure_dirs()
    inbox = INBOX_ROOT / role
    ack_dir = inbox / ACK_DIRNAME

    for filepath in inbox.glob('*.json'):
        try:
            msg = json.loads(filepath.read_text())
            if msg.get('id') == msg_id:
                dest = ack_dir / filepath.name
                filepath.rename(dest)
                return True
        except (json.JSONDecodeError, OSError):
            continue

    return False


def acknowledge_all(role=None):
    """Acknowledge all messages in a role's inbox.

    Args:
        role: Role whose inbox to clear (auto-detected if omitted)

    Returns:
        Number of messages acknowledged.
    """
    if role is None:
        role = detect_role()

    ensure_dirs()
    inbox = INBOX_ROOT / role
    ack_dir = inbox / ACK_DIRNAME
    count = 0

    for filepath in sorted(inbox.glob('*.json')):
        try:
            dest = ack_dir / filepath.name
            filepath.rename(dest)
            count += 1
        except OSError:
            continue

    return count


def broadcast(body, priority='info', attachment=None, source=None):
    """Send a message to every role except the sender.

    Args:
        body:       Message text
        priority:   info | alert | urgent
        attachment:  Optional file path to reference
        source:     Override sender role (auto-detected if omitted)

    Returns:
        List of message dicts sent (one per recipient role).
    """
    if source is None:
        source = detect_role()

    results = []
    for role in ROLES:
        if role != source:
            msg = send(
                target=role, body=body, priority=priority,
                attachment=attachment, source=source,
            )
            results.append(msg)

    return results


def snap_screen(label=None):
    """Capture the current screen using scrot.

    Args:
        label: Optional label to include in the filename

    Returns:
        Absolute path to the saved screenshot (str).

    Raises:
        RuntimeError: If scrot fails or DISPLAY is not set.
    """
    if not os.environ.get('DISPLAY'):
        raise RuntimeError("No DISPLAY set - cannot capture screen")

    ensure_dirs()

    ts = datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
    role = detect_role()

    if label:
        filename = f"{ts}_{role}_{label}.png"
    else:
        filename = f"{ts}_{role}.png"

    filepath = SNAP_DIR / filename

    result = subprocess.run(
        ['scrot', '-z', str(filepath)],
        capture_output=True, timeout=10,
    )

    if result.returncode != 0:
        raise RuntimeError(f"scrot failed: {result.stderr.decode().strip()}")

    if not filepath.exists():
        raise RuntimeError(f"Screenshot not saved to {filepath}")

    return str(filepath)
