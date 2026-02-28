"""Canonical Pydantic model for composition_data.json.

Canonical key mappings:
  - stats → statistics
  - composition_version → version
  - analysis_date → composition_date
  - total_papers → papers_analyzed
  - total_cases → cases_collected
  - total_variants → variants_identified
"""

from typing import Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


class Statistics(BaseModel):
    model_config = ALLOW_EXTRA

    papers_analyzed: int
    cases_collected: int
    variants_identified: int
    total_uos: int
    qc_checkpoints: int
    confidence_score: float = Field(ge=0.0, le=1.0)


class Modularity(BaseModel):
    model_config = ALLOW_EXTRA

    boundary_inputs: list[str]
    boundary_outputs: list[str]


class CompositionData(BaseModel):
    model_config = ALLOW_EXTRA

    schema_version: str = Field(pattern=r"^4\.\d+\.\d+$")
    workflow_id: str = Field(pattern=r"^W[BTDL]\d{3}$")
    workflow_name: str
    category: str
    domain: str
    version: int | float
    composition_date: str
    description: str
    statistics: Statistics
    modularity: Optional[Modularity] = None
