"""Canonical Pydantic models for all workflow composition JSON file types.

Each model defines the single canonical schema that all workflows
should conform to. Deviations are reported as violations by the
audit scoring engine.
"""

from .base import DetailedViolation, pydantic_errors_to_violations
from .composition_data import CompositionData, Modularity, Statistics
from .paper_list import Paper, PaperList
from .case_card import (
    CaseCard,
    CaseMetadata,
    CaseStep,
    Completeness,
    EquipmentItem as CaseEquipmentItem,
    SoftwareItem,
    WorkflowContextRef,
)
from .case_summary import CaseSummary, CaseSummaryEntry
from .variant import (
    ConsumableItem,
    ConsumablesComponent,
    DiscussionComponent,
    EquipmentComponent,
    EquipmentItem as VariantEquipmentItem,
    InputComponent,
    InputItem,
    MaterialAndMethodComponent,
    MeasurementItem,
    OutputComponent,
    OutputItem,
    QcCheckpoint,
    ResultComponent,
    TroubleshootingItem,
    UnitOperation,
    Variant,
)
from .uo_mapping import UoAssignment, UoMapping
from .qc_checkpoints import Checkpoint, CheckpointSummary, QcCheckpoints
from .analysis import (
    AlignmentEntry,
    ClusterResult,
    ClusterVariant,
    CommonPattern,
    CommonStep,
    ParameterEntry,
    ParameterRanges,
    StepAlignment,
    WorkflowSkeleton,
)
from .workflow_context import PreviousStats, WorkflowContext

__all__ = [
    # base
    "DetailedViolation",
    "pydantic_errors_to_violations",
    # composition_data
    "CompositionData",
    "Modularity",
    "Statistics",
    # paper_list
    "Paper",
    "PaperList",
    # case_card
    "CaseCard",
    "CaseMetadata",
    "CaseStep",
    "Completeness",
    "CaseEquipmentItem",
    "SoftwareItem",
    "WorkflowContextRef",
    # case_summary
    "CaseSummary",
    "CaseSummaryEntry",
    # variant
    "Variant",
    "UnitOperation",
    "InputComponent",
    "InputItem",
    "OutputComponent",
    "OutputItem",
    "EquipmentComponent",
    "VariantEquipmentItem",
    "ConsumablesComponent",
    "ConsumableItem",
    "MaterialAndMethodComponent",
    "ResultComponent",
    "MeasurementItem",
    "QcCheckpoint",
    "DiscussionComponent",
    "TroubleshootingItem",
    # uo_mapping
    "UoMapping",
    "UoAssignment",
    # qc_checkpoints
    "QcCheckpoints",
    "Checkpoint",
    "CheckpointSummary",
    # analysis
    "ClusterResult",
    "ClusterVariant",
    "CommonPattern",
    "CommonStep",
    "WorkflowSkeleton",
    "ParameterRanges",
    "ParameterEntry",
    "StepAlignment",
    "AlignmentEntry",
    # workflow_context
    "WorkflowContext",
    "PreviousStats",
]
