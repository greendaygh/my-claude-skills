"""Canonical Pydantic models for 03_analysis/ files.

Covers:
  - cluster_result.json
  - common_pattern.json
  - parameter_ranges.json
  - step_alignment.json
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


# ---------------------------------------------------------------------------
# cluster_result.json
# ---------------------------------------------------------------------------

class ClusterVariant(BaseModel):
    model_config = ALLOW_EXTRA

    variant_id: str
    name: str
    qualifier: Optional[str] = None
    case_ids: list[str] = Field(default_factory=list)
    case_count: Optional[int] = None
    defining_features: Optional[Any] = None


class ClusterResult(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: int
    clustering_method: Optional[str] = None
    primary_axis: Optional[str] = None
    secondary_axes: Optional[list[str]] = None
    notes: Optional[str] = None
    variants: list[ClusterVariant]


# ---------------------------------------------------------------------------
# common_pattern.json
# ---------------------------------------------------------------------------

class CommonStep(BaseModel):
    model_config = ALLOW_EXTRA

    step_function: Optional[str] = None
    description: Optional[str] = None
    frequency: Optional[float | int] = None
    mandatory: Optional[bool] = None


class WorkflowSkeleton(BaseModel):
    model_config = ALLOW_EXTRA

    common_steps: list[CommonStep] = Field(default_factory=list)


class CommonPattern(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: int
    threshold_mandatory: Optional[float] = None
    notes: Optional[str] = None
    workflow_skeleton: WorkflowSkeleton


# ---------------------------------------------------------------------------
# parameter_ranges.json
# ---------------------------------------------------------------------------

class ParameterEntry(BaseModel):
    model_config = ALLOW_EXTRA

    step_function: Optional[str] = None
    parameter: str
    unit: Optional[str] = None
    values_by_case: Optional[Any] = None
    by_variant: Optional[Any] = None
    overall: Optional[Any] = None


class ParameterRanges(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: int
    aggregation_method: Optional[str] = None
    notes: Optional[str] = None
    parameters: list[ParameterEntry]


# ---------------------------------------------------------------------------
# step_alignment.json
# ---------------------------------------------------------------------------

class AlignmentEntry(BaseModel):
    model_config = ALLOW_EXTRA

    aligned_position: int | str
    function: Optional[str] = None
    description: Optional[str] = None
    cases: Optional[Any] = None


class StepAlignment(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: int
    alignment_method: Optional[str] = None
    notes: Optional[str] = None
    alignment: list[AlignmentEntry]
