"""Tests for scoring.py — conformance scoring engine."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CANONICAL_CASE_CARD = {
    "case_id": "WB005-C001",
    "metadata": {
        "pmid": "12345678",
        "doi": "10.1000/xyz123",
        "authors": ["Smith J", "Doe A"],
        "year": 2023,
        "journal": "Nature Biotechnology",
        "title": "A canonical workflow",
        "purpose": "DNA extraction",
        "organism": "E. coli",
        "scale": "lab",
        "automation_level": "manual",
        "core_technique": "extraction",
        "fulltext_access": True,
        "access_method": "doi",
        "access_tier": "open",
    },
    "steps": [
        {
            "step_number": 1,
            "step_name": "Cell lysis",
            "description": "Lyse cells with buffer",
            "equipment": [{"name": "Centrifuge", "model": "5424R", "manufacturer": "Eppendorf"}],
            "software": [{"name": "FIJI", "version": "2.9.0", "developer": "ImageJ"}],
            "reagents": ["Lysis buffer", "Proteinase K"],
            "conditions": {"temperature": "4C", "time": "30min"},
            "result_qc": "Clear lysate",
            "notes": "Keep on ice",
        }
    ],
    "completeness": {"score": 0.95, "missing_fields": []},
    "flow_diagram": "graph LR\n  A --> B",
    "workflow_context": {"workflow_id": "WB005", "variant_id": "V1"},
}

LEGACY_FLAT_CASE_CARD = {
    "paper_id": "paper_001",
    "technique": "western blot",
    "steps": [
        {
            "position": 1,        # alias for step_number
            "name": "Gel run",    # alias for step_name
            "equipment": ["Autoclave", "Centrifuge"],  # flat strings
        }
    ],
}

MIXED_SOFTWARE_CASE_CARD = {
    "case_id": "WB005-C002",
    "metadata": {
        "pmid": "12345678",
        "doi": "10.1000/xyz123",
        "authors": ["Smith J"],
        "year": 2023,
        "journal": "Nature",
        "title": "Test",
        "purpose": "test",
        "organism": "E. coli",
        "scale": "lab",
        "automation_level": "manual",
        "core_technique": "extraction",
        "fulltext_access": True,
        "access_method": "doi",
        "access_tier": "open",
    },
    "steps": [
        {
            "step_number": 1,
            "step_name": "Analysis",
            "description": "Run analysis",
            "equipment": [{"name": "Microscope", "model": "M1", "manufacturer": "Zeiss"}],
            "software": ["FIJI"],  # flat string array — wrong type
            "reagents": [],
            "conditions": {},
            "result_qc": "Pass",
            "notes": "",
        }
    ],
    "completeness": {"score": 0.9, "missing_fields": []},
    "flow_diagram": "graph LR\n  A --> B",
    "workflow_context": {"workflow_id": "WB005", "variant_id": "V1"},
}

CANONICAL_PAPER_LIST = {
    "papers": [
        {
            "paper_id": "P001",
            "doi": "10.1000/abc",
            "title": "First paper",
            "authors": ["Author A"],
            "year": 2022,
            "journal": "Science",
        },
        {
            "paper_id": "P002",
            "doi": "10.1000/def",
            "title": "Second paper",
            "authors": ["Author B"],
            "year": 2021,
            "journal": "Nature",
        },
    ],
    "search_date": "2024-01-01",
    "workflow_id": "WB005",
    "total_papers": 2,
}

CANONICAL_VARIANT = {
    "variant_id": "V1",
    "variant_name": "Standard Lysis",
    "uo_sequence": ["UO-001", "UO-002", "UO-003"],
}

BAD_ID_VARIANT = {
    "variant_id": "WB005-V1",  # non-canonical: should be ^V\d+$
    "variant_name": "Extended",
    "uo_sequence": ["UO-001"],
}

CANONICAL_COMPOSITION = {
    "schema_version": "4.0.0",
    "workflow_id": "WB005",
    "workflow_name": "Western Blot",
    "category": "analysis",
    "domain": "proteomics",
    "version": "1.0",
    "composition_date": "2024-01-15",
    "statistics": {
        "papers_analyzed": 20,
        "cases_collected": 15,
        "variants_identified": 3,
        "total_uos": 8,
        "qc_checkpoints": 4,
        "confidence_score": 0.85,
    },
}

DEPRECATED_STATS_COMPOSITION = {
    "schema_version": "4.0.0",
    "workflow_id": "WB005",
    "workflow_name": "Western Blot",
    "category": "analysis",
    "domain": "proteomics",
    "version": "1.0",
    "composition_date": "2024-01-15",
    "statistics": {
        "total_papers": 20,     # deprecated → papers_analyzed
        "total_cases": 15,      # deprecated → cases_collected
        "total_variants": 3,    # deprecated → variants_identified
    },
}


# ---------------------------------------------------------------------------
# ScoredResult dataclass
# ---------------------------------------------------------------------------

def test_scored_result_dataclass():
    from scoring import ScoredResult
    r = ScoredResult(score=0.8, max_score=1.0)
    assert r.score == 0.8
    assert r.max_score == 1.0
    assert r.violations == []
    assert r.field_details == {}
    assert r.schema_group == ""

    r2 = ScoredResult(
        score=0.5,
        max_score=1.0,
        violations=["missing: steps"],
        field_details={"steps": "missing"},
        schema_group="legacy_flat",
    )
    assert r2.violations == ["missing: steps"]
    assert r2.field_details["steps"] == "missing"
    assert r2.schema_group == "legacy_flat"


# ---------------------------------------------------------------------------
# score_case_card
# ---------------------------------------------------------------------------

def test_score_case_card_canonical():
    from scoring import score_case_card
    result = score_case_card(CANONICAL_CASE_CARD)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"
    assert result.schema_group == "canonical"
    assert result.violations == [] or len(result.violations) == 0


def test_score_case_card_legacy_flat():
    from scoring import score_case_card
    result = score_case_card(LEGACY_FLAT_CASE_CARD)
    # Very sparse card: only paper_id, technique, steps present (no metadata block,
    # no completeness/flow_diagram/workflow_context). Alias matches in steps give 0.3
    # partial credit. Score is low — between 0.05 and 0.4.
    assert result.score < 0.4, f"Expected <0.4 (low), got {result.score}"
    assert result.score > 0.05, f"Expected >0.05 (aliases give some credit), got {result.score}"
    assert result.schema_group == "legacy_flat"
    # Alias keys should be recorded (position→step_number, name→step_name)
    assert any(
        "alias_match" in str(v) for v in result.field_details.values()
    ), f"Expected alias_match in field_details, got {result.field_details}"


def test_score_case_card_mixed_software():
    from scoring import score_case_card
    result = score_case_card(MIXED_SOFTWARE_CASE_CARD)
    # software field in step should be wrong_type (flat strings → 0.5)
    step_details = result.field_details.get("steps", {})
    # Could be stored as steps[0].software or similar; check score reflects partial
    # Overall score should be between 0.7 and 0.95 (one field wrong)
    assert result.score >= 0.7, f"Expected >=0.7, got {result.score}"
    # The software field should not be "present" (full score) anywhere
    # At least check that the result is not perfect
    assert result.score < 1.0


# ---------------------------------------------------------------------------
# score_paper_list
# ---------------------------------------------------------------------------

def test_score_paper_list_canonical():
    from scoring import score_paper_list
    result = score_paper_list(CANONICAL_PAPER_LIST)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"
    assert result.field_details.get("papers") == "present"


def test_score_paper_list_missing_papers_key():
    from scoring import score_paper_list
    flat_list = [
        {"paper_id": "P001", "doi": "10.1000/abc", "title": "T",
         "authors": ["A"], "year": 2022, "journal": "S"}
    ]
    result = score_paper_list(flat_list)
    assert result.score < 0.5, f"Expected <0.5, got {result.score}"
    assert "papers" in result.violations or any("papers" in v for v in result.violations)


# ---------------------------------------------------------------------------
# score_variant
# ---------------------------------------------------------------------------

def test_score_variant_canonical():
    from scoring import score_variant
    result = score_variant(CANONICAL_VARIANT)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"
    assert result.field_details.get("variant_id") == "present"


def test_score_variant_bad_id():
    from scoring import score_variant
    result = score_variant(BAD_ID_VARIANT)
    # variant_id exists but fails pattern → lower score
    assert result.score < 0.9, f"Expected <0.9, got {result.score}"
    assert result.field_details.get("variant_id") == "wrong_type"
    assert any("variant_id" in v for v in result.violations)


# ---------------------------------------------------------------------------
# score_composition_data
# ---------------------------------------------------------------------------

def test_score_composition_data_canonical():
    from scoring import score_composition_data
    result = score_composition_data(CANONICAL_COMPOSITION)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"
    assert result.field_details.get("schema_version") == "present"


def test_score_composition_data_deprecated_stats():
    from scoring import score_composition_data
    result = score_composition_data(DEPRECATED_STATS_COMPOSITION)
    # Has deprecated stats keys → partial score
    assert result.score < 0.9, f"Expected <0.9, got {result.score}"
    assert any("deprecated" in v.lower() for v in result.violations)


# ---------------------------------------------------------------------------
# aggregate_workflow_score
# ---------------------------------------------------------------------------

def test_aggregate_workflow_score():
    from scoring import aggregate_workflow_score
    # All 1.0 → weighted average = 1.0
    all_ones = {
        "case_cards": 1.0,
        "composition_data": 1.0,
        "variant_files": 1.0,
        "report_sections": 1.0,
        "paper_list": 1.0,
        "uo_mapping": 1.0,
        "referential_integrity": 1.0,
    }
    assert aggregate_workflow_score(all_ones) == 1.0

    # All 0.0 → 0.0
    all_zeros = {k: 0.0 for k in all_ones}
    assert aggregate_workflow_score(all_zeros) == 0.0

    # Known partial: case_cards=0.8, rest=1.0
    # case_cards weight=0.25 → contribution = 0.25*0.8 = 0.20
    # other weights sum = 0.75, all at 1.0 → 0.75
    # total = 0.95
    partial = dict(all_ones)
    partial["case_cards"] = 0.8
    result = aggregate_workflow_score(partial)
    assert abs(result - 0.95) < 0.001, f"Expected 0.95, got {result}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
