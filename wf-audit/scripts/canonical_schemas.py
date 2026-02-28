"""Expose canonical schema constants derived from Pydantic models.

Backward-compatible: referential_integrity.py imports CASE_ID_PATTERN
from this module, so the constant name and value must be preserved.
"""

from models.case_card import CaseCard, CaseMetadata, CaseStep
from models.paper_list import PaperList, Paper
from models.variant import Variant
from models.composition_data import CompositionData, Statistics


def _required_field_names(model_cls) -> list[str]:
    """Return list of required field names from a Pydantic model."""
    return [
        name for name, f_info in model_cls.model_fields.items()
        if f_info.is_required()
    ]


SCHEMA_VERSION = "2.0.0"

CASE_CARD = {
    "required_top_level": _required_field_names(CaseCard),
    "metadata_required": _required_field_names(CaseMetadata),
    "step_required": _required_field_names(CaseStep),
    "equipment_item": ["name", "model", "manufacturer"],
    "software_item": ["name", "version", "developer"],
}

PAPER_LIST = {
    "required_top_level": ["papers"],
    "recommended_top_level": ["search_date", "workflow_id", "total_papers"],
    "per_paper_required": _required_field_names(Paper),
}

VARIANT = {
    "required_top_level": _required_field_names(Variant),
    "variant_id_pattern": r"^V\d+$",
    "case_ref_accepted_keys": ["supporting_cases", "case_ids"],
}

COMPOSITION_DATA = {
    "schema_version_prefix": "4.",
    "required_top_level": _required_field_names(CompositionData),
    "statistics_standard": _required_field_names(Statistics),
    "statistics_deprecated_map": {
        "total_papers": "papers_analyzed",
        "total_cases": "cases_collected",
        "total_variants": "variants_identified",
        "total_uo_types": "total_uos",
    },
}

CASE_ID_PATTERN = r"^W[BTDL]\d{3}-C\d{3,}$"

EVIDENCE_TAGS = [
    "literature-direct", "literature-supplementary", "literature-consensus",
    "manufacturer-protocol", "expert-inference", "catalog-default",
]

STEP_KEY_ALIASES = {
    "step_number": ["position", "order"],
    "step_name": ["name"],
    "conditions": ["parameters"],
    "result_qc": ["qc_checkpoints", "qc_criteria", "qc_measures"],
    "description": ["action"],
}
