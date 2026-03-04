from __future__ import annotations
from typing import Literal
from .base import StrictModel

class UoStep(StrictModel):
    order: int
    uo_id: str | None = None
    uo_name: str
    is_hardware: bool = True

class UoComposition(StrictModel):
    steps: list[UoStep]
    description: str = ""

class VariantDefinition(StrictModel):
    variant_id: str
    workflow_id: str
    composition: UoComposition
    source_papers: list[str] = []
    panel_verdict: Literal["accept", "merge", "reject"] | None = None
    description: str = ""
    discovered_in_run: int = 0
