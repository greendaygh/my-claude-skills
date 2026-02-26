"""Conformance scoring engine for workflow audit (0.0-1.0 scale)."""

from dataclasses import dataclass, field
import re
from canonical_schemas import (
    CASE_CARD,
    PAPER_LIST,
    VARIANT,
    COMPOSITION_DATA,
    CASE_ID_PATTERN,
    STEP_KEY_ALIASES,
)


@dataclass
class ScoredResult:
    score: float                                         # 0.0-1.0
    max_score: float
    violations: list = field(default_factory=list)
    field_details: dict = field(default_factory=dict)   # {field: "present"|"missing"|"wrong_type"|"alias_match"}
    schema_group: str = ""                               # "canonical", "legacy_flat", "wt_extended", etc.


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _alias_map() -> dict:
    """Build reverse alias map: alias_key -> canonical_key."""
    rev = {}
    for canonical, aliases in STEP_KEY_ALIASES.items():
        for alias in aliases:
            rev[alias] = canonical
    return rev


_REVERSE_ALIASES = _alias_map()


def _score_item_list(items, required_keys: list, field_name: str) -> tuple:
    """Score a list of items (equipment or software).

    Returns (score 0.0-1.0, detail string).
    - list of dicts with all required keys → 1.0, "present"
    - list of strings (flat) → 0.5, "wrong_type"
    - missing / empty / wrong structure → 0.0, "missing"
    """
    if not isinstance(items, list) or len(items) == 0:
        return 0.0, "missing"
    if all(isinstance(i, str) for i in items):
        return 0.5, "wrong_type"
    if all(isinstance(i, dict) for i in items):
        # Check that required keys exist in each dict
        all_have_keys = all(
            all(k in item for k in required_keys) for item in items
        )
        if all_have_keys:
            return 1.0, "present"
        return 0.5, "wrong_type"
    # Mixed list
    return 0.5, "wrong_type"


def _classify_case_card(data: dict) -> str:
    """Classify schema_group for a case card."""
    has_metadata = "metadata" in data
    has_completeness = "completeness" in data
    has_flow = "flow_diagram" in data
    has_paper_id = "paper_id" in data
    has_technique = "technique" in data
    has_variant_hint = "variant_hint" in data or "variant_cluster" in data
    has_workflow_steps = "workflow_steps" in data
    has_key_findings = "key_findings" in data

    if has_metadata and has_completeness and has_flow:
        return "canonical"
    if has_paper_id and has_technique:
        return "legacy_flat"
    if has_variant_hint:
        return "wt_extended"
    if has_workflow_steps and has_key_findings:
        return "wt_findings"
    return "unknown"


# ---------------------------------------------------------------------------
# score_case_card
# ---------------------------------------------------------------------------

def score_case_card(case_data: dict) -> ScoredResult:
    """Score a case card for canonical conformance.

    Scoring weights are equal per top-level field and per step field.
    """
    violations = []
    field_details = {}
    schema_group = _classify_case_card(case_data)

    # --- Top-level required fields ---
    top_required = CASE_CARD["required_top_level"]
    top_scores = []
    for key in top_required:
        if key in case_data:
            field_details[key] = "present"
            top_scores.append(1.0)
        else:
            # Check alias
            alias_found = None
            for ak, canonical in _REVERSE_ALIASES.items():
                if canonical == key and ak in case_data:
                    alias_found = ak
                    break
            if alias_found:
                field_details[key] = "alias_match"
                top_scores.append(0.3)
                violations.append(f"alias: '{alias_found}' used instead of '{key}'")
            else:
                field_details[key] = "missing"
                top_scores.append(0.0)
                violations.append(f"missing: {key}")

    # --- Metadata fields ---
    meta_scores = []
    if "metadata" in case_data and isinstance(case_data["metadata"], dict):
        metadata = case_data["metadata"]
        for mkey in CASE_CARD["metadata_required"]:
            if mkey in metadata:
                meta_scores.append(1.0)
            else:
                meta_scores.append(0.0)
                violations.append(f"missing metadata field: {mkey}")
    else:
        # No metadata block at all
        meta_scores = [0.0] * len(CASE_CARD["metadata_required"])

    # --- Step fields ---
    step_scores = []
    steps = case_data.get("steps", [])
    if isinstance(steps, list) and len(steps) > 0:
        for step in steps:
            if not isinstance(step, dict):
                step_scores.append(0.0)
                continue
            step_field_scores = []
            for skey in CASE_CARD["step_required"]:
                if skey == "equipment":
                    val = step.get("equipment")
                    if val is None:
                        # Check alias — equipment has no alias, just missing
                        step_field_scores.append(0.0)
                        violations.append("missing step field: equipment")
                    else:
                        sc, detail = _score_item_list(val, CASE_CARD["equipment_item"], "equipment")
                        step_field_scores.append(sc)
                        if detail == "wrong_type":
                            violations.append("step equipment: wrong_type (flat strings)")
                        field_details["step.equipment"] = detail
                elif skey == "software":
                    val = step.get("software")
                    if val is None:
                        # Check alias
                        alias_val = None
                        for ak, canonical in _REVERSE_ALIASES.items():
                            if canonical == skey and ak in step:
                                alias_val = step[ak]
                                break
                        if alias_val is not None:
                            sc, detail = _score_item_list(alias_val, CASE_CARD["software_item"], "software")
                            step_field_scores.append(0.3 * sc if sc == 1.0 else 0.3)
                            field_details["step.software"] = "alias_match"
                        else:
                            step_field_scores.append(0.0)
                            violations.append("missing step field: software")
                            field_details["step.software"] = "missing"
                    else:
                        sc, detail = _score_item_list(val, CASE_CARD["software_item"], "software")
                        step_field_scores.append(sc)
                        field_details["step.software"] = detail
                        if detail == "wrong_type":
                            violations.append("step software: wrong_type (flat strings)")
                else:
                    # Regular field — check direct or alias
                    if skey in step:
                        step_field_scores.append(1.0)
                    else:
                        # Check if an alias is present
                        alias_found = None
                        if skey in STEP_KEY_ALIASES:
                            for alias in STEP_KEY_ALIASES[skey]:
                                if alias in step:
                                    alias_found = alias
                                    break
                        if alias_found:
                            step_field_scores.append(0.3)
                            field_details[f"step.{skey}"] = "alias_match"
                            violations.append(f"alias: '{alias_found}' used instead of '{skey}' in step")
                        else:
                            step_field_scores.append(0.0)
                            field_details[f"step.{skey}"] = "missing"
            if step_field_scores:
                step_scores.append(sum(step_field_scores) / len(step_field_scores))
    else:
        step_scores = [0.0]

    # --- Weighted aggregation ---
    # top-level: 40%, metadata: 30%, steps: 30%
    top_avg = sum(top_scores) / len(top_scores) if top_scores else 0.0
    meta_avg = sum(meta_scores) / len(meta_scores) if meta_scores else 0.0
    step_avg = sum(step_scores) / len(step_scores) if step_scores else 0.0

    final_score = 0.4 * top_avg + 0.3 * meta_avg + 0.3 * step_avg

    return ScoredResult(
        score=round(final_score, 4),
        max_score=1.0,
        violations=violations,
        field_details=field_details,
        schema_group=schema_group,
    )


