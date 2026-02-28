"""Canonical Pydantic model for case_summary.json.

Canonical key mappings:
  - variant_clusters (object or array) → cases (array)
"""

from typing import Optional

from pydantic import BaseModel

from .base import ALLOW_EXTRA


class CaseSummaryEntry(BaseModel):
    model_config = ALLOW_EXTRA

    case_id: str
    paper_id: Optional[str] = None
    technique: Optional[str] = None
    organism: Optional[str] = None
    scale: Optional[str] = None
    access_tier: Optional[int] = None


class CaseSummary(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    total_cases: int
    cases: list[CaseSummaryEntry]
