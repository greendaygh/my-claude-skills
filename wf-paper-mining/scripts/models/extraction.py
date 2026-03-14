from __future__ import annotations
import json
from pydantic import field_validator, model_validator
from typing import Any
from .base import StrictModel, FlexModel


def _remap_name_fields(values: dict, name_aliases: tuple[str, ...],
                       catalog_aliases: tuple[str, ...]) -> dict:
    """Remap common LLM field-name variants to canonical names."""
    if not isinstance(values, dict):
        return values
    # name aliases: workflow_name, uo_name -> name
    if "name" not in values:
        for alias in name_aliases:
            if alias in values:
                values["name"] = values.pop(alias)
                break
    # catalog_id aliases: workflow_id, uo_id -> catalog_id
    if "catalog_id" not in values:
        for alias in catalog_aliases:
            if alias in values:
                values["catalog_id"] = values.pop(alias)
                break
    return values


def _coerce_str_fields(values: dict, fields: tuple[str, ...]) -> dict:
    """Convert dict/list values to JSON strings for fields that expect str."""
    if not isinstance(values, dict):
        return values
    for field in fields:
        if field in values and isinstance(values[field], (dict, list)):
            values[field] = json.dumps(values[field], ensure_ascii=False)
    return values


class HardwareUoRef(FlexModel):
    catalog_id: str | None = None
    name: str
    is_new: bool = False
    input: str = ""
    output: str = ""
    equipment: str = ""
    consumables: str = ""
    material_and_method: str = ""
    result: str = ""
    discussion: str = ""
    confidence: float = 0.0
    source_section: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        values = _remap_name_fields(
            values,
            name_aliases=("uo_name", "unit_operation_name"),
            catalog_aliases=("uo_id", "unit_operation_id"),
        )
        values = _coerce_str_fields(
            values,
            fields=("input", "output", "equipment", "consumables",
                    "material_and_method", "result", "discussion"),
        )
        return values

    @field_validator("confidence")
    @classmethod
    def check_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class SoftwareUoRef(FlexModel):
    catalog_id: str | None = None
    name: str
    is_new: bool = False
    input: str = ""
    output: str = ""
    parameters: str = ""
    environment: str = ""
    method: str = ""
    result: str = ""
    discussion: str = ""
    confidence: float = 0.0
    source_section: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        values = _remap_name_fields(
            values,
            name_aliases=("uo_name", "unit_operation_name"),
            catalog_aliases=("uo_id", "unit_operation_id"),
        )
        values = _coerce_str_fields(
            values,
            fields=("input", "output", "parameters", "environment",
                    "method", "result", "discussion"),
        )
        return values

    @field_validator("confidence")
    @classmethod
    def check_confidence(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
        return v


class WorkflowRef(FlexModel):
    catalog_id: str | None = None
    name: str
    description: str = ""
    is_new: bool = False
    confidence: float = 0.0
    source_section: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_fields(cls, values: Any) -> Any:
        if not isinstance(values, dict):
            return values
        values = _remap_name_fields(
            values,
            name_aliases=("workflow_name",),
            catalog_aliases=("workflow_id",),
        )
        return values


class EquipmentEntry(FlexModel):
    name: str
    manufacturer: str | None = None
    model: str | None = None
    settings: str = ""
    mapped_uo_id: str | None = None
    confidence: float = 0.0
    source_section: str = ""


class ConsumableEntry(FlexModel):
    name: str
    type: str = ""
    manufacturer: str | None = None
    catalog_number: str | None = None
    specification: str | None = None
    confidence: float = 0.0
    source_section: str = ""


class ReagentEntry(FlexModel):
    name: str
    type: str = ""
    manufacturer: str | None = None
    catalog_number: str | None = None
    concentration: str | None = None
    confidence: float = 0.0
    source_section: str = ""


class SampleEntry(FlexModel):
    name: str
    type: str = ""
    organism: str | None = None
    source: str | None = None
    description: str = ""
    confidence: float = 0.0
    source_section: str = ""


class UoConnection(FlexModel):
    from_uo: str
    to_uo: str
    transfer_type: str = "sample"
    transfer_object: str = ""
    confidence: float = 0.0


class QcCheckpoint(FlexModel):
    name: str
    after_uo: str = ""
    metric: str = ""
    threshold: str | None = None
    action_on_fail: str | None = None
    confidence: float = 0.0


class ExtractionResult(FlexModel):
    """FlexModel to tolerate extra fields from LLM-generated extractions."""
    paper_id: str
    workflow_id: str = ""
    extraction_date: str = ""
    workflows: list[WorkflowRef] = []
    hardware_uos: list[HardwareUoRef] = []
    software_uos: list[SoftwareUoRef] = []
    equipment: list[EquipmentEntry] = []
    consumables: list[ConsumableEntry] = []
    reagents: list[ReagentEntry] = []
    samples: list[SampleEntry] = []
    uo_connections: list[UoConnection] = []
    qc_checkpoints: list[QcCheckpoint] = []
    new_uo_candidates: list[str] = []
    notes: str = ""