# ---------------------------------------------------------------------------
# score_paper_list
# ---------------------------------------------------------------------------

def score_paper_list(paper_data) -> ScoredResult:
    """Score a paper list for canonical conformance."""
    violations = []
    field_details = {}

    # Must be a dict with "papers" key
    if not isinstance(paper_data, dict):
        violations.append("missing: papers (top-level must be dict with 'papers' key)")
        field_details["papers"] = "missing"
        return ScoredResult(
            score=0.0,
            max_score=1.0,
            violations=violations,
            field_details=field_details,
            schema_group="unknown",
        )

    scores = []

    # Check required top-level
    for key in PAPER_LIST["required_top_level"]:
        if key in paper_data:
            field_details[key] = "present"
            scores.append(1.0)
        else:
            field_details[key] = "missing"
            scores.append(0.0)
            violations.append(f"missing: {key}")

    # Check recommended top-level (partial credit)
    rec_scores = []
    for key in PAPER_LIST["recommended_top_level"]:
        if key in paper_data:
            rec_scores.append(1.0)
        else:
            rec_scores.append(0.0)
    rec_avg = sum(rec_scores) / len(rec_scores) if rec_scores else 0.0

    # Check per-paper required fields
    papers = paper_data.get("papers", [])
    paper_scores = []
    if isinstance(papers, list) and len(papers) > 0:
        for paper in papers:
            if not isinstance(paper, dict):
                paper_scores.append(0.0)
                continue
            paper_field_scores = []
            for pkey in PAPER_LIST["per_paper_required"]:
                if pkey in paper:
                    paper_field_scores.append(1.0)
                else:
                    paper_field_scores.append(0.0)
                    violations.append(f"missing paper field: {pkey}")
            if paper_field_scores:
                paper_scores.append(sum(paper_field_scores) / len(paper_field_scores))
    else:
        paper_scores = [0.0]

    top_avg = sum(scores) / len(scores) if scores else 0.0
    paper_avg = sum(paper_scores) / len(paper_scores) if paper_scores else 0.0

    # Weights: required top-level 40%, recommended 20%, per-paper 40%
    final_score = 0.4 * top_avg + 0.2 * rec_avg + 0.4 * paper_avg

    return ScoredResult(
        score=round(final_score, 4),
        max_score=1.0,
        violations=violations,
        field_details=field_details,
        schema_group="canonical" if "papers" in paper_data else "unknown",
    )


# ---------------------------------------------------------------------------
# score_variant
# ---------------------------------------------------------------------------

