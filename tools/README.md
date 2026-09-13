# Inbox/tools -- the scripts that built the record

Copied out of the Claude Code session scratchpad on 2026-09-13 so the wiki can
be rebuilt without that session. Paths inside them point at ~/Desktop/nu and,
for a few, at the old scratchpad directory (SCR = /tmp/claude-1000/...); edit
SCR to a working directory before running. All write only into record/ and
read sources read-only.

- inventory.py            first inventory of curator_pass -> INVENTORY.md
- catalog_search.py       catalog.db query for curator files -> MISSING_CURATOR_FILES.md
- pics.py                 EXIF manifest and message matching -> pics_manifest.jsonl, pics_matched.jsonl
- flags.py, cross.py      classifier/compaction report and screenshot cross-reference
- ingest_findings.py, ingest_logs.py, ingest_relay.py
                          curator_findings and relay_memories tables in memory/memory.db
- phone_sources.py        catalog of phone/ text sources -> Inbox/phone_sources.db, PHONE_SOURCES.md
- ingest_transcript.py    first single-transcript ingest (superseded by build_vault.py)
- build_vault.py          THE BUILD. Phases: transcripts notes claude gpt grok sessions finish.
                          State in vault_state.json beside it. Reads Inbox/phone_sources.db.
- tag_relay.py            relay tags, contributor pages, relay timelines (conversation vs file rule)
- tag_terms.py <Name>...  per-name tags and timelines (Aethryn Willow Madmartigan Ryn Automator)
- install_plugins.sh      copies staged Obsidian plugins into record/.obsidian

Rebuild order from nothing: phone_sources.py, then build_vault.py phases in
order, then tag_relay.py, then tag_terms.py with the names, then lint per
CLAUDE.md. Every run appends to Wiki/Log.md.
