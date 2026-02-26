import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from referential_integrity import (
    check_case_variant_refs,
    check_uo_catalog_refs,
    check_paper_case_refs,
    check_statistics_consistency,
    check_case_id_format,
    run_all,
)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


# ---------------------------------------------------------------------------
# check_case_variant_refs
# ---------------------------------------------------------------------------

def test_check_case_variant_refs_valid(tmp_path):
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001", "title": "Test case"},
    )
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {"variant_id": "V1", "supporting_cases": ["C001"]},
    )
    violations = check_case_variant_refs(tmp_path)
    assert violations == []


def test_check_case_variant_refs_missing(tmp_path):
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001"},
    )
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {"variant_id": "V1", "supporting_cases": ["C099"]},
    )
    violations = check_case_variant_refs(tmp_path)
    assert len(violations) == 1
    assert "C099" in violations[0]


def test_check_case_variant_refs_case_ids_key(tmp_path):
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001"},
    )
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {"variant_id": "V1", "case_ids": ["C001"]},
    )
    violations = check_case_variant_refs(tmp_path)
    assert violations == []


# ---------------------------------------------------------------------------
# check_uo_catalog_refs
# ---------------------------------------------------------------------------

def test_check_uo_catalog_refs_valid(tmp_path):
    catalog = {"UHW400a": {"uo_id": "UHW400a", "uo_name": "Test UO"}}
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {"variant_id": "V1", "uo_sequence": [{"uo_id": "UHW400a", "step": 1}]},
    )
    violations = check_uo_catalog_refs(tmp_path, catalog)
    assert violations == []


def test_check_uo_catalog_refs_missing(tmp_path):
    catalog = {"UHW400a": {"uo_id": "UHW400a", "uo_name": "Test UO"}}
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {"variant_id": "V1", "uo_sequence": [{"uo_id": "FAKE001", "step": 1}]},
    )
    violations = check_uo_catalog_refs(tmp_path, catalog)
    assert len(violations) == 1
    assert "FAKE001" in violations[0]


# ---------------------------------------------------------------------------
# check_paper_case_refs
# ---------------------------------------------------------------------------

def test_check_paper_case_refs_valid(tmp_path):
    _write_json(
        tmp_path / "01_literature" / "paper_list.json",
        {"papers": [{"pmid": "12345", "title": "Paper A"}]},
    )
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001", "pmid": "12345"},
    )
    violations = check_paper_case_refs(tmp_path)
    assert violations == []


def test_check_paper_case_refs_missing(tmp_path):
    _write_json(
        tmp_path / "01_literature" / "paper_list.json",
        {"papers": [{"pmid": "12345", "title": "Paper A"}]},
    )
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001", "pmid": "99999"},
    )
    violations = check_paper_case_refs(tmp_path)
    assert len(violations) == 1
    assert "99999" in violations[0]


# ---------------------------------------------------------------------------
# check_statistics_consistency
# ---------------------------------------------------------------------------

def test_check_statistics_consistency_valid(tmp_path):
    _write_json(tmp_path / "02_cases" / "case_C001.json", {"case_id": "WB005-C001"})
    _write_json(tmp_path / "02_cases" / "case_C002.json", {"case_id": "WB005-C002"})
    _write_json(
        tmp_path / "composition_data.json",
        {"statistics": {"cases_collected": 2, "variants_identified": 0}},
    )
    violations = check_statistics_consistency(tmp_path)
    assert violations == []


def test_check_statistics_consistency_mismatch(tmp_path):
    _write_json(tmp_path / "02_cases" / "case_C001.json", {"case_id": "WB005-C001"})
    _write_json(tmp_path / "02_cases" / "case_C002.json", {"case_id": "WB005-C002"})
    _write_json(
        tmp_path / "composition_data.json",
        {"statistics": {"cases_collected": 5, "variants_identified": 0}},
    )
    violations = check_statistics_consistency(tmp_path)
    assert len(violations) >= 1
    assert any("cases_collected" in v or "case" in v.lower() for v in violations)


# ---------------------------------------------------------------------------
# check_case_id_format
# ---------------------------------------------------------------------------

def test_check_case_id_format_valid(tmp_path):
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001"},
    )
    violations = check_case_id_format(tmp_path)
    assert violations == []


def test_check_case_id_format_invalid(tmp_path):
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "C001"},
    )
    violations = check_case_id_format(tmp_path)
    assert len(violations) == 1
    assert "C001" in violations[0]


# ---------------------------------------------------------------------------
# run_all
# ---------------------------------------------------------------------------

def test_run_all(tmp_path):
    # Build a complete minimal workflow dir
    _write_json(
        tmp_path / "01_literature" / "paper_list.json",
        {"papers": [{"pmid": "11111"}]},
    )
    _write_json(
        tmp_path / "02_cases" / "case_C001.json",
        {"case_id": "WB005-C001", "pmid": "11111"},
    )
    _write_json(
        tmp_path / "04_workflow" / "variant_V1.json",
        {
            "variant_id": "V1",
            "supporting_cases": ["C001"],
            "uo_sequence": [],
        },
    )
    _write_json(
        tmp_path / "composition_data.json",
        {"statistics": {"cases_collected": 1, "variants_identified": 1}},
    )

    catalog = {}
    result = run_all(tmp_path, catalog=catalog)

    assert isinstance(result, dict)
    expected_keys = {
        "case_variant_refs",
        "uo_catalog_refs",
        "paper_case_refs",
        "statistics_consistency",
        "case_id_format",
    }
    assert expected_keys == set(result.keys())
    # All checks should be clean for this valid fixture
    for key, violations in result.items():
        assert violations == [], f"{key}: unexpected violations {violations}"
