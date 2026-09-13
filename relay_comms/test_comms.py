#!/usr/bin/env python3
"""Relay Communications -- verification test.

Tests bidirectional messaging, broadcast, relay.log compat, and messages.jsonl.
Run: python3 -m relay_comms.test_comms
"""

import json
import os
import sys
from pathlib import Path

# Force role for testing
os.environ['RELAY_ROLE'] = 'builder'

from relay_comms import send, receive, broadcast, snap_screen
from relay_comms.config import RELAY_LOG, MESSAGE_LOG, INBOX_ROOT, ensure_dirs

PASS = '\033[32mPASS\033[0m'
FAIL = '\033[31mFAIL\033[0m'
results = []


def check(name, condition, detail=''):
    tag = PASS if condition else FAIL
    results.append(condition)
    msg = f"  {tag}  {name}"
    if detail and not condition:
        msg += f" -- {detail}"
    print(msg)


def main():
    print("relay_comms verification test")
    print("=" * 50)

    ensure_dirs()

    # Record relay.log size before test
    log_size_before = RELAY_LOG.stat().st_size if RELAY_LOG.exists() else 0
    jsonl_size_before = MESSAGE_LOG.stat().st_size if MESSAGE_LOG.exists() else 0

    # --- Test 1: send from builder to dispatch ---
    print("\n1. builder -> dispatch")
    msg1 = send(target='dispatch', body='Test message from builder', priority='info')
    check('send returns dict', isinstance(msg1, dict))
    check('has id', 'id' in msg1)
    check('has timestamp', 'timestamp' in msg1)
    check('source is builder', msg1.get('source') == 'builder')
    check('target is dispatch', msg1.get('target') == 'dispatch')

    # Check inbox file exists
    inbox_files = list((INBOX_ROOT / 'dispatch').glob('*.json'))
    check('inbox file created', len(inbox_files) >= 1, f'found {len(inbox_files)} files')

    # --- Test 2: receive on dispatch side ---
    print("\n2. dispatch receives")
    messages = receive(role='dispatch')
    check('receive returns list', isinstance(messages, list))
    check('got at least 1 message', len(messages) >= 1, f'got {len(messages)}')
    if messages:
        check('body matches', messages[-1].get('body') == 'Test message from builder')
        check('source is builder', messages[-1].get('source') == 'builder')

    # Check inbox is empty after consume
    inbox_files_after = list((INBOX_ROOT / 'dispatch').glob('*.json'))
    check('inbox consumed', len(inbox_files_after) == 0, f'{len(inbox_files_after)} files remain')

    # --- Test 3: send from dispatch to builder ---
    print("\n3. dispatch -> builder")
    os.environ['RELAY_ROLE'] = 'dispatch'
    msg2 = send(target='builder', body='Reply from dispatch', priority='alert')
    check('send returns dict', isinstance(msg2, dict))
    check('priority is alert', msg2.get('priority') == 'alert')

    # --- Test 4: receive on builder side ---
    print("\n4. builder receives")
    os.environ['RELAY_ROLE'] = 'builder'
    messages2 = receive(role='builder')
    check('got at least 1 message', len(messages2) >= 1, f'got {len(messages2)}')
    if messages2:
        check('body matches', messages2[-1].get('body') == 'Reply from dispatch')
        check('source is dispatch', messages2[-1].get('source') == 'dispatch')

    # --- Test 5: broadcast ---
    print("\n5. broadcast from sentinel")
    os.environ['RELAY_ROLE'] = 'sentinel'
    results_bc = broadcast(body='Security alert: test broadcast', priority='urgent')
    check('broadcast returns list', isinstance(results_bc, list))
    check('sent to 4 roles (not self)', len(results_bc) == 4, f'sent to {len(results_bc)}')
    targets = {m['target'] for m in results_bc}
    check('dispatch in targets', 'dispatch' in targets)
    check('builder in targets', 'builder' in targets)
    check('sentinel NOT in targets', 'sentinel' not in targets)

    # Receive broadcast on dispatch
    bc_msgs = receive(role='dispatch')
    bc_match = [m for m in bc_msgs if 'test broadcast' in m.get('body', '')]
    check('dispatch got broadcast', len(bc_match) >= 1)

    # --- Test 6: peek mode ---
    print("\n6. peek mode")
    os.environ['RELAY_ROLE'] = 'builder'
    send(target='grok', body='Peek test', source='builder')
    peeked = receive(role='grok', consume=False)
    check('peek returns messages', len(peeked) >= 1)
    still_there = receive(role='grok', consume=False)
    check('messages still in inbox after peek', len(still_there) >= 1)
    # Clean up
    receive(role='grok')

    # --- Test 7: relay.log backward compat ---
    print("\n7. relay.log backward compatibility")
    log_size_after = RELAY_LOG.stat().st_size if RELAY_LOG.exists() else 0
    check('relay.log grew', log_size_after > log_size_before,
          f'{log_size_before} -> {log_size_after}')

    if RELAY_LOG.exists():
        log_tail = RELAY_LOG.read_text().strip().split('\n')[-5:]
        has_arrow = any('->' in line for line in log_tail)
        check('relay.log has arrow format', has_arrow, f'last lines: {log_tail[-1][:60]}')

    # --- Test 8: messages.jsonl ---
    print("\n8. messages.jsonl structured log")
    jsonl_size_after = MESSAGE_LOG.stat().st_size if MESSAGE_LOG.exists() else 0
    check('messages.jsonl grew', jsonl_size_after > jsonl_size_before)

    if MESSAGE_LOG.exists():
        last_line = MESSAGE_LOG.read_text().strip().split('\n')[-1]
        try:
            parsed = json.loads(last_line)
            check('jsonl parses as JSON', True)
            check('has required fields', all(k in parsed for k in ('id', 'timestamp', 'source', 'target', 'priority', 'body')))
        except json.JSONDecodeError:
            check('jsonl parses as JSON', False, f'bad line: {last_line[:60]}')

    # --- Test 9: file attachment reference ---
    print("\n9. file attachment")
    msg_att = send(target='dispatch', body='Check this file', attachment='/tmp/test.txt', source='builder')
    check('attachment in message', msg_att.get('attachment') == '/tmp/test.txt')
    att_msgs = receive(role='dispatch')
    att_match = [m for m in att_msgs if m.get('attachment') == '/tmp/test.txt']
    check('attachment survives send/receive', len(att_match) >= 1)

    # --- Test 10: snap_screen ---
    print("\n10. snap_screen")
    try:
        path = snap_screen(label='test')
        check('screenshot saved', Path(path).exists(), path)
        # Clean up test screenshot
        Path(path).unlink(missing_ok=True)
    except RuntimeError as e:
        check('screenshot (expected fail if no display)', 'DISPLAY' not in os.environ, str(e))

    # --- Test 11: status check ---
    print("\n11. inbox status")
    # Clean up remaining broadcast messages
    for role in ['builder', 'librarian', 'grok']:
        receive(role=role)
    for role_name in ['dispatch', 'builder', 'librarian', 'sentinel', 'grok']:
        inbox = INBOX_ROOT / role_name
        count = len(list(inbox.glob('*.json')))
        check(f'{role_name} inbox clean', count == 0, f'{count} remaining')

    # --- Summary ---
    passed = sum(results)
    total = len(results)
    print(f"\n{'=' * 50}")
    color = '\033[32m' if passed == total else '\033[33m'
    print(f"{color}{passed}/{total} checks passed\033[0m")

    if passed == total:
        print("relay_comms is operational.")
    else:
        print("some checks failed -- review above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
