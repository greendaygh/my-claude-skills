"""Canonical Pydantic model for variant_V*.json.

This defines a single canonical format that all 8 existing variant
structures should be migrated to.

Canonical key mappings:
  - name → variant_name
  - case_refs / cases / supporting_cases → case_ids
  - uo_sequence (str list) → unit_operations (object list)
  - uo_sequence (obj list) → unit_operations (object list)
  - components.step1_* → unit_operations[0]
  - components.{input,...} → unit_operations[0].{input,...}
  - steps[] → unit_operations[]
  - uo_order / position / step_number → step_position
  - Input/Output (capital) → input/output (lowercase)
  - details[] → items[]
  - Material_Method / material_method → material_and_method
  - item (in details) → name (in items)
"""

from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator

from .base import ALLOW_EXTRA


# ---------------------------------------------------------------------------
# Item-level models for each of the 7 components
# Lenient canonical: accepts 'name' (canonical) or 'description' (legacy)
# ---------------------------------------------------------------------------

class InputItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: Optional[str] = None
    description: Optional[str] = None
    source_uo: Optional[str] = None
    specifications: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None

    @model_validator(mode="after")
    def require_name_or_description(self):
        if not self.name and not self.description:
            raise ValueError("name 또는 description 중 하나는 필수")
        return self


class OutputItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: Optional[str] = None
    description: Optional[str] = None
    destination_uo: Optional[str] = None
    specifications: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None

    @model_validator(mode="after")
    def require_name_or_description(self):
        if not self.name and not self.description:
            raise ValueError("name 또는 description 중 하나는 필수")
        return self


class EquipmentItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: Optional[str] = None
    description: Optional[str] = None
    model: Optional[str] = None
    manufacturer: Optional[str] = None
    settings: Optional[dict] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None

    @model_validator(mode="after")
    def require_name_or_description(self):
        if not self.name and not self.description:
            raise ValueError("name 또는 description 중 하나는 필수")
        return self


class ConsumableItem(BaseModel):
    model_config = ALLOW_EXTRA

    name: Optional[str] = None
    description: Optional[str] = None
    catalog: Optional[str] = None
    quantity: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None

    @model_validator(mode="after")
    def require_name_or_description(self):
        if not self.name and not self.description:
            raise ValueError("name 또는 description 중 하나는 필수")
        return self


class MeasurementItem(BaseModel):
    model_config = ALLOW_EXTRA

    metric: str
    value: Any = None
    method: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None


class QcCheckpoint(BaseModel):
    model_config = ALLOW_EXTRA

    measurement: Optional[str] = None
    pass_criteria: Optional[str] = None
    fail_action: Optional[str] = None
    evidence_tag: Optional[str] = None


class TroubleshootingItem(BaseModel):
    model_config = ALLOW_EXTRA

    issue: str
    solution: Optional[str] = None
    case_ref: Optional[str] = None


# ---------------------------------------------------------------------------
# Component-level models (7 canonical components)
# ---------------------------------------------------------------------------

class InputComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    items: list[InputItem] = Field(default_factory=list)


class OutputComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    items: list[OutputItem] = Field(default_factory=list)


class EquipmentComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    items: list[EquipmentItem] = Field(default_factory=list)


class ConsumablesComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    items: list[ConsumableItem] = Field(default_factory=list)


class MaterialAndMethodComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    environment: Optional[str] = None
    procedure: Optional[str] = None
    case_refs: list[str] = Field(default_factory=list)
    evidence_tag: Optional[str] = None


class ResultComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    measurements: list[MeasurementItem] = Field(default_factory=list)
    qc_checkpoint: Optional[QcCheckpoint] = None


class DiscussionComponent(BaseModel):
    model_config = ALLOW_EXTRA

    description: Optional[str] = None
    interpretation: Optional[str] = None
    troubleshooting: list[TroubleshootingItem] = Field(default_factory=list)
    special_notes: Optional[str] = None
    evidence_tag: Optional[str] = None


# ---------------------------------------------------------------------------
# UnitOperation: one step in a variant workflow
# ---------------------------------------------------------------------------

class UnitOperation(BaseModel):
    model_config = ALLOW_EXTRA

    uo_id: str
    uo_name: str
    step_position: int
    input: InputComponent
    output: OutputComponent
    equipment: EquipmentComponent
    consumables: ConsumablesComponent
    material_and_method: MaterialAndMethodComponent
    result: ResultComponent
    discussion: DiscussionComponent


# ---------------------------------------------------------------------------
# Variant: top-level canonical model
# ---------------------------------------------------------------------------

class Variant(BaseModel):
    model_config = ALLOW_EXTRA

    variant_id: str
    variant_name: str
    workflow_id: str = Field(pattern=r"^W[BTDL]\d{3}$")
    schema_version: Optional[str] = None
    analysis_date: Optional[str] = None
    qualifier: Optional[str] = None
    case_ids: list[str] = Field(default_factory=list)
    case_count: Optional[int] = None
    defining_features: Optional[dict] = None
    notes: Optional[str] = None
    unit_operations: list[UnitOperation]
