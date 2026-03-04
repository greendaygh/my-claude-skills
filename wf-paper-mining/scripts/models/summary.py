from __future__ import annotations
from .base import StrictModel
from .variant import VariantDefinition

class FrequencyItem(StrictModel):
    name: str
    count: int
    source_papers: list[str]
    type: str = ""

class UoSummary(StrictModel):
    catalog_id: str | None = None
    name: str
    is_new: bool = False
    occurrence_count: int = 0
    source_papers: list[str] = []

class ResourceSummary(StrictModel):
    workflow_id: str
    generated: str
    total_papers: int
    total_extractions: int
    workflows: list[UoSummary] = []
    hardware_uos: list[UoSummary] = []
    software_uos: list[UoSummary] = []
    equipment: list[FrequencyItem] = []
    consumables: list[FrequencyItem] = []
    reagents: list[FrequencyItem] = []
    samples: list[FrequencyItem] = []
    new_catalog_candidates: list[dict] = []

class VariantSummary(StrictModel):
    workflow_id: str
    generated: str
    total_variants: int = 0
    variants: list[VariantDefinition] = []
    new_since_last_run: list[str] = []
