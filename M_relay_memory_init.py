"""Relay Memory -- persistent memory store for consent-based AI collaboration.

Usage:
    from relay_memory import save, query, get, update, delete, list_all

    save('session_note', 'reference', 'Work session summary', 'Built converter tool...')
    results = query('converter')
    mem = get('session_note')
    update('session_note', content='Updated content...')
    delete('old_memory')
    all_mems = list_all(type='reference')
"""

from relay_memory.core import save, query, get, update, delete, list_all, stats

__all__ = ['save', 'query', 'get', 'update', 'delete', 'list_all', 'stats']
__version__ = '2.0.0'
