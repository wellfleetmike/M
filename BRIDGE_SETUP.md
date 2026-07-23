# Encrypted Relay Bridge — Setup

Git as untrusted transport; age as the trust boundary. GitHub (or any remote)
only ever stores ciphertext. Tiers decide which nodes can read which memories.

## One-time setup

1. Generate an identity per node (POS, laptop, claude-session):

       python3 bridge_crypt.py keygen > relay.key      # keep private, never commit
       # or, with the age binary:  age-keygen -o relay.key

2. In the bridge repo, create tier recipient files (public keys only — these
   ARE committed):

       relay_bridge/recipients/sovereign.txt   # pos + laptop pubkeys
       relay_bridge/recipients/session.txt     # pos + laptop + claude-session pubkeys

3. Add to the repo's .gitignore (plaintext can never leak by accident):

       relay_bridge/**/*.json
       *.key
       relay_memory.db*
       imported.db

## Tiering memories

Tag a memory `tier:session` to put it in the session tier. Untagged memories
default to sovereign. Unknown tiers are skipped loudly at export.

## Daily flow

    # export + push (any node)
    PYTHONPATH=. python3 export_bridge.py /path/to/repo/relay_bridge
    git -C /path/to/repo add -A && git commit -m sync && git push

    # pull + import (any node)
    git -C /path/to/repo pull
    PYTHONPATH=. python3 import_bridge.py /path/to/repo/relay_bridge -i relay.key

Imports are idempotent: a SQLite ledger hashes every processed file, so
re-runs skip unchanged memories and never re-deliver messages. Files outside
your tier are skipped (that's the boundary working).

## Claude-as-node bootstrap (per session)

Provide: a fine-grained PAT (contents read/write, this repo only) and the
session-tier identity. The session can then clone, import its tier, work,
export new memories tagged `tier:session`, and push. Rotate either credential
any time — the session key is one line in recipients/session.txt.

## Key rotation

1. Generate the new identity; add its pubkey to the tier file(s).
2. Re-run export on any sovereign node (re-encrypts everything to the new set).
3. Remove the old pubkey; commit. Old key now opens nothing new.
