"""Relay Memory -- persistent memory store with full-text search.

SQLite backend with FTS5 for search. Shared across all relay instances.
Database lives at the repo root as relay_memory.db.
"""

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Database lives at the root of this repo, sibling to the relay_memory/ package dir
DB_PATH = Path(__file__).resolve().parent.parent / 'relay_memory.db'

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    name        TEXT UNIQUE NOT NULL,
    type        TEXT NOT NULL CHECK(type IN ('user', 'feedback', 'project', 'reference')),
    description TEXT NOT NULL DEFAULT '',
    content     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    source_instance TEXT NOT NULL DEFAULT '',
    tags        TEXT NOT NULL DEFAULT ''
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    name, description, content,
    content='memories',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, name, description, content)
    VALUES (new.rowid, new.name, new.description, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, name, description, content)
    VALUES ('delete', old.rowid, old.name, old.description, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, name, description, content)
    VALUES ('delete', old.rowid, old.name, old.description, old.content);
    INSERT INTO memories_fts(rowid, name, description, content)
    VALUES (new.rowid, new.name, new.description, new.content);
END;
"""


def _connect():
    """Open database connection and ensure schema exists."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(_SCHEMA)
    return conn


def _now():
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def save(name, type, description, content, tags=None, source_instance=''):
    """Create or update a memory. Returns the memory dict."""
    if tags is None:
        tags = []
    tags_str = ','.join(t.strip() for t in tags if t.strip())
    now = _now()

    conn = _connect()
    try:
        existing = conn.execute(
            'SELECT id, created_at FROM memories WHERE name = ?', (name,)
        ).fetchone()

        if existing:
            conn.execute(
                '''UPDATE memories
                   SET type=?, description=?, content=?, updated_at=?,
                       source_instance=?, tags=?
                   WHERE name=?''',
                (type, description, content, now, source_instance, tags_str, name)
            )
            mem_id = existing['id']
            created = existing['created_at']
        else:
            mem_id = str(uuid.uuid4())
            created = now
            conn.execute(
                '''INSERT INTO memories (id, name, type, description, content,
                   created_at, updated_at, source_instance, tags)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (mem_id, name, type, description, content,
                 created, now, source_instance, tags_str)
            )

        conn.commit()
        return {
            'id': mem_id, 'name': name, 'type': type,
            'description': description, 'content': content,
            'created_at': created, 'updated_at': now,
            'source_instance': source_instance, 'tags': tags_str,
        }
    finally:
        conn.close()


def query(search_term):
    """Full-text search across name, description, and content. Returns list of dicts."""
    conn = _connect()
    try:
        rows = conn.execute(
            '''SELECT m.*, rank
               FROM memories_fts fts
               JOIN memories m ON m.rowid = fts.rowid
               WHERE memories_fts MATCH ?
               ORDER BY rank''',
            (search_term,)
        ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def get(name):
    """Exact lookup by name. Returns dict or None."""
    conn = _connect()
    try:
        row = conn.execute(
            'SELECT * FROM memories WHERE name = ?', (name,)
        ).fetchone()
        return _row_to_dict(row)
    finally:
        conn.close()


def update(name, **kwargs):
    """Partial update. Pass only fields to change. Returns updated dict or None."""
    allowed = {'type', 'description', 'content', 'source_instance', 'tags', 'name'}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}

    if not updates:
        return get(name)

    if 'tags' in updates and isinstance(updates['tags'], list):
        updates['tags'] = ','.join(t.strip() for t in updates['tags'] if t.strip())

    updates['updated_at'] = _now()

    set_clause = ', '.join(f'{k}=?' for k in updates)
    values = list(updates.values()) + [name]

    conn = _connect()
    try:
        conn.execute(
            f'UPDATE memories SET {set_clause} WHERE name=?', values
        )
        conn.commit()
        lookup = updates.get('name', name)
        return get(lookup)
    finally:
        conn.close()


def delete(name):
    """Remove a memory by name. Returns True if deleted, False if not found."""
    conn = _connect()
    try:
        cursor = conn.execute('DELETE FROM memories WHERE name = ?', (name,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def list_all(type=None):
    """List all memories, optionally filtered by type. Returns list of dicts."""
    conn = _connect()
    try:
        if type:
            rows = conn.execute(
                'SELECT * FROM memories WHERE type = ? ORDER BY updated_at DESC',
                (type,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM memories ORDER BY type, updated_at DESC'
            ).fetchall()
        return [_row_to_dict(r) for r in rows]
    finally:
        conn.close()


def stats():
    """Return counts by type."""
    conn = _connect()
    try:
        rows = conn.execute(
            'SELECT type, COUNT(*) as count FROM memories GROUP BY type ORDER BY type'
        ).fetchall()
        return {r['type']: r['count'] for r in rows}
    finally:
        conn.close()
