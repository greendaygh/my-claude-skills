"""Canonical Pydantic model for workflow_context.json."""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


class PreviousStats(BaseModel):
    model_config = ALLOW_EXTRA

    papers_analyzed: Optional[int] = None
    cases_collected: Optional[int] = None
    variants_identified: Optional[int] = None
    total_uos: Optional[int] = None
    qc_checkpoints: Optional[int] = None
    confidence_score: Optional[float] = None


class WorkflowContext(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str = Field(pattern=r"^W[BTDL]\d{3}$")
    workflow_name: str
    category: Optional[str] = None
    domain: Optional[str] = None
    description: Optional[str] = None
    mode: Optional[str] = None
    previous_version: Optional[int | float] = None
    target_version: Optional[int | float] = None
    composition_date: Optional[str] = None
    backup_path: Optional[str] = None
    previous_stats: Optional[PreviousStats] = None
