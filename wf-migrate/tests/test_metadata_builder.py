import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from metadata_builder import (
    build_paper_index,
    build_metadata,
    build_completeness_stub,
    build_flow_diagram,
    build_workflow_context,
)


# ---------------------------------------------------------------------------
# Paper index building
# ---------------------------------------------------------------------------

def test_build_paper_index():
    paper_data = {
        "papers": [
            {"paper_id": "P001", "pmid": "123", "doi": "10.1/x", "title": "T",
             "authors": "A et al.", "year": 2021, "journal": "J"},
            {"paper_id": "P002", "pmid": "456", "doi": "10.2/y", "title": "T2",
             "authors": "B et al.", "year": 2022, "journal": "J2"},
        ]
    }
    result = build_paper_index(paper_data)
    assert result["P001"]["pmid"] == "123"
    assert result["P001"]["doi"] == "10.1/x"
    assert result["P001"]["title"] == "T"
    assert result["P001"]["authors"] == "A et al."
    assert result["P001"]["year"] == 2021
    assert result["P001"]["journal"] == "J"
    assert result["P002"]["pmid"] == "456"
    assert result["P002"]["doi"] == "10.2/y"


def test_build_paper_index_flat_list():
    paper_data = [
        {"paper_id": "P001", "pmid": "123", "doi": "10.1/x", "title": "T",
         "authors": "A et al.", "year": 2021, "journal": "J"},
    ]
    result = build_paper_index(paper_data)
    assert result["P001"]["pmid"] == "123"
    assert result["P001"]["doi"] == "10.1/x"


def test_build_paper_index_empty():
    assert build_paper_index({"papers": []}) == {}
    assert build_paper_index({}) == {}


# ---------------------------------------------------------------------------
# Metadata construction
# ---------------------------------------------------------------------------

PAPER_INDEX = {
    "P001": {
        "pmid": "123",
        "doi": "10.1/x",
        "authors": "A",
        "year": 2021,
        "journal": "J",
        "title": "Paper title",
    }
}


def test_build_metadata_full_match():
    case_data = {
        "paper_id": "P001",
        "organism": "E. coli",
        "scale": "bench",
        "technique": "Overnight Culture",
        "title": "Standard overnight culture",
    }
    meta = build_metadata(case_data, PAPER_INDEX)
    # All 14 required fields present
    required_fields = [
        "pmid", "doi", "authors", "year", "journal", "title",
        "purpose", "organism", "scale", "core_technique",
        "automation_level", "fulltext_access", "access_method", "access_tier",
    ]
    for field in required_fields:
        assert field in meta, f"Missing field: {field}"
    # Paper fields from index
    assert meta["pmid"] == "123"
    assert meta["doi"] == "10.1/x"
    assert meta["authors"] == "A"
    assert meta["year"] == 2021
    assert meta["journal"] == "J"
    assert meta["title"] == "Paper title"
    # Case fields mapped
    assert meta["purpose"] == "Standard overnight culture"
    assert meta["organism"] == "E. coli"
    assert meta["scale"] == "bench"
    assert meta["core_technique"] == "Overnight Culture"


def test_build_metadata_no_paper_match():
    case_data = {
        "paper_id": "P099",
        "organism": "Human",
        "scale": "micro",
        "technique": "PCR",
        "title": "PCR amplification",
    }
    meta = build_metadata(case_data, PAPER_INDEX)
    # Paper fields empty/None
    assert meta["pmid"] in ("", None)
    assert meta["doi"] in ("", None)
    assert meta["authors"] in ("", None)
    assert meta["year"] in ("", None, 0)
    assert meta["journal"] in ("", None)
    # Case fields still populated
    assert meta["organism"] == "Human"
    assert meta["scale"] == "micro"
    assert meta["core_technique"] == "PCR"
    assert meta["purpose"] == "PCR amplification"


def test_build_metadata_no_paper_id():
    case_data = {
        "organism": "Mouse",
        "scale": "nano",
        "technique": "Western Blot",
        "title": "Protein detection",
    }
    meta = build_metadata(case_data, PAPER_INDEX)
    # All paper fields empty/None
    assert meta["pmid"] in ("", None)
    assert meta["doi"] in ("", None)
    # Case fields used
    assert meta["organism"] == "Mouse"
    assert meta["core_technique"] == "Western Blot"
    assert meta["purpose"] == "Protein detection"


def test_build_metadata_defaults():
    case_data = {"paper_id": "P001", "title": "Test"}
    meta = build_metadata(case_data, PAPER_INDEX)
    assert meta["automation_level"] == "manual"
    assert meta["fulltext_access"] == False
    assert meta["access_method"] == "unknown"
    assert meta["access_tier"] == 3


def test_build_metadata_wt_extended():
    case_data = {
        "paper_id": "P001",
        "sample_type": "plasma",
        "technique": "Protein precipitation",
        "title": "Plasma protein removal",
    }
    meta = build_metadata(case_data, PAPER_INDEX)
    # technique maps to core_technique even with extra fields
    assert meta["core_technique"] == "Protein precipitation"
    # sample_type is not a canonical field — should not raise
    assert meta["title"] == "Paper title"
    assert meta["purpose"] == "Plasma protein removal"


# ---------------------------------------------------------------------------
# Top-level field extraction
# ---------------------------------------------------------------------------

def test_extract_canonical_top_fields():
    """Legacy case with mixed fields: canonical ones mapped, extras don't break anything."""
    case_data = {
        "case_id": "WB140-001",
        "paper_id": "P001",
        "title": "Standard culture",
        "technique": "Overnight Culture",
        "organism": "E. coli",
        "scale": "bench",
        "steps": [{"step_name": "Inoculate"}],
        "notes": "some notes",
        "qc_checkpoints": ["check pH"],
    }
    meta = build_metadata(case_data, PAPER_INDEX)
    # Canonical mappings work
    assert meta["core_technique"] == "Overnight Culture"
    assert meta["organism"] == "E. coli"
    assert meta["scale"] == "bench"
    # case_id and steps are not in metadata (they live at top level of case card)
    assert "case_id" not in meta
    assert "steps" not in meta


# ---------------------------------------------------------------------------
# Completeness stub
# ---------------------------------------------------------------------------

def test_build_completeness_stub():
    result = build_completeness_stub()
    assert result["score"] == 0.0
    assert "Auto-generated during migration" in result["notes"]
    assert "manual review" in result["notes"]


# ---------------------------------------------------------------------------
# Flow diagram
# ---------------------------------------------------------------------------

def test_build_flow_diagram_from_steps():
    steps = [{"step_name": "A"}, {"step_name": "B"}, {"step_name": "C"}]
    result = build_flow_diagram(steps)
    assert result == "A -> B -> C"


def test_build_flow_diagram_empty_steps():
    assert build_flow_diagram([]) == ""


# ---------------------------------------------------------------------------
# Workflow context stub
# ---------------------------------------------------------------------------

def test_build_workflow_context_stub():
    result = build_workflow_context("WB140")
    assert result["workflow_id"] == "WB140"
    assert result["migration_source"] == "wf-migrate v1.0.0"
