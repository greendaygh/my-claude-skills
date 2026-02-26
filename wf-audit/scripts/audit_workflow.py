"""Single workflow deep audit."""

import json
from pathlib import Path
from scoring import (
    ScoredResult,
    score_case_card,
    score_paper_list,
    score_variant,
    score_composition_data,
    score_report_sections,
    aggregate_workflow_score,
)
from referential_integrity import run_all as run_integrity_checks
from canonical_schemas import SCHEMA_VERSION
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# detect_schema_era
# ---------------------------------------------------------------------------

def detect_schema_era(wf_dir: Path) -> dict:
    """Classify the schema era of a workflow directory.

    Looks at the first case card (02_cases/case_C001.json) and returns:
        {"era": "<era>", "step_field_style": "<style>"}

    Era values:
        v2_canonical    — has metadata + completeness + flow_diagram + workflow_context
        v1_legacy_flat  — has paper_id + technique, no metadata block
        v1_wt_extended  — has variant_hint or variant_cluster
        v1_wt_findings  — has workflow_steps + key_findings
        v1_unknown      — anything else

    Step field style values:
        step_number+step_name
        position+name
        position+action
        other
    """
    case_path = wf_dir / "02_cases" / "case_C001.json"
    if not case_path.exists():
        return {"era": "v1_unknown", "step_field_style": "other"}

    try:
        with open(case_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"era": "v1_unknown", "step_field_style": "other"}

    # Classify era
    has_metadata = "metadata" in data
    has_completeness = "completeness" in data
    has_flow = "flow_diagram" in data
    has_workflow_context = "workflow_context" in data
    has_paper_id = "paper_id" in data
    has_technique = "technique" in data
    has_variant_hint = "variant_hint" in data or "variant_cluster" in data
    has_workflow_steps = "workflow_steps" in data
    has_key_findings = "key_findings" in data

    if has_metadata and has_completeness and has_flow and has_workflow_context:
        era = "v2_canonical"
    elif has_variant_hint:
        era = "v1_wt_extended"
    elif has_paper_id and has_technique:
        era = "v1_legacy_flat"
    elif has_workflow_steps and has_key_findings:
        era = "v1_wt_findings"
    else:
        era = "v1_unknown"

    # Detect step field style from first step
    steps = data.get("steps", [])
    step_field_style = "other"
    if isinstance(steps, list) and len(steps) > 0:
        first = steps[0]
        if isinstance(first, dict):
            if "step_number" in first and "step_name" in first:
                step_field_style = "step_number+step_name"
            elif "position" in first and "name" in first:
                step_field_style = "position+name"
            elif "position" in first and "action" in first:
                step_field_style = "position+action"

    return {"era": era, "step_field_style": step_field_style}


# ---------------------------------------------------------------------------
# load_existing_validation
# ---------------------------------------------------------------------------

