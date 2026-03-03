"""Remove abstract-only files from full_texts/ directory.

Detects P*.txt files that contain only abstracts (single-line, < 3000 bytes)
and moves them to a backup directory or deletes them. Updates paper_list.json
to reflect the removal.

Usage:
    python3 cleanup_abstract_fulltexts.py --wf-dir path/to/WB005_* [--backup] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SIZE_THRESHOLD = 3000
SECTION_HEADER = "=== "


def is_abstract_only(filepath: Path) -> bool:
    """Heuristic: abstract-only if single-line AND < SIZE_THRESHOLD bytes
    AND no structured section headers."""
    try:
        size = filepath.stat().st_size
        if size >= SIZE_THRESHOLD:
            content = filepath.read_text(encoding="utf-8", errors="replace")
            if SECTION_HEADER in content:
                return False
            line_count = content.count("\n")
            if line_count >= 5:
                return False
            return True
        content = filepath.read_text(encoding="utf-8", errors="replace")
        if SECTION_HEADER in content:
            return False
        line_count = content.count("\n")
        return line_count <= 1
    except OSError:
        return False


def cleanup_fulltexts(
    wf_dir: Path,
    backup: bool = True,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """Scan full_texts/ for abstract-only files and remove/backup them.

    Returns summary dict with counts and file lists.
    """
    wf_dir = Path(wf_dir)
    ft_dir = wf_dir / "01_papers" / "full_texts"

    stats = {
        "total_files": 0,
        "abstract_only": 0,
        "kept": 0,
        "removed_files": [],
        "kept_files": [],
    }

    if not ft_dir.exists():
        if verbose:
            print(f"  No full_texts/ directory in {wf_dir.name}", flush=True)
        return stats

    txt_files = sorted(ft_dir.glob("P*.txt"))
    stats["total_files"] = len(txt_files)

    backup_dir = ft_dir / "_abstract_backup"

    for f in txt_files:
        if is_abstract_only(f):
            stats["abstract_only"] += 1
            stats["removed_files"].append(f.name)
            if verbose:
                size = f.stat().st_size
                print(f"    {f.name}: abstract-only ({size} bytes) → "
                      f"{'backup' if backup else 'delete'}", flush=True)
            if not dry_run:
                if backup:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(backup_dir / f.name))
                else:
                    f.unlink()
        else:
            stats["kept"] += 1
            stats["kept_files"].append(f.name)

    # Also handle PMID-named files (e.g. 26937682.txt)
    pmid_files = [f for f in ft_dir.glob("*.txt")
                  if f.stem.isdigit() and not f.name.startswith("P")]
    for f in pmid_files:
        stats["total_files"] += 1
        if is_abstract_only(f):
            stats["abstract_only"] += 1
            stats["removed_files"].append(f.name)
            if not dry_run:
                if backup:
                    backup_dir.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(f), str(backup_dir / f.name))
                else:
                    f.unlink()
        else:
            stats["kept"] += 1
            stats["kept_files"].append(f.name)

    _update_paper_list(wf_dir, stats["removed_files"], dry_run, verbose)

    return stats


def _update_paper_list(
    wf_dir: Path,
    removed_files: list[str],
    dry_run: bool,
    verbose: bool,
) -> None:
    """Set has_full_text=false for papers whose full text was removed."""
    if not removed_files:
        return

    paper_list_path = wf_dir / "01_papers" / "paper_list.json"
    if not paper_list_path.exists():
        return

    removed_ids = {Path(f).stem for f in removed_files}

    try:
        data = json.loads(paper_list_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return

    modified = False
    for paper in data.get("papers", []):
        pid = paper.get("paper_id", "")
        if pid in removed_ids:
            if paper.get("has_full_text") is not False:
                paper["has_full_text"] = False
                paper["text_source"] = "needs_refetch"
                modified = True

    if modified and not dry_run:
        paper_list_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if verbose:
            print(f"  Updated paper_list.json: {len(removed_ids)} papers → "
                  f"has_full_text=false", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Remove abstract-only files from full_texts/")
    parser.add_argument("--wf-dir", required=True,
                        help="Workflow directory (e.g. WB005_Nucleotide_Quantification)")
    parser.add_argument("--backup", action="store_true",
                        help="Move to _abstract_backup/ instead of deleting")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying files")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-file messages")
    args = parser.parse_args()

    wf_dir = Path(args.wf_dir)
    if not wf_dir.exists():
        print(f"ERROR: {wf_dir} not found", file=sys.stderr)
        sys.exit(1)

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"[cleanup_abstract_fulltexts] {mode} — {wf_dir.name}", flush=True)

    stats = cleanup_fulltexts(wf_dir, backup=args.backup,
                              dry_run=args.dry_run, verbose=not args.quiet)

    print(f"\n[SUMMARY] total={stats['total_files']} "
          f"abstract_only={stats['abstract_only']} kept={stats['kept']}",
          flush=True)


if __name__ == "__main__":
    main()
