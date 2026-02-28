"""Conformance scoring engine for workflow audit (0.0-1.0 scale).

Uses Pydantic v2 models as the single source of truth for canonical schemas.
Each score_* function validates data against its Pydantic model and converts
ValidationErrors into scored results with detailed violation locations.
"""

from dataclasses import dataclass, field
import re

from pydantic import ValidationError

from models import (
    CaseCard,
    CaseSummary,
    ClusterResult,
    CommonPattern,
    CompositionData,
    ParameterRanges,
    Paper,
    PaperList,
    QcCheckpoints,
    StepAlignment,
    UoMapping,
    Variant,
    WorkflowContext,
)
from models.base import DetailedViolation, pydantic_errors_to_violations


@dataclass
class ScoredResult:
    score: float                                         # 0.0-1.0
    max_score: float
    violations: list = field(default_factory=list)
    detailed_violations: list = field(default_factory=list)
    field_details: dict = field(default_factory=dict)
    schema_group: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _count_required_fields(model_cls) -> int:
    """Count required (non-optional) fields in a Pydantic model."""
    count = 0
    for f_info in model_cls.model_fields.values():
        if f_info.is_required():
            count += 1
    return count


def _score_from_errors(error_count: int, total_fields: int) -> float:
    if total_fields == 0:
        return 1.0
    return max(0.0, round(1.0 - error_count / total_fields, 4))


def _classify_case_card(data: dict) -> str:
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

def score_case_card(case_data: dict, source_file: str = "") -> ScoredResult:
    """Score a case card against canonical CaseCard model."""
    schema_group = _classify_case_card(case_data)
    record_id = case_data.get("case_id", "unknown")

    try:
        CaseCard.model_validate(case_data)
        return ScoredResult(
            score=1.0, max_score=1.0,
            violations=[], detailed_violations=[],
            field_details={}, schema_group=schema_group,
        )
    except ValidationError as e:
        detailed = pydantic_errors_to_violations(
            e.errors(), source_file=source_file, record_id=record_id,
        )
        violations = [f"{d.path}: {d.error}" for d in detailed]
        total = _count_required_fields(CaseCard) + 10  # metadata + step fields
        score = _score_from_errors(len(e.errors()), total)
        return ScoredResult(
            score=score, max_score=1.0,
            violations=violations,
            detailed_violations=[d.to_dict() for d in detailed],
            field_details={}, schema_group=schema_group,
        )


# ---------------------------------------------------------------------------
# score_paper_list
# ---------------------------------------------------------------------------

def score_paper_list(paper_data, source_file: str = "") -> ScoredResult:
    """Score paper_list.json against canonical PaperList model."""
    if not isinstance(paper_data, dict):
        return ScoredResult(
            score=0.0, max_score=1.0,
            violations=["top-level must be a dict with 'papers' key"],
            detailed_violations=[],
            field_details={}, schema_group="unknown",
        )

    record_id = paper_data.get("workflow_id", "unknown")

    try:
        PaperList.model_validate(paper_data)
        return ScoredResult(
            score=1.0, max_score=1.0,
            violations=[], detailed_violations=[],
            field_details={}, schema_group="canonical",
        )
    except ValidationError as e:
        detailed = pydantic_errors_to_violations(
            e.errors(), source_file=source_file, record_id=record_id,
        )
        # Enrich record info for per-paper errors
        papers = paper_data.get("papers", [])
        for d in detailed:
            parts = d.path.split(".")
            if len(parts) >= 2 and parts[0] == "papers" and parts[1].isdigit():
                idx = int(parts[1])
                if isinstance(papers, list) and idx < len(papers):
                    paper = papers[idx]
                    if isinstance(paper, dict):
                        d.record = paper.get("paper_id", paper.get("id", f"papers[{idx}]"))

        violations = [f"{d.path}: {d.error}" for d in detailed]
        total_fields = _count_required_fields(PaperList)
        n_papers = len(papers) if isinstance(papers, list) else 0
        total = total_fields + n_papers * _count_required_fields(Paper)
        score = _score_from_errors(len(e.errors()), max(total, 1))
        return ScoredResult(
            score=score, max_score=1.0,
            violations=violations,
            detailed_violations=[d.to_dict() for d in detailed],
            field_details={}, schema_group="canonical" if "papers" in paper_data else "unknown",
        )


# ---------------------------------------------------------------------------
# score_variant
# ---------------------------------------------------------------------------

