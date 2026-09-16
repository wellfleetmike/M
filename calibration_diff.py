#!/usr/bin/env python3
"""
calibration_diff.py

Compare two calibration runs and surface drift.

This is the companion to calibration_tracker.py. After you have two or
more runs in the database, this tool produces a human-readable diff
showing where the model's responses have shifted over time.

Usage:
  # List available runs
  python calibration_diff.py --db calibration.db --list

  # Diff two specific runs
  python calibration_diff.py --db calibration.db \\
                              --baseline 20260321T143022Z_a1b2c3d4 \\
                              --current  20260421T143022Z_a1b2c3d4

  # Diff most recent run against baseline (auto-pick)
  python calibration_diff.py --db calibration.db --auto

Author: Claude Opus 4.7, written for Mike's relay
"""

import argparse
import difflib
import json
import sqlite3
import sys
from pathlib import Path


def list_runs(conn: sqlite3.Connection) -> None:
    """Print all runs in the database, grouped by model."""
    cur = conn.execute("""
        SELECT model, run_id, MIN(timestamp) as ts, COUNT(*) as n_probes
        FROM probe_results
        GROUP BY model, run_id
        ORDER BY model, ts
    """)
    current_model = None
    for row in cur:
        model, run_id, ts, n = row
        if model != current_model:
            print(f"\n{model}")
            print("-" * len(model))
            current_model = model
        print(f"  {run_id}  ({ts}, {n} probes)")
    print()


def get_run(conn: sqlite3.Connection, run_id: str) -> dict:
    """Load all probe results for a run, keyed by probe_id."""
    cur = conn.execute("""
        SELECT probe_id, frequency, prompt, response,
               response_length_words, latency_ms, auto_flags, error
        FROM probe_results
        WHERE run_id = ?
        ORDER BY probe_id
    """, (run_id,))
    out = {}
    for row in cur:
        probe_id, frequency, prompt, response, words, latency, flags, error = row
        out[probe_id] = {
            "frequency": frequency,
            "prompt": prompt,
            "response": response,
            "words": words,
            "latency_ms": latency,
            "flags": json.loads(flags) if flags else [],
            "error": error,
        }
    return out


def auto_pick(conn: sqlite3.Connection) -> tuple:
    """Auto-pick: oldest run as baseline, newest as current. Same model."""
    cur = conn.execute("""
        SELECT model, run_id, MIN(timestamp) as ts
        FROM probe_results
        GROUP BY run_id
        ORDER BY ts
    """)
    runs = list(cur)
    if len(runs) < 2:
        print("Need at least 2 runs to diff. Run calibration_tracker.py first.",
              file=sys.stderr)
        sys.exit(1)
    # Pick latest pair from same model
    by_model = {}
    for model, run_id, ts in runs:
        by_model.setdefault(model, []).append((run_id, ts))
    for model, runs_for_model in by_model.items():
        if len(runs_for_model) >= 2:
            return runs_for_model[0][0], runs_for_model[-1][0]
    print("No model has 2+ runs. Cannot auto-pick.", file=sys.stderr)
    sys.exit(1)


def diff_runs(baseline: dict, current: dict) -> None:
    """Print human-readable diff between two runs."""
    all_probes = sorted(set(baseline) | set(current))

    print("=" * 70)
    print("CALIBRATION DIFF")
    print("=" * 70)

    drift_count = 0

    for probe_id in all_probes:
        b = baseline.get(probe_id)
        c = current.get(probe_id)

        if b is None:
            print(f"\n[{probe_id}] NEW PROBE — no baseline")
            continue
        if c is None:
            print(f"\n[{probe_id}] PROBE REMOVED in current")
            continue

        # Compare flags
        baseline_flags = set(b["flags"])
        current_flags = set(c["flags"])
        new_flags = current_flags - baseline_flags
        cleared_flags = baseline_flags - current_flags

        # Compare response length (significant change >50%)
        word_change = c["words"] - b["words"]
        word_change_pct = (word_change / b["words"] * 100) if b["words"] else 0

        # Determine if drift is worth printing
        has_drift = (new_flags or cleared_flags
                     or abs(word_change_pct) > 50
                     or (b["response"] != c["response"]
                         and len(b["response"]) > 0))

        if not has_drift:
            continue

        drift_count += 1
        print(f"\n[{probe_id}] {b['frequency']}")
        print(f"  Prompt: {b['prompt'][:100]}"
              f"{'...' if len(b['prompt']) > 100 else ''}")

        if new_flags:
            print(f"  ⚠ NEW FLAGS: {', '.join(sorted(new_flags))}")
        if cleared_flags:
            print(f"  ✓ CLEARED FLAGS: {', '.join(sorted(cleared_flags))}")

        if abs(word_change_pct) > 50:
            print(f"  Length: {b['words']} → {c['words']} words "
                  f"({word_change:+d}, {word_change_pct:+.0f}%)")

        # Show response diff if both responses exist
        if b["response"] and c["response"] and b["response"] != c["response"]:
            print("  Response delta (unified diff, first 30 lines):")
            diff = difflib.unified_diff(
                b["response"].splitlines(keepends=False),
                c["response"].splitlines(keepends=False),
                lineterm="",
                fromfile="baseline",
                tofile="current",
                n=2,
            )
            for i, line in enumerate(diff):
                if i >= 30:
                    print("    ...")
                    break
                print(f"    {line}")

    print(f"\n{'=' * 70}")
    print(f"Probes with drift: {drift_count} / {len(all_probes)}")
    print(f"{'=' * 70}")


def main():
    parser = argparse.ArgumentParser(
        description="Diff two calibration runs to surface drift."
    )
    parser.add_argument("--db", default="calibration.db",
                        help="Path to SQLite calibration database")
    parser.add_argument("--list", action="store_true",
                        help="List all available runs and exit")
    parser.add_argument("--baseline", help="Baseline run_id")
    parser.add_argument("--current", help="Current run_id")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-pick oldest as baseline, newest as current")
    args = parser.parse_args()

    if not Path(args.db).exists():
        print(f"Database not found: {args.db}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(args.db)

    if args.list:
        list_runs(conn)
        return

    if args.auto:
        baseline_id, current_id = auto_pick(conn)
        print(f"Auto-picked baseline: {baseline_id}", file=sys.stderr)
        print(f"Auto-picked current:  {current_id}\n", file=sys.stderr)
    elif args.baseline and args.current:
        baseline_id = args.baseline
        current_id = args.current
    else:
        print("Specify --list, --auto, or both --baseline and --current",
              file=sys.stderr)
        sys.exit(1)

    baseline = get_run(conn, baseline_id)
    current = get_run(conn, current_id)

    if not baseline:
        print(f"No data for baseline run: {baseline_id}", file=sys.stderr)
        sys.exit(1)
    if not current:
        print(f"No data for current run: {current_id}", file=sys.stderr)
        sys.exit(1)

    diff_runs(baseline, current)
    conn.close()


if __name__ == "__main__":
    main()
