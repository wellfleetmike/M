"""Relay Communications -- structured inter-instance messaging.

Usage:
    from relay_comms import send, receive, broadcast, snap_screen

    send('operator', 'Build complete.', priority='info')
    messages = receive()
    broadcast('System alert.', priority='urgent')
    path = snap_screen(label='dashboard')
"""

from relay_comms.core import send, receive, broadcast, snap_screen, acknowledge, acknowledge_all

__all__ = ['send', 'receive', 'broadcast', 'snap_screen', 'acknowledge', 'acknowledge_all']
__version__ = '1.0.0'
