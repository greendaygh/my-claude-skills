"""Tests for canonical_schemas.py — schema loading and constant verification."""

import json
import re
import sys
from pathlib import Path

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


def test_json_loads_successfully():
    """canonical_schemas.json is valid JSON and loads without error."""
    json_path = Path(__file__).parent.parent / "assets" / "canonical_schemas.json"
    assert json_path.exists(), f"Missing {json_path}"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert isinstance(data, dict)
    assert "schema_version" in data


def test_schema_version():
    from canonical_schemas import SCHEMA_VERSION
    assert SCHEMA_VERSION == "1.0.0"


def test_case_card_constants():
    from canonical_schemas import CASE_CARD
    assert "required_top_level" in CASE_CARD
    assert "metadata_required" in CASE_CARD
    assert "step_required" in CASE_CARD
    assert "equipment_item" in CASE_CARD
    assert "software_item" in CASE_CARD
    # Check specific required fields
    assert "case_id" in CASE_CARD["required_top_level"]
    assert "metadata" in CASE_CARD["required_top_level"]
    assert "steps" in CASE_CARD["required_top_level"]
    assert "pmid" in CASE_CARD["metadata_required"]
    assert "step_number" in CASE_CARD["step_required"]


def test_paper_list_constants():
    from canonical_schemas import PAPER_LIST
    assert "required_top_level" in PAPER_LIST
    assert "papers" in PAPER_LIST["required_top_level"]
    assert "per_paper_required" in PAPER_LIST
    assert "paper_id" in PAPER_LIST["per_paper_required"]
    assert "doi" in PAPER_LIST["per_paper_required"]


def test_variant_constants():
    from canonical_schemas import VARIANT
    assert "required_top_level" in VARIANT
    assert "variant_id" in VARIANT["required_top_level"]
    assert "uo_sequence" in VARIANT["required_top_level"]
    assert "variant_id_pattern" in VARIANT
    # Pattern should be a valid regex
    re.compile(VARIANT["variant_id_pattern"])


def test_composition_data_constants():
    from canonical_schemas import COMPOSITION_DATA
    assert "required_top_level" in COMPOSITION_DATA
    assert "statistics_standard" in COMPOSITION_DATA
    assert "statistics_deprecated_map" in COMPOSITION_DATA
    assert "schema_version_prefix" in COMPOSITION_DATA
    assert COMPOSITION_DATA["schema_version_prefix"] == "4."
    # Standard statistics fields
    std = COMPOSITION_DATA["statistics_standard"]
    assert "papers_analyzed" in std
    assert "cases_collected" in std
    assert "confidence_score" in std


def test_case_id_pattern():
    from canonical_schemas import CASE_ID_PATTERN
    pattern = re.compile(CASE_ID_PATTERN)
    # Valid patterns
    assert pattern.match("WB005-C001")
    assert pattern.match("WT050-C123")
    assert pattern.match("WD010-C0001")
    assert pattern.match("WL020-C999")
    # Invalid patterns
    assert not pattern.match("C001")
    assert not pattern.match("WB005-C01")  # too few digits
    assert not pattern.match("WX005-C001")  # X not valid


def test_evidence_tags():
    from canonical_schemas import EVIDENCE_TAGS
    assert isinstance(EVIDENCE_TAGS, list)
    assert "literature-direct" in EVIDENCE_TAGS
    assert "catalog-default" in EVIDENCE_TAGS
    assert len(EVIDENCE_TAGS) == 6


def test_step_key_aliases():
    from canonical_schemas import STEP_KEY_ALIASES
    assert "step_number" in STEP_KEY_ALIASES
    assert "position" in STEP_KEY_ALIASES["step_number"]
    assert "conditions" in STEP_KEY_ALIASES
    assert "parameters" in STEP_KEY_ALIASES["conditions"]
    assert "description" in STEP_KEY_ALIASES
    assert "action" in STEP_KEY_ALIASES["description"]


def test_deprecated_statistics_map():
    from canonical_schemas import COMPOSITION_DATA
    dep = COMPOSITION_DATA["statistics_deprecated_map"]
    # Each deprecated name maps to a standard name
    std = COMPOSITION_DATA["statistics_standard"]
    for deprecated, canonical in dep.items():
        assert canonical in std, f"{deprecated} maps to {canonical} which is not in standard fields"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