def load_existing_validation(wf_dir: Path) -> dict | None:
    """READ-ONLY. Load 00_metadata/validation_report.json if it exists.

    Returns:
        {"source": "validation_report.json", "format": "workflow-composer"|"wf-output", "data": <parsed>}
        or None if the file is missing or unreadable.

    No subprocess calls are made.
    """
    val_path = wf_dir / "00_metadata" / "validation_report.json"
    if not val_path.exists():
        return None

    try:
        with open(val_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    # Auto-detect format
    if isinstance(data, dict) and "violations_by_category" in data:
        fmt = "workflow-composer"
    elif isinstance(data, dict) and "checks" in data:
        fmt = "wf-output"
    else:
        fmt = "unknown"

    return {"source": "validation_report.json", "format": fmt, "data": data}


# ---------------------------------------------------------------------------
# get_migration_priority
# ---------------------------------------------------------------------------

def get_migration_priority(score: float) -> str:
    """Map a conformance score (0.0-1.0) to a migration priority label."""
    if score >= 0.9:
        return "none"
    if score >= 0.7:
        return "low"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "high"
    return "critical"


# ---------------------------------------------------------------------------
# audit_single_workflow
# ---------------------------------------------------------------------------

def _load_json(path: Path):
    """Load JSON file; return None on failure."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _build_migration_recommendations(scores: dict, era_info: dict) -> list:
    """Generate human-readable migration recommendations from score details."""
    recs = []

    # Step field style renames
    style = era_info.get("step_field_style", "other")
    if style == "position+name":
        recs.append("Rename 'position' to 'step_number' and 'name' to 'step_name' in step fields")
    elif style == "position+action":
        recs.append("Rename 'position' to 'step_number' and 'action' to 'step_name' in step fields")

    # Era-based recommendations
    era = era_info.get("era", "")
    if era in ("v1_legacy_flat", "v1_wt_extended", "v1_wt_findings", "v1_unknown"):
        recs.append("Add canonical metadata block to case cards (pmid, doi, authors, year, journal, title, purpose, organism, scale, automation_level, core_technique, fulltext_access, access_method, access_tier)")
        recs.append("Add 'completeness', 'flow_diagram', and 'workflow_context' blocks to case cards")

    # Case card violations
    case_scores = scores.get("case_cards", {})
    for v in case_scores.get("violations", []):
        if "equipment" in v and "wrong_type" in v:
            recs.append("Convert equipment fields from flat strings to structured objects {name, model, manufacturer}")
        elif "missing metadata" in v:
            pass  # already covered above

    # Paper list violations
    paper_scores = scores.get("paper_list", {})
    if paper_scores.get("score", 1.0) < 0.5:
        recs.append("Restructure paper_list.json to canonical format: {\"papers\": [{paper_id, doi, pmid, title, authors, year, journal}]}")

    # Variant violations
    variant_scores = scores.get("variant_files", {})
    if variant_scores.get("score", 1.0) < 0.5 and variant_scores.get("count", 0) == 0:
        recs.append("Create variant files in 04_workflow/variant_V*.json")

    # UO mapping
    uo_scores = scores.get("uo_mapping", {})
    if uo_scores.get("score", 1.0) == 0.0:
        recs.append("Create uo_mapping.json in 04_workflow/")

    # Report sections
    report_scores = scores.get("report_sections", {})
    if report_scores.get("score", 1.0) < 1.0:
        recs.append("Ensure composition_report.md contains all 13 required numbered sections")

    # Deduplicate while preserving order
    seen = set()
    unique_recs = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            unique_recs.append(r)
    return unique_recs


def audit_single_workflow(wf_dir: Path, catalog: dict = None) -> dict:
    """Run a deep audit of a single workflow directory.

    Returns a conformance report dict with scores, era info, and recommendations.
    """
    wf_dir = Path(wf_dir)
    scores_raw = {}
    all_violations = {}

    # 1. composition_data.json
    comp_path = wf_dir / "composition_data.json"
    comp_data = _load_json(comp_path) or {}
    comp_result = score_composition_data(comp_data)
    scores_raw["composition_data"] = comp_result.score
    all_violations["composition_data"] = {
        "score": comp_result.score,
        "violations": comp_result.violations,
    }

    # 2. Case cards from 02_cases/case_C*.json
    cases_dir = wf_dir / "02_cases"
    case_results = []
    case_violations = []
    if cases_dir.exists():
        for cfile in sorted(cases_dir.glob("case_C*.json")):
            cdata = _load_json(cfile)
            if isinstance(cdata, dict):
                r = score_case_card(cdata)
                case_results.append(r.score)
                case_violations.extend(r.violations)

    case_avg = sum(case_results) / len(case_results) if case_results else 0.0
    scores_raw["case_cards"] = case_avg
    all_violations["case_cards"] = {
        "score": case_avg,
        "count": len(case_results),
        "violations": list(dict.fromkeys(case_violations)),  # deduplicate
    }

    # 3. paper_list.json — try 01_papers/ first, fall back to 01_literature/
    paper_data = None
    for paper_subdir in ("01_papers", "01_literature"):
        paper_path = wf_dir / paper_subdir / "paper_list.json"
        if paper_path.exists():
            paper_data = _load_json(paper_path)
            break
    paper_result = score_paper_list(paper_data if paper_data is not None else {})
    scores_raw["paper_list"] = paper_result.score
    all_violations["paper_list"] = {
        "score": paper_result.score,
        "violations": paper_result.violations,
    }

    # 4. Variant files from 04_workflow/variant_*.json
    variant_dir = wf_dir / "04_workflow"
    variant_results = []
    variant_violations = []
    if variant_dir.exists():
        for vfile in sorted(variant_dir.glob("variant_*.json")):
            vdata = _load_json(vfile)
            if isinstance(vdata, dict):
                r = score_variant(vdata)
                variant_results.append(r.score)
                variant_violations.extend(r.violations)

    variant_avg = sum(variant_results) / len(variant_results) if variant_results else 0.0
    scores_raw["variant_files"] = variant_avg
    all_violations["variant_files"] = {
        "score": variant_avg,
        "count": len(variant_results),
        "violations": list(dict.fromkeys(variant_violations)),
    }

    # 5. composition_report.md
    report_path = wf_dir / "composition_report.md"
    if report_path.exists():
        report_text = report_path.read_text(encoding="utf-8")
        report_result = score_report_sections(report_text)
    else:
        report_result = ScoredResult(score=0.0, max_score=1.0,
                                     violations=["missing: composition_report.md"],
                                     schema_group="report")
    scores_raw["report_sections"] = report_result.score
    all_violations["report_sections"] = {
        "score": report_result.score,
        "violations": report_result.violations,
    }

    # 6. uo_mapping.json
    uo_map_path = wf_dir / "04_workflow" / "uo_mapping.json"
    uo_data = _load_json(uo_map_path)
    if uo_data and (isinstance(uo_data, dict) and uo_data or
                    isinstance(uo_data, list) and len(uo_data) > 0):
        uo_score = 1.0
        uo_violations = []
    else:
        uo_score = 0.0
        uo_violations = ["missing or empty: 04_workflow/uo_mapping.json"]
    scores_raw["uo_mapping"] = uo_score
    all_violations["uo_mapping"] = {
        "score": uo_score,
        "violations": uo_violations,
    }

    # 7. Referential integrity
    paper_validity_info = {}
    try:
        integrity_results = run_integrity_checks(wf_dir, catalog)
        all_integrity_violations = []
        for check_name, check_result in integrity_results.items():
            if check_name == "paper_validity":
                # paper_validity returns a dict, not a list
                paper_validity_info = check_result
                all_integrity_violations.extend(check_result.get("violations", []))
            else:
                all_integrity_violations.extend(check_result)
        violation_count = len(all_integrity_violations)
        integrity_score = max(0.0, 1.0 - violation_count * 0.1)
    except Exception as e:
        all_integrity_violations = [f"integrity check error: {e}"]
        integrity_score = 0.5  # partial credit — couldn't run

    scores_raw["referential_integrity"] = integrity_score
    all_violations["referential_integrity"] = {
        "score": integrity_score,
        "violations": all_integrity_violations,
    }

    # 8. Aggregate
    aggregate_score = aggregate_workflow_score(scores_raw)

    # 9. Detect schema era
    era_info = detect_schema_era(wf_dir)

    # 10. Load existing validation (read-only)
    existing_validation = load_existing_validation(wf_dir)

    # Build migration recommendations
    migration_recs = _build_migration_recommendations(all_violations, era_info)

    return {
        "audit_version": SCHEMA_VERSION,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "workflow_id": comp_data.get("workflow_id", wf_dir.name),
        "conformance_score": aggregate_score,
        "migration_priority": get_migration_priority(aggregate_score),
        "schema_era": era_info["era"],
        "step_field_style": era_info["step_field_style"],
        "scores": all_violations,
        "paper_validity": paper_validity_info,
        "existing_validation": existing_validation,
        "migration_recommendations": migration_recs,
    }
