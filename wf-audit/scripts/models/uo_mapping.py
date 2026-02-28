"""Canonical Pydantic model for uo_mapping.json."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


class UoAssignment(BaseModel):
    model_config = ALLOW_EXTRA

    step_position: int | str
    step_function: Optional[str] = None
    applicable_variants: Optional[list[str]] = None
    primary_uo: str
    primary_uo_name: Optional[str] = None
    score_breakdown: Optional[Any] = None
    composite_score: Optional[float] = None
    alternative_uo: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)


class UoMapping(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: Optional[int] = None
    schema_version: Optional[str] = None
    notes: Optional[str] = None
    scoring_weights: Optional[dict] = None
    uo_assignments: list[UoAssignment]
