"""Canonical Pydantic model for case_C*.json (case cards).

Canonical key mappings (step fields):
  - position → step_number
  - name → step_name
  - action → step_name
  - parameters → conditions
  - qc_checkpoints / qc_criteria → result_qc
"""

from typing import Any, Optional

from pydantic import BaseModel, Field

from .base import ALLOW_EXTRA


class EquipmentItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: str
    model: Optional[str] = None
    manufacturer: Optional[str] = None


class SoftwareItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: str
    version: Optional[str] = None
    developer: Optional[str] = None


class CaseStep(BaseModel):
    model_config = ALLOW_EXTRA

    step_number: int | str
    step_name: str
    description: str
    equipment: list[EquipmentItem | str] = Field(default_factory=list)
    software: list[SoftwareItem | str] = Field(default_factory=list)
    reagents: Any = None
    conditions: Any = None
    result_qc: Any = None
    notes: Optional[str] = None


class CaseMetadata(BaseModel):
    model_config = ALLOW_EXTRA

    pmid: Optional[str] = None
    doi: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    title: str
    purpose: Optional[str] = None
    organism: Optional[str] = None
    scale: Optional[str] = None
    core_technique: Optional[str] = None
    automation_level: Optional[str] = None
    fulltext_access: Optional[bool | str] = None
    access_method: Optional[str] = None
    access_tier: Optional[int] = None


class Completeness(BaseModel):
    model_config = ALLOW_EXTRA

    score: float | int | str
    details: Optional[Any] = None
    notes: Optional[str] = None


class WorkflowContextRef(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    boundary_inputs: Optional[list[str]] = None
    boundary_outputs: Optional[list[str]] = None


class CaseCard(BaseModel):
    model_config = ALLOW_EXTRA

    case_id: str = Field(pattern=r"^W[BTDL]\d{3}-C\d{3,}$")
    metadata: CaseMetadata
    steps: list[CaseStep]
    completeness: Completeness
    flow_diagram: str
    workflow_context: WorkflowContextRef
