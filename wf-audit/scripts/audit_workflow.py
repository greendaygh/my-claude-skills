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
    score_case_summary,
    score_cluster_result,
    score_common_pattern,
    score_parameter_ranges,
    score_step_alignment,
    score_uo_mapping,
    score_qc_checkpoints,
    score_workflow_context,
    aggregate_workflow_score,
)
from referential_integrity import run_all as run_integrity_checks
from canonical_schemas import SCHEMA_VERSION
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# detect_schema_era
# ---------------------------------------------------------------------------

def detect_schema_era(wf_dir: Path) -> dict:
    """Classify the schema era of a workflow directory."""
    case_path = wf_dir / "02_cases" / "case_C001.json"
    if not case_path.exists():
        return {"era": "v1_unknown", "step_field_style": "other"}

    try:
        with open(case_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {"era": "v1_unknown", "step_field_style": "other"}

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
    """READ-ONLY. Load 00_metadata/validation_report.json if it exists."""
    val_path = wf_dir / "00_metadata" / "validation_report.json"
    if not val_path.exists():
        return None
    try:
        with open(val_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    if isinstance(data, dict) and "violations_by_category" in data:
        fmt = "workflow-composer"
    elif isinstance(data, dict) and "checks" in data:
        fmt = "wf-output"
    else:
        fmt = "unknown"

    return {"source": "validation_report.json", "format": fmt, "data": data}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_migration_priority(score: float) -> str:
    if score >= 0.9:
        return "none"
    if score >= 0.7:
        return "low"
    if score >= 0.5:
        return "medium"
    if score >= 0.3:
        return "high"
    return "critical"


def _load_json(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None


def _rel_path(wf_dir: Path, file_path: Path) -> str:
    """Return path relative to the workflow dir."""
    try:
        return str(file_path.relative_to(wf_dir))
    except ValueError:
        return str(file_path)


def _build_score_entry(result: ScoredResult, **extra) -> dict:
    """Build a score entry dict from a ScoredResult."""
    entry = {
        "score": result.score,
        "violations": result.violations,
        "detailed_violations": result.detailed_violations,
    }
    entry.update(extra)
    return entry


def _build_migration_recommendations(scores: dict, era_info: dict) -> list:
    recs = []

    style = era_info.get("step_field_style", "other")
    if style == "position+name":
        recs.append("Rename 'position' to 'step_number' and 'name' to 'step_name' in step fields")
    elif style == "position+action":
        recs.append("Rename 'position' to 'step_number' and 'action' to 'step_name' in step fields")

    era = era_info.get("era", "")
    if era in ("v1_legacy_flat", "v1_wt_extended", "v1_wt_findings", "v1_unknown"):
        recs.append("Add canonical metadata block to case cards (pmid, doi, authors, year, journal, title, purpose, organism, scale, automation_level, core_technique, fulltext_access, access_method, access_tier)")
        recs.append("Add 'completeness', 'flow_diagram', and 'workflow_context' blocks to case cards")

    case_violations = scores.get("case_cards", {}).get("violations", [])
    for v in case_violations:
        if "equipment" in v and "wrong_type" in v:
            recs.append("Convert equipment fields from flat strings to structured objects {name, model, manufacturer}")
            break

    paper_score = scores.get("paper_list", {}).get("score", 1.0)
    if paper_score < 0.5:
        recs.append("Restructure paper_list.json to canonical format: {\"papers\": [{paper_id, doi, pmid, title, authors, year, journal}]}")

    variant_entry = scores.get("variant_files", {})
    if variant_entry.get("score", 1.0) < 0.5 and variant_entry.get("count", 0) == 0:
        recs.append("Create variant files in 04_workflow/variant_V*.json")

    uo_score = scores.get("uo_mapping", {}).get("score", 1.0)
    if uo_score == 0.0:
        recs.append("Create uo_mapping.json in 04_workflow/")

    report_score = scores.get("report_sections", {}).get("score", 1.0)
    if report_score < 1.0:
        recs.append("Ensure composition_report.md contains all 13 required numbered sections")

    seen = set()
    unique = []
    for r in recs:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique


# ---------------------------------------------------------------------------
# audit_single_workflow
# ---------------------------------------------------------------------------

def audit_single_workflow(wf_dir: Path, catalog: dict = None) -> dict:
    """Run a deep audit of a single workflow directory."""
    wf_dir = Path(wf_dir)
    scores_raw = {}
    all_violations = {}

    # 1. composition_data.json
    comp_path = wf_dir / "composition_data.json"
    comp_data = _load_json(comp_path) or {}
    comp_result = score_composition_data(comp_data, source_file=_rel_path(wf_dir, comp_path))
    scores_raw["composition_data"] = comp_result.score
    all_violations["composition_data"] = _build_score_entry(comp_result)

    # 2. Case cards from 02_cases/case_C*.json
    cases_dir = wf_dir / "02_cases"
    case_results = []
    case_violations_flat = []
    case_detailed = []
    if cases_dir.exists():
        for cfile in sorted(cases_dir.glob("case_C*.json")):
            cdata = _load_json(cfile)
            if isinstance(cdata, dict):
                r = score_case_card(cdata, source_file=_rel_path(wf_dir, cfile))
                case_results.append(r.score)
                case_violations_flat.extend(r.violations)
                case_detailed.extend(r.detailed_violations)

    case_avg = sum(case_results) / len(case_results) if case_results else 0.0
    scores_raw["case_cards"] = case_avg
    all_violations["case_cards"] = {
        "score": case_avg,
        "count": len(case_results),
        "violations": list(dict.fromkeys(case_violations_flat)),
        "detailed_violations": case_detailed,
    }

    # 3. paper_list.json
    paper_data = None
    paper_source = ""
    for paper_subdir in ("01_papers", "01_literature"):
        paper_path = wf_dir / paper_subdir / "paper_list.json"
        if paper_path.exists():
            paper_data = _load_json(paper_path)
            paper_source = _rel_path(wf_dir, paper_path)
            break
    paper_result = score_paper_list(paper_data if paper_data is not None else {}, source_file=paper_source)
    scores_raw["paper_list"] = paper_result.score
    all_violations["paper_list"] = _build_score_entry(paper_result)

    # 4. Variant files from 04_workflow/variant_*.json
    variant_dir = wf_dir / "04_workflow"
    variant_results = []
    variant_violations_flat = []
    variant_detailed = []
    if variant_dir.exists():
        for vfile in sorted(variant_dir.glob("variant_*.json")):
            vdata = _load_json(vfile)
            if isinstance(vdata, dict):
                r = score_variant(vdata, source_file=_rel_path(wf_dir, vfile))
                variant_results.append(r.score)
                variant_violations_flat.extend(r.violations)
                variant_detailed.extend(r.detailed_violations)

    variant_avg = sum(variant_results) / len(variant_results) if variant_results else 0.0
    scores_raw["variant_files"] = variant_avg
    all_violations["variant_files"] = {
        "score": variant_avg,
        "count": len(variant_results),
        "violations": list(dict.fromkeys(variant_violations_flat)),
        "detailed_violations": variant_detailed,
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
    all_violations["report_sections"] = _build_score_entry(report_result)

    # 6. uo_mapping.json (Pydantic-based)
    uo_map_path = wf_dir / "04_workflow" / "uo_mapping.json"
    uo_data = _load_json(uo_map_path)
    if isinstance(uo_data, dict) and uo_data:
        uo_result = score_uo_mapping(uo_data, source_file=_rel_path(wf_dir, uo_map_path))
        scores_raw["uo_mapping"] = uo_result.score
        all_violations["uo_mapping"] = _build_score_entry(uo_result)
    else:
        scores_raw["uo_mapping"] = 0.0
        all_violations["uo_mapping"] = {
            "score": 0.0,
            "violations": ["missing or empty: 04_workflow/uo_mapping.json"],
            "detailed_violations": [],
        }

    # 7. Referential integrity (unchanged)
    paper_validity_info = {}
    try:
        integrity_results = run_integrity_checks(wf_dir, catalog)
        all_integrity_violations = []
        for check_name, check_result in integrity_results.items():
            if check_name == "paper_validity":
                paper_validity_info = check_result
                all_integrity_violations.extend(check_result.get("violations", []))
            else:
                all_integrity_violations.extend(check_result)
        violation_count = len(all_integrity_violations)
        integrity_score = max(0.0, 1.0 - violation_count * 0.1)
    except Exception as e:
        all_integrity_violations = [f"integrity check error: {e}"]
        integrity_score = 0.5

    scores_raw["referential_integrity"] = integrity_score
    all_violations["referential_integrity"] = {
        "score": integrity_score,
        "violations": all_integrity_violations,
        "detailed_violations": [],
    }

    # --- New file types (8-14) ---

    # 8. case_summary.json
    cs_path = wf_dir / "02_cases" / "case_summary.json"
    cs_data = _load_json(cs_path)
    if isinstance(cs_data, dict):
        cs_result = score_case_summary(cs_data, source_file=_rel_path(wf_dir, cs_path))
        all_violations["case_summary"] = _build_score_entry(cs_result)
    else:
        all_violations["case_summary"] = {"score": 0.0, "violations": ["missing: case_summary.json"], "detailed_violations": []}

    # 9. cluster_result.json
    cr_path = wf_dir / "03_analysis" / "cluster_result.json"
    cr_data = _load_json(cr_path)
    if isinstance(cr_data, dict):
        cr_result = score_cluster_result(cr_data, source_file=_rel_path(wf_dir, cr_path))
        all_violations["cluster_result"] = _build_score_entry(cr_result)
    else:
        all_violations["cluster_result"] = {"score": 0.0, "violations": ["missing: cluster_result.json"], "detailed_violations": []}

    # 10. common_pattern.json
    cp_path = wf_dir / "03_analysis" / "common_pattern.json"
    cp_data = _load_json(cp_path)
    if isinstance(cp_data, dict):
        cp_result = score_common_pattern(cp_data, source_file=_rel_path(wf_dir, cp_path))
        all_violations["common_pattern"] = _build_score_entry(cp_result)
    else:
        all_violations["common_pattern"] = {"score": 0.0, "violations": ["missing: common_pattern.json"], "detailed_violations": []}

    # 11. parameter_ranges.json
    pr_path = wf_dir / "03_analysis" / "parameter_ranges.json"
    pr_data = _load_json(pr_path)
    if isinstance(pr_data, dict):
        pr_result = score_parameter_ranges(pr_data, source_file=_rel_path(wf_dir, pr_path))
        all_violations["parameter_ranges"] = _build_score_entry(pr_result)
    else:
        all_violations["parameter_ranges"] = {"score": 0.0, "violations": ["missing: parameter_ranges.json"], "detailed_violations": []}

    # 12. step_alignment.json
    sa_path = wf_dir / "03_analysis" / "step_alignment.json"
    sa_data = _load_json(sa_path)
    if isinstance(sa_data, dict):
        sa_result = score_step_alignment(sa_data, source_file=_rel_path(wf_dir, sa_path))
        all_violations["step_alignment"] = _build_score_entry(sa_result)
    else:
        all_violations["step_alignment"] = {"score": 0.0, "violations": ["missing: step_alignment.json"], "detailed_violations": []}

    # 13. qc_checkpoints.json
    qc_path = wf_dir / "04_workflow" / "qc_checkpoints.json"
    qc_data = _load_json(qc_path)
    if isinstance(qc_data, dict):
        qc_result = score_qc_checkpoints(qc_data, source_file=_rel_path(wf_dir, qc_path))
        all_violations["qc_checkpoints"] = _build_score_entry(qc_result)

    # 14. workflow_context.json
    wc_path = wf_dir / "00_metadata" / "workflow_context.json"
    wc_data = _load_json(wc_path)
    if isinstance(wc_data, dict):
        wc_result = score_workflow_context(wc_data, source_file=_rel_path(wf_dir, wc_path))
        all_violations["workflow_context"] = _build_score_entry(wc_result)

    # --- Aggregate ---
    aggregate_score = aggregate_workflow_score(scores_raw)
    era_info = detect_schema_era(wf_dir)
    existing_validation = load_existing_validation(wf_dir)
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
