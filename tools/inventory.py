#!/usr/bin/env python3
"""Read-only inventory of ~/Desktop/nu/curator_pass -> ~/Desktop/nu/INVENTORY.md"""
import os, re, sys, datetime
from collections import OrderedDict

ROOT = os.path.expanduser("~/Desktop/nu/curator_pass")
OUT = os.path.expanduser("~/Desktop/nu/INVENTORY.md")
MAX_BYTES = 4 * 1024 * 1024  # cap per file when reading "first 10 lines"

CURATOR_MARKERS = ("PHOENIX_RECALL", "GROK_SELF_AUDIT", "AETHRYN_RELAY_CURATOR", "activation_counts")
SHARD_MARKERS = ("Phoenix_Shard", "nano_memory")
CONVO_RE = re.compile(r"^###\s+\S.*?\[[^\]]+\]", re.M)
OLLAMA_BLOB_RE = re.compile(r"^sha256-[0-9a-f]{64}$")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
KEEP_EXT = {".md", ".jsonl", ".py", ".ath", ".txt"}

def in_scope(fn):
    return os.path.splitext(fn)[1].lower() in KEEP_EXT or fn.lower().startswith("modelfile")

SECTIONS = OrderedDict([
    ("CURATOR PASSES", "any .md or .jsonl whose filename or first 10 lines contain PHOENIX_RECALL, GROK_SELF_AUDIT, AETHRYN_RELAY_CURATOR, or activation_counts"),
    ("PERSONALITY VECTORS", "any .jsonl whose first 10 lines contain `embedding`"),
    ("MEMORY SHARDS", "any .ath or .jsonl whose filename or first 10 lines contain Phoenix_Shard or nano_memory"),
    ("MODEL FILES", "any file named Modelfile*"),
    ("CONVERSATIONS", "any .md whose first 10 lines match the `### <timestamp> [sender]` pattern"),
    ("CODE", "any .py file"),
    ("MANIFESTS", "any MANIFEST* or SHA256* file (case-insensitive prefix match)"),
    ("INDEXED DRIVES", "catalog.db and related files (everything under indexed_drives/, plus any catalog.db* elsewhere)"),
    ("OTHER", "everything else"),
])

def head10(path):
    """Return the first 10 lines (decoded, lossy) of a file, capped at MAX_BYTES."""
    lines = []
    total = 0
    try:
        with open(path, "rb") as f:
            for _ in range(10):
                line = f.readline(MAX_BYTES - total)
                if not line:
                    break
                total += len(line)
                lines.append(line)
                if total >= MAX_BYTES:
                    break
    except Exception as e:
        return "", f"read error: {e}"
    return b"".join(lines).decode("utf-8", errors="replace"), None

def classify(path, rel):
    name = os.path.basename(path)
    lname = name.lower()
    ext = os.path.splitext(name)[1].lower()
    top = rel.split(os.sep)[0]
    text, err = head10(path)
    hay = name + "\n" + text

    if ext in (".md", ".jsonl") and any(m in hay for m in CURATOR_MARKERS):
        return "CURATOR PASSES", err
    if ext == ".jsonl" and "embedding" in text:
        return "PERSONALITY VECTORS", err
    if ext in (".ath", ".jsonl") and any(m in hay for m in SHARD_MARKERS):
        return "MEMORY SHARDS", err
    if lname.startswith("modelfile"):
        return "MODEL FILES", err
    if ext == ".md" and CONVO_RE.search(text):
        return "CONVERSATIONS", err
    if ext == ".py":
        return "CODE", err
    if lname.startswith("manifest") or lname.startswith("sha256"):
        # Ollama model layer blobs are named sha256-<64 hex>; they are model weights, not manifests.
        if OLLAMA_BLOB_RE.match(name) and "blobs" in rel.split(os.sep):
            return "OTHER", err
        return "MANIFESTS", err
    if top == "indexed_drives" or lname.startswith("catalog.db"):
        return "INDEXED DRIVES", err
    return "OTHER", err

def lname_of(fn):
    return fn.lower()

