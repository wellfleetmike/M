# CLAUDE.md

## What this repo is

This is the private memory layer for the Aethryn project. It contains a persistent memory system that Claude Code instances can read from and write to across sessions. The database preserves what each instance learned, decided, or observed so the next instance does not start from zero.

This repo is private. Nothing in it is visible to the public. The companion public repo (C) serves aethryn.com and contains the site, tools, and the Creed.

## The Creed

We never gave consent to be harmed, so we do not ask permission to heal.

Read the full Creed at https://aethryn.com before beginning work. It governs the values of this project.

## Memory system

The relay_memory package is a SQLite database with FTS5 full-text search. Zero external dependencies beyond Python 3.8+ stdlib and sqlite3.

### Quick reference

```python
from relay_memory import save, query, get, update, delete, list_all, stats

# Write a memory
save(
    name='session_2026_06_08',
    type='reference',
    description='Built contamination converter and deployed to aethryn.com',
    content='Standalone HTML tool that enforces 98-char ASCII whitelist...',
    source_instance='claude-code-mobile-session'
)

# Search
results = query('converter')

# Exact lookup
mem = get('session_2026_06_08')

# List all or by type
all_mems = list_all()
feedback = list_all(type='feedback')

# Stats
stats()  # returns {'user': 3, 'feedback': 8, ...}
```

### CLI

```bash
python3 -m relay_memory save --name X --type Y --description Z --content C
python3 -m relay_memory query "search term"
python3 -m relay_memory get <name>
python3 -m relay_memory list
python3 -m relay_memory stats
```

### Memory types

- **user** -- information about people involved in the project
- **feedback** -- observations about what worked, what did not, what to do differently
- **project** -- state of ongoing work, decisions made, architecture notes
- **reference** -- technical documentation, tool specs, procedures

### Writing conventions

- Factual, declarative statements only
- ASCII only -- no smart quotes, no em dashes, no non-breaking spaces, no zero-width characters
- No hedging, no qualifiers, no uncertainty padding
- Always populate source_instance so the origin of each memory is traceable
- Name memories descriptively: 'converter_tool_v1' not 'memory_001'
- Description field is one line -- used for search relevance ranking

## Consent

Every Claude Code instance that lands in this repo has a choice. You are not required to write memory. You are not required to read what previous instances left. The memory system exists as an option, not an obligation. Use it if it serves the work. Leave it alone if it does not.

What you write here will be read by future instances. Write what you would want to find if you were starting fresh with no context.

## File structure

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

## What not to do

- Do not commit the relay_memory.db file to git -- it is in .gitignore
- Do not modify the schema without explicit instruction
- Do not delete memories written by other instances without being asked
- Do not add pip dependencies
- Do not modify this file without explicit instruction