def score_variant(variant_data: dict, source_file: str = "") -> ScoredResult:
    """Score a variant file against canonical Variant model."""
    record_id = variant_data.get("variant_id", "unknown")

    try:
        Variant.model_validate(variant_data)
        return ScoredResult(
            score=1.0, max_score=1.0,
            violations=[], detailed_violations=[],
            field_details={}, schema_group="canonical",
        )
    except ValidationError as e:
        detailed = pydantic_errors_to_violations(
            e.errors(), source_file=source_file, record_id=record_id,
        )
        violations = [f"{d.path}: {d.error}" for d in detailed]
        total = _count_required_fields(Variant) + 5
        score = _score_from_errors(len(e.errors()), max(total, 1))
        return ScoredResult(
            score=score, max_score=1.0,
            violations=violations,
            detailed_violations=[d.to_dict() for d in detailed],
            field_details={}, schema_group="non_canonical" if violations else "canonical",
        )


# ---------------------------------------------------------------------------
# score_composition_data
# ---------------------------------------------------------------------------

def score_composition_data(comp_data: dict, source_file: str = "") -> ScoredResult:
    """Score composition_data.json against canonical CompositionData model."""
    record_id = comp_data.get("workflow_id", "unknown")

    try:
        CompositionData.model_validate(comp_data)
        return ScoredResult(
            score=1.0, max_score=1.0,
            violations=[], detailed_violations=[],
            field_details={}, schema_group="canonical",
        )
    except ValidationError as e:
        detailed = pydantic_errors_to_violations(
            e.errors(), source_file=source_file, record_id=record_id,
        )
        violations = [f"{d.path}: {d.error}" for d in detailed]
        total = _count_required_fields(CompositionData) + _count_required_fields(
            __import__("models.composition_data", fromlist=["Statistics"]).Statistics
        )
        score = _score_from_errors(len(e.errors()), max(total, 1))
        return ScoredResult(
            score=score, max_score=1.0,
            violations=violations,
            detailed_violations=[d.to_dict() for d in detailed],
            field_details={}, schema_group="non_canonical" if violations else "canonical",
        )


# ---------------------------------------------------------------------------
# New: score functions for the 9 additional file types
# ---------------------------------------------------------------------------

def _score_generic(model_cls, data: dict, source_file: str = "", record_key: str = "workflow_id") -> ScoredResult:
    """Generic Pydantic validation scorer for any model."""
    record_id = data.get(record_key, "unknown") if isinstance(data, dict) else "unknown"
    if not isinstance(data, dict):
        return ScoredResult(
            score=0.0, max_score=1.0,
            violations=[f"expected dict, got {type(data).__name__}"],
            detailed_violations=[], field_details={}, schema_group="unknown",
        )
    try:
        model_cls.model_validate(data)
        return ScoredResult(
            score=1.0, max_score=1.0,
            violations=[], detailed_violations=[],
            field_details={}, schema_group="canonical",
        )
    except ValidationError as e:
        detailed = pydantic_errors_to_violations(
            e.errors(), source_file=source_file, record_id=record_id,
        )
        violations = [f"{d.path}: {d.error}" for d in detailed]
        total = _count_required_fields(model_cls) + 3
        score = _score_from_errors(len(e.errors()), max(total, 1))
        return ScoredResult(
            score=score, max_score=1.0,
            violations=violations,
            detailed_violations=[d.to_dict() for d in detailed],
            field_details={}, schema_group="non_canonical" if violations else "canonical",
        )


def score_case_summary(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(CaseSummary, data, source_file)

def score_cluster_result(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(ClusterResult, data, source_file)

def score_common_pattern(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(CommonPattern, data, source_file)

def score_parameter_ranges(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(ParameterRanges, data, source_file)

def score_step_alignment(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(StepAlignment, data, source_file)

def score_uo_mapping(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(UoMapping, data, source_file)

def score_qc_checkpoints(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(QcCheckpoints, data, source_file)

def score_workflow_context(data: dict, source_file: str = "") -> ScoredResult:
    return _score_generic(WorkflowContext, data, source_file)


# ---------------------------------------------------------------------------
# score_report_sections (unchanged — no Pydantic model for markdown)
# ---------------------------------------------------------------------------

def score_report_sections(report_text: str) -> ScoredResult:
    """Score a report for 13 required numbered sections."""
    violations = []
    field_details = {}

    pattern = re.compile(r"^#{1,3}\s*\d+\.", re.MULTILINE)
    matches = pattern.findall(report_text)
    found = len(matches)
    expected = 13

    score = min(found / expected, 1.0)

    if found < expected:
        violations.append(f"found {found}/{expected} numbered sections")
    field_details["sections_found"] = str(found)
    field_details["sections_expected"] = str(expected)

    return ScoredResult(
        score=round(score, 4),
        max_score=1.0,
        violations=violations,
        detailed_violations=[],
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
    """Weighted average of component scores."""
    total = 0.0
    weight_sum = 0.0
    for component, weight in _WEIGHTS.items():
        val = scores.get(component, 0.0)
        total += weight * val
        weight_sum += weight
    if weight_sum == 0.0:
        return 0.0
    return round(total / weight_sum, 6)
