"""Canonical Pydantic model for qc_checkpoints.json."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


class Checkpoint(BaseModel):
    model_config = ALLOW_EXTRA

    checkpoint_id: str
    name: str
    position: Optional[str | int] = None
    applicable_variants: Optional[list[str]] = None
    type: Optional[str] = None
    description: Optional[str] = None
    criteria: Optional[Any] = None
    evidence_tags: list[str] = Field(default_factory=list)


class CheckpointSummary(BaseModel):
    model_config = ALLOW_EXTRA

    total_checkpoints: Optional[int] = None
    universal_checkpoints: Optional[int] = None
    method_specific_checkpoints: Optional[int] = None


class QcCheckpoints(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    workflow_name: Optional[str] = None
    analysis_date: Optional[str] = None
    total_cases: Optional[int] = None
    schema_version: Optional[str] = None
    notes: Optional[str] = None
    checkpoints: list[Checkpoint]
    checkpoint_summary: Optional[CheckpointSummary] = None
