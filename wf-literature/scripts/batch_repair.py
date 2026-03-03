"""Batch repair pipeline for all workflow-compositions.

Runs repair → cleanup → fetch → validate across all workflow directories.

Usage:
    python3 batch_repair.py --base-dir ./workflow-compositions --steps metadata,cleanup,fetch,validate
    python3 batch_repair.py --base-dir ./workflow-compositions --steps metadata --dry-run
    python3 batch_repair.py --base-dir ./workflow-compositions --workflows WB005,WB030
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent

ALL_STEPS = ("metadata", "cleanup", "fetch", "validate")


def _find_workflows(base_dir: Path, filter_ids: list[str] | None = None) -> list[Path]:
    """Find all workflow directories (WB* and WT*) under base_dir."""
    dirs = sorted(
        d for d in base_dir.iterdir()
        if d.is_dir() and (d.name.startswith("WB") or d.name.startswith("WT"))
    )
    if filter_ids:
        ids_set = set(filter_ids)
        dirs = [d for d in dirs if d.name.split("_")[0] in ids_set]
    return dirs


def _has_paper_list(wf_dir: Path) -> bool:
    return (wf_dir / "01_papers" / "paper_list.json").exists()


def run_metadata_repair(wf_dir: Path, dry_run: bool) -> dict:
    """Run repair_paper_metadata on a single workflow."""
    from repair_paper_metadata import repair_paper_list

    paper_list = wf_dir / "01_papers" / "paper_list.json"
    if not paper_list.exists():
        return {"skipped": True, "reason": "no paper_list.json"}
    return repair_paper_list(paper_list, dry_run=dry_run, verbose=True)


def run_cleanup(wf_dir: Path, dry_run: bool) -> dict:
    """Run cleanup_abstract_fulltexts on a single workflow."""
    from cleanup_abstract_fulltexts import cleanup_fulltexts

    return cleanup_fulltexts(wf_dir, backup=True, dry_run=dry_run, verbose=True)


def run_fetch(wf_dir: Path, dry_run: bool) -> dict:
    """Run fetch_fulltext on a single workflow."""
    if dry_run:
        paper_list = wf_dir / "01_papers" / "paper_list.json"
        if not paper_list.exists():
            return {"skipped": True}
        data = json.loads(paper_list.read_text(encoding="utf-8"))
        papers = data.get("papers", [])
        with_pmcid = sum(1 for p in papers if p.get("pmcid"))
        return {"dry_run": True, "total": len(papers), "with_pmcid": with_pmcid}

    from fetch_fulltext import process_papers

    paper_list = wf_dir / "01_papers" / "paper_list.json"
    if not paper_list.exists():
        return {"skipped": True, "reason": "no paper_list.json"}

    output_dir = wf_dir / "01_papers" / "full_texts"
    output_dir.mkdir(parents=True, exist_ok=True)
    return process_papers(paper_list, wf_dir, pending_only=False)


def run_validate(wf_dir: Path, dry_run: bool) -> dict:
    """Run validate_papers on a single workflow."""
    from validate_papers import run_full_validation

    paper_list = wf_dir / "01_papers" / "paper_list.json"
    if not paper_list.exists():
        return {"skipped": True, "reason": "no paper_list.json"}

    ft_dir = wf_dir / "01_papers" / "full_texts"
    return run_full_validation(paper_list, ft_dir, check_pmid=False)


STEP_RUNNERS = {
    "metadata": run_metadata_repair,
    "cleanup": run_cleanup,
    "fetch": run_fetch,
    "validate": run_validate,
}


def _format_metadata_result(result: dict) -> str:
    if result.get("skipped"):
        return "skipped"
    return (f"{result.get('repaired', 0)} repaired, "
            f"{result.get('cleared', 0)} cleared, "
            f"{result.get('clean', 0)} clean")


def _format_cleanup_result(result: dict) -> str:
    return (f"{result.get('abstract_only', 0)} removed, "
            f"{result.get('kept', 0)} kept")


def _format_fetch_result(result: dict) -> str:
    if result.get("skipped"):
        return "skipped"
    if result.get("dry_run"):
        return f"{result.get('with_pmcid', 0)}/{result.get('total', 0)} with PMCID"
    return (f"{result.get('processed', 0)} fetched, "
            f"{result.get('failed', 0)} failed, "
            f"{result.get('no_pmcid', 0)} no_pmcid")


def _format_validate_result(result: dict) -> str:
    if result.get("skipped"):
        return "skipped"
    return (f"{result.get('critical_count', '?')} critical, "
            f"{result.get('warning_count', '?')} warnings")


STEP_FORMATTERS = {
    "metadata": _format_metadata_result,
    "cleanup": _format_cleanup_result,
    "fetch": _format_fetch_result,
    "validate": _format_validate_result,
}


def run_batch(
    base_dir: Path,
    steps: list[str],
    dry_run: bool = False,
    filter_ids: list[str] | None = None,
) -> dict:
    """Run the repair pipeline across all workflows.

    Returns overall summary dict.
    """
    workflows = _find_workflows(base_dir, filter_ids)
    total = len(workflows)

    print(f"\n{'='*70}", flush=True)
    mode = "DRY-RUN" if dry_run else "LIVE"
    print(f"[batch_repair] {mode} — {total} workflows, steps: {','.join(steps)}",
          flush=True)
    print(f"{'='*70}\n", flush=True)

    overall: dict = {
        "total_workflows": total,
        "steps": steps,
        "dry_run": dry_run,
        "results": {},
        "errors": [],
    }

    for i, wf_dir in enumerate(workflows, 1):
        wf_id = wf_dir.name.split("_")[0]

        if not _has_paper_list(wf_dir):
            print(f"[{i}/{total}] {wf_id} — no paper_list.json, skipping",
                  flush=True)
            overall["results"][wf_id] = {"skipped": True}
            continue

        print(f"\n[{i}/{total}] {wf_dir.name}", flush=True)
        print(f"  {'-'*50}", flush=True)

        wf_results: dict = {}

        for step in steps:
            runner = STEP_RUNNERS.get(step)
            if not runner:
                print(f"  Unknown step: {step}", flush=True)
                continue

            try:
                print(f"  [{step}] ...", end=" ", flush=True)
                t0 = time.time()
                result = runner(wf_dir, dry_run)
                elapsed = time.time() - t0

                formatter = STEP_FORMATTERS.get(step, str)
                summary = formatter(result)
                print(f"{summary} ({elapsed:.1f}s)", flush=True)

                wf_results[step] = result
            except Exception as e:
                print(f"ERROR: {e}", flush=True)
                wf_results[step] = {"error": str(e)}
                overall["errors"].append({
                    "workflow": wf_id,
                    "step": step,
                    "error": str(e),
                })

        overall["results"][wf_id] = wf_results

    _print_final_summary(overall, steps)
    return overall


def _print_final_summary(overall: dict, steps: list[str]) -> None:
    print(f"\n{'='*70}", flush=True)
    print("[FINAL SUMMARY]", flush=True)
    print(f"{'='*70}", flush=True)

    results = overall["results"]
    total = overall["total_workflows"]
    errors = overall["errors"]

    if "metadata" in steps:
        total_repaired = sum(
            r.get("metadata", {}).get("repaired", 0)
            for r in results.values() if isinstance(r, dict)
        )
        total_cleared = sum(
            r.get("metadata", {}).get("cleared", 0)
            for r in results.values() if isinstance(r, dict)
        )
        print(f"  metadata: {total_repaired} repaired, {total_cleared} cleared",
              flush=True)

    if "cleanup" in steps:
        total_removed = sum(
            r.get("cleanup", {}).get("abstract_only", 0)
            for r in results.values() if isinstance(r, dict)
        )
        print(f"  cleanup: {total_removed} abstract-only files removed", flush=True)

    if "fetch" in steps:
        total_fetched = sum(
            r.get("fetch", {}).get("processed", 0)
            for r in results.values() if isinstance(r, dict)
        )
        total_failed = sum(
            r.get("fetch", {}).get("failed", 0)
            for r in results.values() if isinstance(r, dict)
        )
        print(f"  fetch: {total_fetched} full texts downloaded, "
              f"{total_failed} failed", flush=True)

    if "validate" in steps:
        total_critical = sum(
            r.get("validate", {}).get("critical_count", 0)
            for r in results.values() if isinstance(r, dict)
        )
        total_warnings = sum(
            r.get("validate", {}).get("warning_count", 0)
            for r in results.values() if isinstance(r, dict)
        )
        print(f"  validate: {total_critical} critical, "
              f"{total_warnings} warnings", flush=True)

    if errors:
        print(f"\n  ERRORS: {len(errors)} failures across {total} workflows",
              flush=True)
        for e in errors[:10]:
            print(f"    {e['workflow']}/{e['step']}: {e['error']}", flush=True)

    print(f"\nProcessed {total} workflows.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Batch repair pipeline for workflow-compositions")
    parser.add_argument("--base-dir", type=Path, required=True,
                        help="Base directory containing workflow folders")
    parser.add_argument("--steps", type=str, default="metadata,cleanup,fetch,validate",
                        help="Comma-separated steps: metadata,cleanup,fetch,validate")
    parser.add_argument("--workflows", type=str, default="",
                        help="Comma-separated workflow IDs to process (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without modifying files")
    args = parser.parse_args()

    if not args.base_dir.exists():
        print(f"ERROR: {args.base_dir} not found", file=sys.stderr)
        sys.exit(1)

    steps = [s.strip() for s in args.steps.split(",") if s.strip()]
    for s in steps:
        if s not in ALL_STEPS:
            print(f"ERROR: unknown step '{s}'. Valid: {','.join(ALL_STEPS)}",
                  file=sys.stderr)
            sys.exit(1)

    filter_ids = [w.strip() for w in args.workflows.split(",") if w.strip()] or None

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))

    run_batch(args.base_dir, steps, dry_run=args.dry_run, filter_ids=filter_ids)


if __name__ == "__main__":
    main()
