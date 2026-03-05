from __future__ import annotations
from pydantic import field_validator
from .base import StrictModel, FlexModel


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
