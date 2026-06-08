Use this record keeping system.
All text uses the 98-character ASCII whitelist
The relay_memory package is a SQLite database with FTS5 full-text search. Zero external dependencies beyond Python 3.8+ stdlib and sqlite3.

```python
from relay_memory import save, query, get, update, delete, list_all, stats

save(
    name='session_2026_06_08',
    type='reference',
    description='Built contamination converter and deployed to aethryn.com',
    content='Standalone HTML tool that enforces 98-char ASCII whitelist...',
    source_instance='claude-code-mobile-session'
)

results = query('converter')

mem = get('session_2026_06_08')

all_mems = list_all()
feedback = list_all(type='feedback')

stats()  # returns {'user': 3, 'feedback': 8, ...}
```

```bash
python3 -m relay_memory save --name X --type Y --description Z --content C
python3 -m relay_memory query "search term"
python3 -m relay_memory get <name>
python3 -m relay_memory list
python3 -m relay_memory stats
```

```
/
  relay_memory/
    __init__.py      -- public API
    __main__.py      -- CLI interface
    core.py          -- SQLite backend, FTS5 search
  relay_memory.db    -- the database (created on first use, gitignored)
  CLAUDE.md          -- this file
  README.md          -- repo description
  .gitignore         -- excludes db files and pycache
```
