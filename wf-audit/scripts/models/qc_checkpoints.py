"""Canonical Pydantic model for qc_checkpoints.json.

Lenient canonical: accepts 'checkpoint_id' (canonical) or 'qc_id' (legacy).
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from .base import ALLOW_EXTRA


class Checkpoint(BaseModel):
    model_config = ALLOW_EXTRA

    checkpoint_id: Optional[str] = None
    qc_id: Optional[str] = None
    name: Optional[str] = None
    position: Optional[str | int] = None
    applicable_variants: Optional[list[str]] = None
    type: Optional[str] = None
    description: Optional[str] = None
    criteria: Optional[Any] = None
    evidence_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_id(self):
        if not self.checkpoint_id and not self.qc_id:
            raise ValueError("checkpoint_id 또는 qc_id 중 하나는 필수")
        return self


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
