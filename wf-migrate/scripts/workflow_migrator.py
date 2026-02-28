"""Full workflow directory migration."""

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from case_migrator import migrate_case_card, is_canonical, enrich_case_card, is_enriched
from metadata_builder import load_paper_list, build_paper_index
from paper_enricher import enrich_paper_list, save_enriched_paper_list, save_paper_fulltext
from report_generator import write_reports


def _log(msg, verbose=True):
    if verbose:
        print(f"  {msg}", file=sys.stderr, flush=True)


# Deprecated → standard statistics field name map
_STATS_RENAME = {
    "total_papers": "papers_analyzed",
    "total_cases": "cases_collected",
    "total_variants": "variants_identified",
    "total_uo_types": "total_uos",
}


def update_statistics(stats: dict) -> tuple[dict, list[str]]:
    """Rename deprecated statistics field names to standard.

    Returns (updated_stats, list of change descriptions).
    """
    updated = {}
    changes = []
    for key, value in stats.items():
        if key in _STATS_RENAME:
            new_key = _STATS_RENAME[key]
            updated[new_key] = value
            changes.append(f"{key} → {new_key}")
        else:
            updated[key] = value
    return updated, changes


_CANONICAL_STAT_FIELDS = {
    "papers_analyzed": 0,
    "cases_collected": 0,
    "variants_identified": 0,
    "total_uos": 0,
    "qc_checkpoints": 0,
    "confidence_score": 0.0,
}


def _compute_stat_defaults(wf_dir: Path) -> dict:
    """Compute sensible defaults for missing statistics fields by counting files."""
    defaults = dict(_CANONICAL_STAT_FIELDS)
    papers_dir = wf_dir / "01_papers"
    if not papers_dir.exists():
        papers_dir = wf_dir / "01_literature"
    pl = papers_dir / "paper_list.json" if papers_dir.exists() else None
    if pl and pl.exists():
        try:
            data = json.loads(pl.read_text(encoding="utf-8"))
            papers = data.get("papers", data) if isinstance(data, dict) else data
            if isinstance(papers, list):
                defaults["papers_analyzed"] = len(papers)
        except (json.JSONDecodeError, OSError):
            pass
    cases_dir = wf_dir / "02_cases"
    if cases_dir.exists():
        defaults["cases_collected"] = len(list(cases_dir.glob("case_C*.json")))
    wf_dir_04 = wf_dir / "04_workflow"
    if wf_dir_04.exists():
        defaults["variants_identified"] = len(list(wf_dir_04.glob("variant_V*.json")))
    return defaults


def migrate_composition_data(comp_data: dict, wf_dir: Path) -> tuple[dict, list[str]]:
    """Migrate composition_data.json to canonical format.

    Transforms:
    - modularity.boundary_inputs/outputs: object array -> string array
    - statistics: rename legacy fields + fill missing canonical fields
    """
    changes: list[str] = []

    mod = comp_data.get("modularity", {})
    for key in ("boundary_inputs", "boundary_outputs"):
        items = mod.get(key, [])
        if items and isinstance(items[0], dict):
            mod[key] = [item.get("name", str(item)) for item in items]
            changes.append(f"{key}: object-to-string ({len(items)} items)")

    stats = comp_data.get("statistics", {})
    stats, rename_changes = update_statistics(stats)
    changes.extend(rename_changes)

    defaults = _compute_stat_defaults(wf_dir)
    for field, default in defaults.items():
        if field not in stats:
            stats[field] = default
            changes.append(f"statistics.{field}: added default {default}")
    comp_data["statistics"] = stats

    return comp_data, changes


def _backup_cases(wf_dir: Path) -> Path:
    """Copy 02_cases/ to _versions/pre_migration/02_cases/.

    Returns the backup dir path.
    """
    backup_dir = wf_dir / "_versions" / "pre_migration"
    cases_src = wf_dir / "02_cases"
    if cases_src.exists():
        backup_cases = backup_dir / "02_cases"
        if not backup_cases.exists():
            shutil.copytree(cases_src, backup_cases)
    return backup_dir