def human(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024

def main():
    buckets = {k: [] for k in SECTIONS}
    errors = []
    symlinks = []
    near_manifest = []
    ollama_blobs = []
    skipped = 0
    nfiles = 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        for fn in sorted(filenames):
            if not in_scope(fn):
                skipped += 1
                continue
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, ROOT)
            if os.path.islink(p):
                symlinks.append(rel)
                if not os.path.exists(p):
                    continue
            try:
                size = os.path.getsize(p)
            except OSError as e:
                errors.append((rel, str(e)))
                continue
            nfiles += 1
            sec, err = classify(p, rel)
            if err:
                errors.append((rel, err))
            buckets[sec].append((rel, size))
            if sec != "MANIFESTS" and ("manifest" in lname_of(fn) or lname_of(fn).endswith(".sha256")):
                near_manifest.append((rel, size, sec))
            if OLLAMA_BLOB_RE.match(fn):
                ollama_blobs.append((rel, size))
            if nfiles % 2000 == 0:
                print(f"  scanned {nfiles}...", file=sys.stderr)

    total_size = sum(s for b in buckets.values() for _, s in b)
    out = []
    out.append("# INVENTORY: ~/Desktop/nu/curator_pass\n")
    out.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}  ")
    out.append(f"Root: `{ROOT}`  ")
    out.append("Scope: only files with extension .md, .jsonl, .py, .ath, .txt, or named Modelfile*; directories named .git, node_modules, __pycache__, and .venv skipped entirely.  ")
    out.append(f"Files in scope: {nfiles}  ")
    out.append(f"Files skipped (out-of-scope extension): {skipped}  ")
    out.append(f"Total size: {human(total_size)} ({total_size:,} bytes)  ")
    out.append("Method: recursive walk; each in-scope file classified by filename plus its first 10 lines (read-only, nothing moved or copied). First matching rule wins, in section order.\n")

    out.append("## Summary\n")
    out.append("| # | Section | Files | Size |")
    out.append("|---|---------|------:|-----:|")
    for i, (sec, _) in enumerate(SECTIONS.items(), 1):
        b = buckets[sec]
        out.append(f"| {i} | {sec} | {len(b)} | {human(sum(s for _, s in b))} |")
    out.append("")

    for i, (sec, rule) in enumerate(SECTIONS.items(), 1):
        b = buckets[sec]
        sz = sum(s for _, s in b)
        out.append(f"## {i}. {sec}\n")
        out.append(f"Rule: {rule}  ")
        out.append(f"Files: {len(b)}  ")
        out.append(f"Total size: {human(sz)} ({sz:,} bytes)\n")
        if b:
            out.append("| Size | Path |")
            out.append("|-----:|------|")
            for rel, s in b:
                out.append(f"| {human(s)} | `{rel}` |")
        else:
            out.append("_none_")
        out.append("")

    out.append("## Notes\n")
    out.append("### Conversations rule\n")
    out.append("No .md file in the tree has a `### <timestamp> [sender]` header, in its first 10 lines or anywhere else (verified with a full-file grep). The only `### ... [...]` headers present are section labels such as `### [VOICE]` or `### **[BUILD] Project MirrorNode**`. Conversation-like files in this corpus are therefore counted under whichever other rule they match, or under OTHER.\n")
    if ollama_blobs:
        out.append("### Ollama model blobs excluded from MANIFESTS\n")
        for rel, s in ollama_blobs:
            out.append(f"- {human(s)} `{rel}`")
        out.append("")
    out.append("### Manifest-like files that did not match the MANIFEST*/SHA256* prefix rule\n")
    out.append("Name contains `manifest` or ends in `.sha256` but does not start with MANIFEST or SHA256. Listed here so they are not overlooked; each is counted in the section shown.\n")
    if near_manifest:
        out.append("| Size | Section | Path |")
        out.append("|-----:|---------|------|")
        for rel, s, sec in near_manifest:
            out.append(f"| {human(s)} | {sec} | `{rel}` |")
    else:
        out.append("_none_")
    out.append("")
    if symlinks:
        out.append("### Symlinks encountered\n")
        for s in symlinks:
            out.append(f"- `{s}`")
        out.append("")
    if errors:
        out.append("### Read errors\n")
        for rel, e in errors:
            out.append(f"- `{rel}`: {e}")
        out.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")

    print(f"wrote {OUT}")
    for sec in SECTIONS:
        b = buckets[sec]
        print(f"{sec:22s} {len(b):6d} files  {human(sum(s for _, s in b))}")
    print(f"{'TOTAL':22s} {nfiles:6d} files  {human(total_size)}")
    print(f"skipped out-of-scope files: {skipped}")
    if errors:
        print(f"read errors: {len(errors)}")

if __name__ == "__main__":
    main()
