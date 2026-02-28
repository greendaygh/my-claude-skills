"""Tests for scoring.py — Pydantic-based conformance scoring engine."""

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
        "authors": "Smith J, Doe A",
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
        "access_tier": 1,
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
    "completeness": {"score": 0.95},
    "flow_diagram": "graph LR\n  A --> B",
    "workflow_context": {"workflow_id": "WB005"},
}

LEGACY_FLAT_CASE_CARD = {
    "paper_id": "paper_001",
    "technique": "western blot",
    "steps": [
        {
            "position": 1,
            "name": "Gel run",
            "equipment": ["Autoclave", "Centrifuge"],
        }
    ],
}

CANONICAL_PAPER_LIST = {
    "papers": [
        {
            "paper_id": "P001",
            "doi": "10.1000/abc",
            "title": "First paper",
            "authors": "Author A",
            "year": 2022,
            "journal": "Science",
        },
        {
            "paper_id": "P002",
            "doi": "10.1000/def",
            "title": "Second paper",
            "authors": "Author B",
            "year": 2021,
            "journal": "Nature",
        },
    ],
    "search_date": "2024-01-01",
    "workflow_id": "WB005",
    "total_papers": 2,
}

MINIMAL_UO = {
    "uo_id": "UHW400",
    "uo_name": "Sample Prep",
    "step_position": 1,
    "input": {"items": []},
    "output": {"items": []},
    "equipment": {"items": []},
    "consumables": {"items": []},
    "material_and_method": {},
    "result": {},
    "discussion": {},
}

CANONICAL_VARIANT = {
    "variant_id": "V1",
    "variant_name": "Standard Lysis",
    "workflow_id": "WB005",
    "unit_operations": [MINIMAL_UO],
}

BAD_ID_VARIANT = {
    "variant_id": "WB005-V1",
    "variant_name": "Extended",
    "workflow_id": "WB005",
    "unit_operations": [MINIMAL_UO],
}