def migrate_workflow(wf_dir: Path, dry_run: bool = False, verbose: bool = True) -> dict:
    """Migrate all case cards in a workflow directory.

    Steps:
    1. Load paper_list.json → build paper index
    2. Load composition_data.json → extract workflow_id
    3. Backup original cases to _versions/pre_migration/
    4. Migrate each case card in 02_cases/
    5. Migrate composition_data.json (statistics + modularity)
    6. Migrate variant files
    7. Write migration report to 00_metadata/migration_report.json

    Args:
        wf_dir: workflow directory path
        dry_run: if True, compute changes but don't write files
        verbose: if True (default), print progress to stderr

    Returns:
        Migration report dict with: workflow_id, migrated_cases, skipped_cases,
        total_changes, composition_data_changes, variant_changes, timestamp
    """
    wf_dir = Path(wf_dir)

    # 1. Load paper index
    paper_data = load_paper_list(wf_dir)
    paper_index = build_paper_index(paper_data)

    # 2. Load composition_data.json
    comp_path = wf_dir / "composition_data.json"
    comp_data = {}
    if comp_path.exists():
        with open(comp_path, encoding="utf-8") as f:
            comp_data = json.load(f)
    workflow_id = comp_data.get("workflow_id", "")

    # 3. Backup (only in real run)
    if not dry_run:
        backup_dir = _backup_cases(wf_dir)
        # Also backup composition_data.json
        comp_backup = backup_dir / "composition_data.json"
        if comp_path.exists() and not comp_backup.exists():
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(comp_path, comp_backup)
    _log("[A.1] backup completed", verbose)

    # 4. Migrate each case file
    cases_dir = wf_dir / "02_cases"
    case_files = sorted(cases_dir.glob("case_C*.json")) if cases_dir.exists() else []

    migrated_cases = 0
    skipped_cases = 0
    total_changes = 0
    per_case_changes: dict[str, list[str]] = {}

    for case_path in case_files:
        with open(case_path, encoding="utf-8") as f:
            case_data = json.load(f)

        if is_canonical(case_data):
            skipped_cases += 1
            per_case_changes[case_path.name] = ["Already canonical — skipped"]
            continue

        result = migrate_case_card(case_data, paper_index, workflow_id=workflow_id, dry_run=True)
        migrated_dict = result["migrated"]
        changes = result["changes"]

        per_case_changes[case_path.name] = changes
        total_changes += len(changes)
        migrated_cases += 1

        if not dry_run:
            with open(case_path, "w", encoding="utf-8") as f:
                json.dump(migrated_dict, f, indent=2)

    _log(f"[A.2] case_cards: {migrated_cases} migrated, {skipped_cases} skipped", verbose)

    # 5. Migrate composition_data.json (statistics + modularity)
    comp_changes: list[str] = []
    if comp_data:
        comp_data, comp_changes = migrate_composition_data(comp_data, wf_dir)
        if not dry_run and comp_changes:
            with open(comp_path, "w", encoding="utf-8") as f:
                json.dump(comp_data, f, indent=2, ensure_ascii=False)

    _log(f"[A.3] composition_data: {len(comp_changes)} changes", verbose)

    # 6. Migrate variant files
    variant_changes: dict[str, list[str]] = {}
    wf_dir_04 = wf_dir / "04_workflow"
    if wf_dir_04.exists():
        try:
            from variant_migrator import migrate_variant_file
            for vf in sorted(wf_dir_04.glob("variant_V*.json")):
                result = migrate_variant_file(vf, dry_run=dry_run)
                if result.get("changes"):
                    variant_changes[vf.name] = result["changes"]
        except ImportError:
            pass

    total_variants = len(list(wf_dir_04.glob("variant_V*.json"))) if wf_dir_04.exists() else 0
    _log(f"[A.4] variants: {len(variant_changes)}/{total_variants} migrated", verbose)

    # 7. Build report
    now = datetime.now(timezone.utc).isoformat()
    report = {
        "migration_version": "2.2.0",
        "migrated_at": now,
        "timestamp": now,
        "workflow_id": workflow_id,
        "migrated_cases": migrated_cases,
        "skipped_cases": skipped_cases,
        "total_changes": total_changes,
        "composition_data_changes": comp_changes,
        "variant_changes": variant_changes,
        "per_case_changes": per_case_changes,
    }

    if not dry_run:
        report_dir = wf_dir / "00_metadata"
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / "migration_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    return report


