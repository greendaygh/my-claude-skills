"""Tests for audit_workflow.py — written TDD-first."""

import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_workflow import (
    detect_schema_era,
    load_existing_validation,
    get_migration_priority,
    audit_single_workflow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_canonical_workflow(base):
    """Create a canonical (v2) workflow directory."""
    wf = base / "WB005_Test"
    _write_json(wf / "composition_data.json", {
        "schema_version": "4.0.0", "workflow_id": "WB005",
        "workflow_name": "Test", "category": "Build", "domain": "Test",
        "version": 1.0, "composition_date": "2026-01-01",
        "statistics": {"papers_analyzed": 1, "cases_collected": 1,
                       "variants_identified": 1, "total_uos": 1,
                       "qc_checkpoints": 1, "confidence_score": 0.9}
    })
    _write_json(wf / "02_cases" / "case_C001.json", {
        "case_id": "WB005-C001", "metadata": {
            "pmid": "123", "doi": "10.1/x", "authors": "A", "year": 2020,
            "journal": "J", "title": "T", "purpose": "P", "organism": "E.coli",
            "scale": "bench", "automation_level": "manual", "core_technique": "PCR",
            "fulltext_access": True, "access_method": "pmc", "access_tier": 1
        },
        "steps": [{"step_number": 1, "step_name": "S1", "description": "D",
                    "equipment": [{"name": "E", "model": "M", "manufacturer": "X"}],
                    "software": [], "reagents": "R", "conditions": "C",
                    "result_qc": "Q", "notes": "N"}],
        "completeness": {"score": 0.9}, "flow_diagram": "A->B",
        "workflow_context": {"id": "WB005"}
    })
    _write_json(wf / "04_workflow" / "variant_V1_Test.json", {
        "variant_id": "V1", "variant_name": "Test", "uo_sequence": [
            {"uo_id": "UHW010", "uo_name": "Test"}
        ], "supporting_cases": ["C001"]
    })
    _write_json(wf / "01_papers" / "paper_list.json", {
        "papers": [{"paper_id": "P001", "doi": "10.1/x", "pmid": "123",
                     "title": "T", "authors": "A", "year": 2020, "journal": "J"}]
    })
    (wf / "composition_report.md").write_text(
        "# 1. Intro\n# 2. Scope\n# 3. Methods\n# 4. Results\n# 5. Cases\n"
        "# 6. Variants\n# 7. UO\n# 8. Components\n# 9. Evidence\n# 10. Modularity\n"
        "# 11. Limitations\n# 12. Feedback\n# 13. Metrics\n"
    )
    return wf


def _make_legacy_workflow(base):
    """Create a legacy (v1) workflow directory."""
    wf = base / "WB140_Test"
    _write_json(wf / "composition_data.json", {
        "schema_version": "4.0.0", "workflow_id": "WB140",
        "workflow_name": "Legacy", "category": "Build", "domain": "Test",
        "version": 1.0, "composition_date": "2026-01-01",
        "statistics": {"papers_analyzed": 1, "cases_collected": 1,
                       "variants_identified": 0, "total_uos": 1,
                       "qc_checkpoints": 1, "confidence_score": 0.8}
    })
    _write_json(wf / "02_cases" / "case_C001.json", {
        "case_id": "WB140-C001", "paper_id": "P001", "title": "T",
        "technique": "Culture", "organism": "E.coli", "scale": "bench",
        "steps": [{"position": 1, "name": "S1", "description": "D",
                    "equipment": ["Autoclave"], "parameters": {"temp": "37C"},
                    "evidence_tag": "literature-direct"}]
    })
    return wf


# ---------------------------------------------------------------------------
# Tests: detect_schema_era
# ---------------------------------------------------------------------------

def test_detect_schema_era_canonical(tmp_path):
    wf = _make_canonical_workflow(tmp_path)
    result = detect_schema_era(wf)
    assert result["era"] == "v2_canonical"


def test_detect_schema_era_legacy(tmp_path):
    wf = _make_legacy_workflow(tmp_path)
    result = detect_schema_era(wf)
    assert result["era"] == "v1_legacy_flat"


def test_detect_schema_era_wt_extended(tmp_path):
    wf = tmp_path / "WB999_Test"
    _write_json(wf / "composition_data.json", {
        "schema_version": "4.0.0", "workflow_id": "WB999",
        "workflow_name": "WT", "category": "Build", "domain": "Test",
        "version": 1.0, "composition_date": "2026-01-01",
        "statistics": {}
    })
    _write_json(wf / "02_cases" / "case_C001.json", {
        "case_id": "WB999-C001",
        "variant_hint": "aerobic",
        "steps": [{"position": 1, "name": "S1", "description": "D"}]
    })
    result = detect_schema_era(wf)
    assert result["era"] == "v1_wt_extended"


# ---------------------------------------------------------------------------
# Tests: load_existing_validation
# ---------------------------------------------------------------------------

def test_load_existing_validation_workflow_composer(tmp_path):
    wf = tmp_path / "WB005_Test"
    val_data = {"violations_by_category": {"schema": [], "integrity": []}}
    _write_json(wf / "00_metadata" / "validation_report.json", val_data)
    result = load_existing_validation(wf)
    assert result is not None
    assert result["format"] == "workflow-composer"
    assert result["source"] == "validation_report.json"
    assert "violations_by_category" in result["data"]


def test_load_existing_validation_wf_output(tmp_path):
    wf = tmp_path / "WB005_Test"
    val_data = {"checks": [{"check_id": "CHK01", "result": "PASS"}]}
    _write_json(wf / "00_metadata" / "validation_report.json", val_data)
    result = load_existing_validation(wf)
    assert result is not None
    assert result["format"] == "wf-output"
    assert result["source"] == "validation_report.json"
    assert "checks" in result["data"]


def test_load_existing_validation_missing(tmp_path):
    wf = tmp_path / "WB005_Test"
    wf.mkdir(parents=True, exist_ok=True)
    result = load_existing_validation(wf)
    assert result is None


# ---------------------------------------------------------------------------
# Tests: get_migration_priority
# ---------------------------------------------------------------------------

def test_migration_priority_thresholds():
    assert get_migration_priority(0.95) == "none"
    assert get_migration_priority(0.9) == "none"
    assert get_migration_priority(0.85) == "low"
    assert get_migration_priority(0.7) == "low"
    assert get_migration_priority(0.65) == "medium"
    assert get_migration_priority(0.5) == "medium"
    assert get_migration_priority(0.4) == "high"
    assert get_migration_priority(0.3) == "high"
    assert get_migration_priority(0.29) == "critical"
    assert get_migration_priority(0.0) == "critical"


# ---------------------------------------------------------------------------
# Tests: audit_single_workflow
# ---------------------------------------------------------------------------

def test_audit_single_workflow_canonical(tmp_path):
    wf = _make_canonical_workflow(tmp_path)
    result = audit_single_workflow(wf)
    assert "conformance_score" in result
    assert "migration_priority" in result
    assert "schema_era" in result
    assert "scores" in result
    assert result["conformance_score"] >= 0.7
    assert result["migration_priority"] in ("none", "low")
    assert result["schema_era"] == "v2_canonical"


def test_audit_single_workflow_legacy(tmp_path):
    wf = _make_legacy_workflow(tmp_path)
    result = audit_single_workflow(wf)
    assert "conformance_score" in result
    assert result["conformance_score"] < 0.5
    assert result["migration_priority"] in ("high", "critical")
    assert result["schema_era"] == "v1_legacy_flat"