CANONICAL_COMPOSITION = {
    "schema_version": "4.0.0",
    "workflow_id": "WB005",
    "workflow_name": "Western Blot",
    "category": "analysis",
    "domain": "proteomics",
    "version": 1.0,
    "composition_date": "2024-01-15",
    "description": "Analysis workflow",
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
    "version": 1.0,
    "composition_date": "2024-01-15",
    "description": "Analysis workflow",
    "statistics": {
        "total_papers": 20,
        "total_cases": 15,
        "total_variants": 3,
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
    assert r.detailed_violations == []
    assert r.field_details == {}
    assert r.schema_group == ""


# ---------------------------------------------------------------------------
# score_case_card
# ---------------------------------------------------------------------------

def test_score_case_card_canonical():
    from scoring import score_case_card
    result = score_case_card(CANONICAL_CASE_CARD)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"
    assert result.schema_group == "canonical"


def test_score_case_card_legacy_flat():
    from scoring import score_case_card
    result = score_case_card(LEGACY_FLAT_CASE_CARD)
    assert result.score <= 0.5, f"Expected <=0.5 (low), got {result.score}"
    assert result.schema_group == "legacy_flat"
    assert len(result.violations) > 0
    assert len(result.detailed_violations) > 0


def test_score_case_card_detailed_violations_have_structure():
    from scoring import score_case_card
    result = score_case_card(LEGACY_FLAT_CASE_CARD, source_file="02_cases/case_C001.json")
    for dv in result.detailed_violations:
        assert "file" in dv
        assert "record" in dv
        assert "path" in dv
        assert "error" in dv
        assert "error_type" in dv
        assert "fix_hint" in dv
        assert dv["file"] == "02_cases/case_C001.json"


# ---------------------------------------------------------------------------
# score_paper_list
# ---------------------------------------------------------------------------

def test_score_paper_list_canonical():
    from scoring import score_paper_list
    result = score_paper_list(CANONICAL_PAPER_LIST)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"


def test_score_paper_list_missing_papers_key():
    from scoring import score_paper_list
    flat_list = [
        {"paper_id": "P001", "doi": "10.1000/abc", "title": "T",
         "authors": "A", "year": 2022, "journal": "S"}
    ]
    result = score_paper_list(flat_list)
    assert result.score == 0.0


def test_score_paper_list_missing_doi():
    from scoring import score_paper_list
    data = {
        "workflow_id": "WB005",
        "total_papers": 1,
        "papers": [
            {"paper_id": "P001", "title": "T", "authors": "A", "year": 2022, "journal": "S"}
        ],
    }
    result = score_paper_list(data)
    assert result.score < 1.0
    assert any("doi" in v for v in result.violations)
    assert len(result.detailed_violations) > 0
    doi_violation = [d for d in result.detailed_violations if "doi" in d["path"]]
    assert len(doi_violation) > 0


def test_score_paper_list_full_text_detected():
    from scoring import score_paper_list
    data = {
        "workflow_id": "WB005",
        "total_papers": 2,
        "papers": [
            {"paper_id": "P001", "doi": "10.1000/abc", "title": "T",
             "authors": "A", "year": 2022, "journal": "S",
             "full_text": "This is the entire text of the paper..." * 100},
            {"paper_id": "P002", "doi": "10.1000/def", "title": "T2",
             "authors": "B", "year": 2023, "journal": "N"},
        ],
    }
    result = score_paper_list(data, source_file="paper_list.json")
    assert result.score < 1.0
    cq_violations = [d for d in result.detailed_violations if d["error_type"] == "content_quality"]
    assert len(cq_violations) == 1
    assert "full_text" in cq_violations[0]["path"]
    assert cq_violations[0]["file"] == "paper_list.json"
    assert cq_violations[0]["record"] == "P001"


def test_score_paper_list_duplicate_doi():
    from scoring import score_paper_list
    data = {
        "workflow_id": "WB005",
        "total_papers": 3,
        "papers": [
            {"paper_id": "P001", "doi": "10.1000/abc", "title": "T",
             "authors": "A", "year": 2022, "journal": "S"},
            {"paper_id": "P002", "doi": "10.1000/abc", "title": "T2",
             "authors": "B", "year": 2023, "journal": "N"},
            {"paper_id": "P003", "doi": "10.1000/def", "title": "T3",
             "authors": "C", "year": 2024, "journal": "X"},
        ],
    }
    result = score_paper_list(data, source_file="paper_list.json")
    assert result.score < 1.0
    dup_violations = [d for d in result.detailed_violations if d["error_type"] == "duplicate"]
    assert len(dup_violations) == 1
    assert "Duplicate DOI" in dup_violations[0]["error"]
    assert "P001" in dup_violations[0]["record"] or "P002" in dup_violations[0]["record"]


def test_score_paper_list_full_text_and_dup_combined():
    from scoring import score_paper_list
    data = {
        "workflow_id": "WB005",
        "total_papers": 2,
        "papers": [
            {"paper_id": "P001", "doi": "10.1000/same", "title": "T",
             "authors": "A", "year": 2022, "journal": "S",
             "full_text": "Long text here..."},
            {"paper_id": "P002", "doi": "10.1000/same", "title": "T2",
             "authors": "B", "year": 2023, "journal": "N"},
        ],
    }
    result = score_paper_list(data, source_file="paper_list.json")
    assert result.score < 1.0
    cq = [d for d in result.detailed_violations if d["error_type"] == "content_quality"]
    dup = [d for d in result.detailed_violations if d["error_type"] == "duplicate"]
    assert len(cq) == 1
    assert len(dup) == 1


def test_score_paper_list_no_content_issues():
    """Clean paper_list should get perfect score."""
    from scoring import score_paper_list
    data = {
        "workflow_id": "WB005",
        "total_papers": 2,
        "papers": [
            {"paper_id": "P001", "doi": "10.1000/abc", "title": "T",
             "authors": "A", "year": 2022, "journal": "S"},
            {"paper_id": "P002", "doi": "10.1000/def", "title": "T2",
             "authors": "B", "year": 2023, "journal": "N"},
        ],
    }
    result = score_paper_list(data, source_file="paper_list.json")
    assert result.score == 1.0
    assert len(result.detailed_violations) == 0


# ---------------------------------------------------------------------------
# score_variant
# ---------------------------------------------------------------------------

def test_score_variant_canonical():
    from scoring import score_variant
    result = score_variant(CANONICAL_VARIANT)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"


def test_score_variant_missing_unit_operations():
    from scoring import score_variant
    data = {"variant_id": "V1", "variant_name": "Test", "workflow_id": "WB005"}
    result = score_variant(data)
    assert result.score < 0.9
    assert any("unit_operations" in v for v in result.violations)


# ---------------------------------------------------------------------------
# score_composition_data
# ---------------------------------------------------------------------------

def test_score_composition_data_canonical():
    from scoring import score_composition_data
    result = score_composition_data(CANONICAL_COMPOSITION)
    assert result.score >= 0.9, f"Expected >=0.9, got {result.score}"


def test_score_composition_data_missing_fields():
    from scoring import score_composition_data
    result = score_composition_data({"workflow_id": "WB005"})
    assert result.score < 0.5
    assert len(result.detailed_violations) > 0


def test_score_composition_data_deprecated_stats():
    from scoring import score_composition_data
    result = score_composition_data(DEPRECATED_STATS_COMPOSITION)
    # Has deprecated stats keys that don't match canonical model field names
    assert result.score < 1.0


# ---------------------------------------------------------------------------
# New file type scoring functions
# ---------------------------------------------------------------------------

def test_score_case_summary():
    from scoring import score_case_summary
    data = {
        "workflow_id": "WB005",
        "total_cases": 2,
        "cases": [
            {"case_id": "WB005-C001"},
            {"case_id": "WB005-C002"},
        ],
    }
    result = score_case_summary(data)
    assert result.score >= 0.9


def test_score_cluster_result():
    from scoring import score_cluster_result
    data = {
        "workflow_id": "WB005",
        "total_cases": 5,
        "variants": [
            {"variant_id": "V1", "name": "Standard"},
        ],
    }
    result = score_cluster_result(data)
    assert result.score >= 0.9


def test_score_uo_mapping():
    from scoring import score_uo_mapping
    data = {
        "workflow_id": "WB005",
        "uo_assignments": [
            {"step_position": 1, "primary_uo": "UHW400"},
        ],
    }
    result = score_uo_mapping(data)
    assert result.score >= 0.9


def test_score_workflow_context():
    from scoring import score_workflow_context
    data = {
        "workflow_id": "WB005",
        "workflow_name": "Test Workflow",
    }
    result = score_workflow_context(data)
    assert result.score >= 0.9


# ---------------------------------------------------------------------------
# aggregate_workflow_score
# ---------------------------------------------------------------------------

def test_aggregate_workflow_score():
    from scoring import aggregate_workflow_score
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

    all_zeros = {k: 0.0 for k in all_ones}
    assert aggregate_workflow_score(all_zeros) == 0.0

    partial = dict(all_ones)
    partial["case_cards"] = 0.8
    result = aggregate_workflow_score(partial)
    assert abs(result - 0.95) < 0.001, f"Expected 0.95, got {result}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
