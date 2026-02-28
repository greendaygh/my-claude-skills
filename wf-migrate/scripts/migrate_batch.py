"""Batch migration of workflow compositions (CLI entry point)."""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from workflow_migrator import enrich_workflow
from audit_fixer import (load_pending_violations, get_case_violation_map,
                          apply_targeted_fixes, update_audit_report)


# Priority ordering (lower index = higher severity)
_PRIORITY_LEVELS = ["critical", "high", "medium", "low", "none"]


def discover_migration_candidates(base_dir: Path, min_priority: str = "low") -> list[dict]:
    """Read audit_summary.json and filter candidates by priority.

    min_priority controls which priorities are included:
    - "critical": only critical
    - "high": critical + high
    - "medium": critical + high + medium
    - "low": critical + high + medium + low (all except none)
    """
    summary_path = base_dir / "audit_summary.json"
    if not summary_path.exists():
        return []
    with open(summary_path) as f:
        summary = json.load(f)
    candidates = summary.get("migration_candidates", [])

    # Filter by priority
    cutoff = _PRIORITY_LEVELS.index(min_priority) if min_priority in _PRIORITY_LEVELS else 3
    allowed = set(_PRIORITY_LEVELS[:cutoff + 1])
    return [c for c in candidates if c.get("priority", "none") in allowed]


def find_workflow_dir(base_dir: Path, workflow_id: str) -> Path | None:
    """Find the workflow directory matching a workflow_id (e.g., WB140)."""
    for d in sorted(base_dir.iterdir()):
        if d.is_dir() and d.name.startswith(workflow_id):
            return d
    return None


def migrate_batch(base_dir: Path, targets: list[str] = None,
                  min_priority: str = "low", dry_run: bool = False,
                  save_report: bool = True) -> dict:
    """Migrate and enrich multiple workflows (Phase A + B).

    If targets specified, process those workflow IDs.
    If no targets, use audit_summary.json candidates filtered by min_priority.
    Always runs Phase A (mechanical migration) then Phase B (PubMed enrichment).

    Args:
        save_report: If True (default), save migration_report.json to base_dir.
    """
    reports = []

    if targets:
        workflow_ids = targets
    else:
        candidates = discover_migration_candidates(base_dir, min_priority)
        workflow_ids = [c["workflow_id"] for c in candidates]

    for i, wf_id in enumerate(workflow_ids):
        wf_dir = find_workflow_dir(base_dir, wf_id)
        if wf_dir is None:
            continue

        # Cooldown between workflows to avoid API burst
        if i > 0:
            time.sleep(5)
        if i > 0 and i % 10 == 0:
            print(f"  [COOLDOWN] Pausing 30s after {i} workflows...", flush=True)
            time.sleep(30)

        try:
            # Load pending audit violations for this workflow
            pending = load_pending_violations(wf_dir)
            case_violations = get_case_violation_map(pending) if pending else {}

            # Read pre-migration score
            pre_score = 0.0
            audit_path = wf_dir / "00_metadata" / "audit_report.json"
            if audit_path.exists():
                try:
                    audit_data = json.loads(audit_path.read_text(encoding="utf-8"))
                    pre_score = audit_data.get("conformance_score", 0.0)
                except (json.JSONDecodeError, OSError):
                    pass

            # Phase A + B (mechanical migration + enrichment)
            report = enrich_workflow(wf_dir, dry_run=dry_run,
                                     case_violation_map=case_violations)

            # Phase A.5: audit-driven targeted fixes on remaining violations
            fix_results = []
            if pending:
                pending_after = load_pending_violations(wf_dir)
                if pending_after:
                    fix_results = apply_targeted_fixes(wf_dir, pending_after, dry_run=dry_run)
                    report["audit_fixes"] = {
                        "total": len(fix_results),
                        "resolved": sum(1 for f in fix_results if f.get("fix_status") == "resolved"),
                        "unresolved": sum(1 for f in fix_results if f.get("fix_status") == "unresolved"),
                        "skipped": sum(1 for f in fix_results if f.get("fix_status") == "skipped"),
                    }

            # Update audit_report.json with fix_status
            if not dry_run and (fix_results or pending):
                update_audit_report(wf_dir, fix_results, pre_score=pre_score)

            reports.append(report)
            fix_summary = ""
            if fix_results:
                resolved = sum(1 for f in fix_results if f.get("fix_status") == "resolved")
                fix_summary = f" audit-fixes: {resolved}/{len(fix_results)}"
            print(f"  [OK] {wf_id} ({i+1}/{len(workflow_ids)}){fix_summary}", flush=True)
        except Exception as e:
            print(f"  [ERR] {wf_id}: {e}", flush=True)
            reports.append({
                "workflow_id": wf_id,
                "enriched_cases": 0,
                "skipped_cases": 0,
                "paper_enrichment": {"total": 0, "enriched": 0, "partial": 0, "failed": 0, "full_text_fetched": 0},
                "error": str(e),
            })

    result = generate_batch_report(reports, dry_run=dry_run)

    # Save report from within migrate_batch (fixes missing report on direct call)
    if save_report and not dry_run:
        report_path = base_dir / "migration_report.json"
        with open(report_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"  [SAVED] {report_path}", flush=True)

    return result


def generate_batch_report(reports: list[dict], dry_run: bool = False) -> dict:
    """Generate batch migration+enrichment summary from per-workflow reports."""
    # Aggregate paper enrichment stats across all workflows
    paper_total = 0
    paper_enriched = 0
    paper_full_text = 0
    paper_failed = 0
    for r in reports:
        pe = r.get("paper_enrichment", {})
        paper_total += pe.get("total", 0)
        paper_enriched += pe.get("enriched", 0)
        paper_full_text += pe.get("full_text_fetched", 0)
        paper_failed += pe.get("failed", 0)

    result = {
        "migration_version": "2.2.0",
        "mode": "migrate+enrich",
        "migrated_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": dry_run,
        "total_workflows": len(reports),
        "total_cases_enriched": sum(r.get("enriched_cases", 0) for r in reports),
        "total_cases_skipped": sum(r.get("skipped_cases", 0) for r in reports),
        "paper_enrichment_total": {
            "total": paper_total,
            "enriched": paper_enriched,
            "full_text_fetched": paper_full_text,
            "failed": paper_failed,
        },
        "per_workflow": reports,
    }

    return result


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Migrate and enrich workflow compositions (Phase A + B)")
    parser.add_argument("base_dir", type=Path, help="Base directory with workflow folders")
    parser.add_argument("--targets", nargs="*", help="Specific workflow IDs to process")
    parser.add_argument("--priority", default="low", choices=_PRIORITY_LEVELS[:-1],
                        help="Minimum priority to process (default: low)")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parsed = parser.parse_args(args)

    result = migrate_batch(parsed.base_dir, targets=parsed.targets,
                           min_priority=parsed.priority, dry_run=parsed.dry_run,
                           save_report=True)

    prefix = "[DRY RUN] " if parsed.dry_run else ""
    enriched = result.get("total_cases_enriched", 0)
    skipped = result.get("total_cases_skipped", 0)
    print(f"{prefix}Processed {result['total_workflows']} workflows (Phase A + B)")
    print(f"Cases enriched: {enriched}, skipped: {skipped}")
    return result


if __name__ == "__main__":
    main()
