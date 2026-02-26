"""Load and expose canonical schemas (Single Source of Truth).

All schema definitions live in assets/canonical_schemas.json.
This module loads them once and exposes convenience constants.
"""

import json
from pathlib import Path


def load_schemas() -> dict:
    """Load canonical_schemas.json (Single Source of Truth)."""
    path = Path(__file__).parent.parent / "assets" / "canonical_schemas.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


SCHEMAS = load_schemas()

# Convenience constants
CASE_CARD = SCHEMAS["case_card"]
PAPER_LIST = SCHEMAS["paper_list"]
VARIANT = SCHEMAS["variant"]
COMPOSITION_DATA = SCHEMAS["composition_data"]
CASE_ID_PATTERN = SCHEMAS["case_id_pattern"]
EVIDENCE_TAGS = SCHEMAS["evidence_tags"]
STEP_KEY_ALIASES = SCHEMAS["step_key_aliases"]
SCHEMA_VERSION = SCHEMAS["schema_version"]