def score_variant(variant_data: dict) -> ScoredResult:
    """Score a variant file for canonical conformance."""
    violations = []
    field_details = {}
    scores = []

    variant_id_pattern = VARIANT.get("variant_id_pattern", r"^V\d+$")

    for key in VARIANT["required_top_level"]:
        if key not in variant_data:
            field_details[key] = "missing"
            scores.append(0.0)
            violations.append(f"missing: {key}")
        elif key == "variant_id":
            vid = variant_data[key]
            if re.match(variant_id_pattern, str(vid)):
                field_details[key] = "present"
                scores.append(1.0)
            else:
                field_details[key] = "wrong_type"
                scores.append(0.0)
                violations.append(
                    f"variant_id '{vid}' does not match pattern '{variant_id_pattern}'"
                )
        elif key == "uo_sequence":
            val = variant_data[key]
            if isinstance(val, list):
                field_details[key] = "present"
                scores.append(1.0)
            else:
                field_details[key] = "wrong_type"
                scores.append(0.5)
                violations.append(f"uo_sequence should be a list, got {type(val).__name__}")
        else:
            field_details[key] = "present"
            scores.append(1.0)

    final_score = sum(scores) / len(scores) if scores else 0.0

    return ScoredResult(
        score=round(final_score, 4),
        max_score=1.0,
        violations=violations,
        field_details=field_details,
        schema_group="canonical" if not violations else "non_canonical",
    )


# ---------------------------------------------------------------------------
# score_composition_data
# ---------------------------------------------------------------------------

def score_composition_data(comp_data: dict) -> ScoredResult:
    """Score composition_data.json for canonical conformance."""
    violations = []
    field_details = {}
    scores = []

    schema_prefix = COMPOSITION_DATA["schema_version_prefix"]

    for key in COMPOSITION_DATA["required_top_level"]:
        if key not in comp_data:
            field_details[key] = "missing"
            scores.append(0.0)
            violations.append(f"missing: {key}")
        elif key == "schema_version":
            sv = str(comp_data[key])
            if sv.startswith(schema_prefix):
                field_details[key] = "present"
                scores.append(1.0)
            else:
                field_details[key] = "wrong_type"
                scores.append(0.0)
                violations.append(
                    f"schema_version '{sv}' does not start with '{schema_prefix}'"
                )
        else:
            field_details[key] = "present"
            scores.append(1.0)

    # Check statistics field
    statistics = comp_data.get("statistics", {})
    if isinstance(statistics, dict) and statistics:
        deprecated_map = COMPOSITION_DATA["statistics_deprecated_map"]
        standard = COMPOSITION_DATA["statistics_standard"]
        has_deprecated = False
        for dep_key in deprecated_map:
            if dep_key in statistics:
                has_deprecated = True
                canonical = deprecated_map[dep_key]
                violations.append(
                    f"deprecated statistics key '{dep_key}', use '{canonical}'"
                )
        # Check how many standard keys are present
        std_present = sum(1 for k in standard if k in statistics)
        std_score = std_present / len(standard) if standard else 0.0
        if has_deprecated:
            # Penalty for using deprecated keys
            stats_score = std_score * 0.5
        else:
            stats_score = std_score
        field_details["statistics"] = "present" if not has_deprecated and std_score >= 1.0 else "wrong_type"
        scores.append(stats_score)
    else:
        scores.append(0.0)
        violations.append("missing or empty: statistics")
        field_details["statistics"] = "missing"

    final_score = sum(scores) / len(scores) if scores else 0.0

    return ScoredResult(
        score=round(final_score, 4),
        max_score=1.0,
        violations=violations,
        field_details=field_details,
        schema_group="canonical" if not violations else "non_canonical",
    )


# ---------------------------------------------------------------------------
# score_report_sections
# ---------------------------------------------------------------------------

def score_report_sections(report_text: str) -> ScoredResult:
    """Score a report for 13 required numbered sections.

    Looks for headings matching: ^#{1,3}\\s*\\d+\\.
    """
    violations = []
    field_details = {}

    pattern = re.compile(r"^#{1,3}\s*\d+\.", re.MULTILINE)
    matches = pattern.findall(report_text)
    found = len(matches)
    expected = 13

    score = min(found / expected, 1.0)

    if found < expected:
        violations.append(
            f"found {found}/{expected} numbered sections"
        )
    field_details["sections_found"] = str(found)
    field_details["sections_expected"] = str(expected)

    return ScoredResult(
        score=round(score, 4),
        max_score=1.0,
        violations=violations,
        field_details=field_details,
        schema_group="report",
    )


# ---------------------------------------------------------------------------
# aggregate_workflow_score
# ---------------------------------------------------------------------------

_WEIGHTS = {
    "case_cards": 0.25,
    "composition_data": 0.20,
    "variant_files": 0.15,
    "report_sections": 0.15,
    "paper_list": 0.10,
    "uo_mapping": 0.10,
    "referential_integrity": 0.05,
}


def aggregate_workflow_score(scores: dict) -> float:
    """Weighted average of component scores.

    Args:
        scores: dict mapping component name to float (0.0-1.0).

    Returns:
        Weighted average as float (0.0-1.0).
    """
    total = 0.0
    weight_sum = 0.0
    for component, weight in _WEIGHTS.items():
        val = scores.get(component, 0.0)
        total += weight * val
        weight_sum += weight
    if weight_sum == 0.0:
        return 0.0
    return round(total / weight_sum, 6)
