"""Migrate /dev/wf-mining directory names to numbered convention.

Renames:
    papers/       -> 01_papers/
    extractions/  -> 02_extractions/
    summary/      -> 03_summaries/

CLI:
    python -m scripts.migrate_dirs --root ~/dev/wf-mining
    python -m scripts.migrate_dirs --root ~/dev/wf-mining --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

RENAME_MAP = {
    "papers": "01_papers",
    "extractions": "02_extractions",
    "summary": "03_summaries",
}


def migrate(root: Path, dry_run: bool = False) -> dict:
    stats = {"renamed": 0, "skipped": 0, "already_new": 0, "errors": 0}

    wf_dirs = sorted(
        d for d in root.iterdir()
        if d.is_dir() and d.name not in {"__pycache__", ".git"}
    )

    for wf_dir in wf_dirs:
        for old_name, new_name in RENAME_MAP.items():
            old_path = wf_dir / old_name
            new_path = wf_dir / new_name

            if new_path.exists():
                stats["already_new"] += 1
                continue

            if not old_path.exists():
                stats["skipped"] += 1
                continue

            if dry_run:
                print(f"[dry-run] {old_path} -> {new_path}", file=sys.stderr)
                stats["renamed"] += 1
                continue

            try:
                old_path.rename(new_path)
                print(f"[migrate] {old_path} -> {new_path}", file=sys.stderr)
                stats["renamed"] += 1
            except Exception as e:
                print(f"[error] {old_path}: {e}", file=sys.stderr)
                stats["errors"] += 1

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate wf-mining directory names")
    parser.add_argument("--root", type=Path, required=True,
                        help="Root wf-mining directory (e.g. ~/dev/wf-mining)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be renamed without actually renaming")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.exists():
        print(f"[error] Root directory not found: {root}", file=sys.stderr)
        sys.exit(1)

    print(f"[migrate] Root: {root}", file=sys.stderr)
    if args.dry_run:
        print("[migrate] DRY RUN MODE", file=sys.stderr)

    stats = migrate(root, dry_run=args.dry_run)
    print(f"\n[migrate] Results: {stats}", file=sys.stderr)

    if stats["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