# ---------------------------------------------------------------------------
# Phase B: Enrichment
# ---------------------------------------------------------------------------

def _backup_for_enrichment(wf_dir: Path) -> Path:
    """Backup cases and reports before enrichment.

    Creates _versions/pre_enrichment/ with:
    - 02_cases/ (all case card JSONs)
    - composition_report.md, composition_workflow.md
    - paper_list.json

    Returns backup dir path. Idempotent: skips if already exists.
    """
    backup_dir = wf_dir / "_versions" / "pre_enrichment"

    # Backup cases
    cases_src = wf_dir / "02_cases"
    if cases_src.exists():
        backup_cases = backup_dir / "02_cases"
        if not backup_cases.exists():
            shutil.copytree(cases_src, backup_cases)

    # Backup reports
    for fname in ("composition_report.md", "composition_workflow.md",
                   "composition_report_ko.md", "composition_workflow_ko.md"):
        src = wf_dir / fname
        if src.exists():
            dst = backup_dir / fname
            if not dst.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    # Backup paper_list
    for subdir in ("01_papers", "01_literature"):
        src = wf_dir / subdir / "paper_list.json"
        if src.exists():
            dst = backup_dir / "paper_list.json"
            if not dst.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            break

    return backup_dir


def enrich_workflow(wf_dir: Path, dry_run: bool = False,
                    case_violation_map: dict[str, bool] | None = None,
                    verbose: bool = True) -> dict:
    """Enrich all case cards in a workflow directory using PubMed data.

    Automatically runs Phase A (mechanical migration) first to ensure
    case cards are in canonical format before enrichment.

    Phase A — Mechanical migration (field renaming, case_id fix, etc.)
    Phase B pipeline:
    B.1 — Enrich paper_list with PubMed metadata (PMID, abstract, MeSH)
    B.2 — Enrich each case card using paper data (6-principle extraction)
    B.3 — Structural blocks (completeness, flow_diagram, workflow_context)
    B.4 — Regenerate reports (13-section + 5-section + Korean)

    Args:
        wf_dir: workflow directory path
        dry_run: if True, compute changes but don't write files
        case_violation_map: {filename: True} for cases with pending audit violations
        verbose: if True (default), print progress to stderr

    Returns:
        Enrichment report dict (includes Phase A migration summary).
    """
    wf_dir = Path(wf_dir)
    now = datetime.now(timezone.utc).isoformat()
    case_violation_map = case_violation_map or {}

    # Phase A — Mechanical migration first (idempotent: skips canonical cards)
    migration_report = migrate_workflow(wf_dir, dry_run=dry_run, verbose=verbose)

    # Load composition_data
    comp_path = wf_dir / "composition_data.json"
    comp_data = {}
    if comp_path.exists():
        with open(comp_path, encoding="utf-8") as f:
            comp_data = json.load(f)
    workflow_id = comp_data.get("workflow_id", "")

    # B.1 — Paper enrichment
    paper_data = load_paper_list(wf_dir)
    enriched_papers = enrich_paper_list(paper_data)
    papers = enriched_papers.get("papers", [])

    # Build paper index by paper_id and also by "id" field
    paper_index = {}
    for p in papers:
        pid = p.get("paper_id", p.get("id", ""))
        if pid:
            paper_index[pid] = p

    paper_enrichment_stats = {
        "total": len(papers),
        "enriched": sum(1 for p in papers if p.get("enrichment_status") == "enriched"),
        "partial": sum(1 for p in papers if p.get("enrichment_status") == "partial"),
        "failed": sum(1 for p in papers if p.get("enrichment_status") == "failed"),
        "full_text_fetched": sum(1 for p in papers if p.get("text_source") in ("pmc_oa", "europepmc")),
    }

    _log(
        f"[B.1] papers: {paper_enrichment_stats['enriched']}/{paper_enrichment_stats['total']} enriched, "
        f"{paper_enrichment_stats['full_text_fetched']} full-text",
        verbose,
    )

    # Backup before writing
    if not dry_run:
        _backup_for_enrichment(wf_dir)

    # Save full texts to separate files and strip from paper objects
    if not dry_run:
        for p in papers:
            pending_text = p.pop("_full_text_pending", "")
            text = pending_text or p.get("abstract", "")
            pid = p.get("paper_id", p.get("id", ""))
            if text and pid:
                save_paper_fulltext(wf_dir, pid, text)
            p.pop("full_text", None)
        save_enriched_paper_list(wf_dir, enriched_papers)

    # B.2 — Case card enrichment
    cases_dir = wf_dir / "02_cases"
    case_files = sorted(cases_dir.glob("case_C*.json")) if cases_dir.exists() else []

    enriched_cases = 0
    skipped_cases = 0
    per_case_changes: dict[str, list[str]] = {}

    for case_path in case_files:
        with open(case_path, encoding="utf-8") as f:
            case_data = json.load(f)

        # Idempotency check (bypass if case has pending audit violations)
        case_has_violations = case_path.name in case_violation_map
        if is_enriched(case_data, has_violations=case_has_violations):
            skipped_cases += 1
            per_case_changes[case_path.name] = ["Already enriched — skipped"]
            continue

        # Find matching paper
        paper_id = case_data.get("paper_id", "")
        if not paper_id:
            meta = case_data.get("metadata", {})
            # Try to match by existing paper reference
            for pid, pinfo in paper_index.items():
                if meta.get("doi") and meta["doi"] == pinfo.get("doi"):
                    paper_id = pid
                    break
                if meta.get("pmid") and str(meta["pmid"]) == str(pinfo.get("pmid")):
                    paper_id = pid
                    break

        paper_info = paper_index.get(paper_id, {})

        # Enrich the case card
        enriched = enrich_case_card(case_data, paper_info, comp_data, wf_dir=wf_dir)
        enriched_cases += 1

        changes = []
        if paper_info.get("enrichment_status") == "enriched":
            changes.append(f"Paper {paper_id}: PubMed metadata applied")
        if enriched.get("completeness", {}).get("score", 0) > 0:
            changes.append(f"Completeness: {enriched['completeness']['score']:.3f}")
        if enriched.get("flow_diagram") and "[QC]" in enriched.get("flow_diagram", ""):
            changes.append("Flow diagram: QC checkpoints added")
        if enriched.get("workflow_context", {}).get("boundary_inputs"):
            changes.append("Workflow context: boundary info added")
        per_case_changes[case_path.name] = changes if changes else ["Enrichment applied"]

        if not dry_run:
            with open(case_path, "w", encoding="utf-8") as f:
                json.dump(enriched, f, indent=2, ensure_ascii=False)

    _log(f"[B.2] cases: {enriched_cases} enriched, {skipped_cases} skipped", verbose)

    # B.4 — Report regeneration
    report_files = {}
    report_error = ""
    if not dry_run:
        try:
            report_files = write_reports(wf_dir)
        except Exception as e:
            report_error = str(e)
            print(f"[WARN] Report generation failed for {workflow_id}: {e}", file=sys.stderr, flush=True)

    _log(f"[B.4] reports: {len(report_files)} generated", verbose)

    m = migration_report.get("migrated_cases", 0)
    _log(f"=> {workflow_id}: migrated={m} enriched={enriched_cases}", verbose)

    # Build enrichment report
    report = {
        "enrichment_version": "2.1.0",
        "enriched_at": now,
        "workflow_id": workflow_id,
        "dry_run": dry_run,
        "migration_phase_a": {
            "migrated_cases": migration_report.get("migrated_cases", 0),
            "skipped_cases": migration_report.get("skipped_cases", 0),
            "total_changes": migration_report.get("total_changes", 0),
        },
        "paper_enrichment": paper_enrichment_stats,
        "enriched_cases": enriched_cases,
        "skipped_cases": skipped_cases,
        "per_case_changes": per_case_changes,
        "reports_generated": list(report_files.keys()) if report_files else [],
        **({"report_error": report_error} if report_error else {}),
    }

    if not dry_run:
        report_dir = wf_dir / "00_metadata"
        report_dir.mkdir(parents=True, exist_ok=True)
        with open(report_dir / "enrichment_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

    return report
