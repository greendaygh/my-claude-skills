import sys
import json
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_batch import (
    discover_workflows,
    audit_all_workflows,
    detect_cross_workflow_drift,
    generate_batch_summary,
    main,
)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_workflow(base, wf_id, name, era="canonical"):
    """Create a minimal workflow dir for batch testing."""
    wf = base / f"{wf_id}_{name}"
    stats = {
        "papers_analyzed": 1,
        "cases_collected": 1,
        "variants_identified": 1,
        "total_uos": 1,
        "qc_checkpoints": 1,
        "confidence_score": 0.9,
    }
    if era == "legacy":
        stats = {
            "total_papers": 1,
            "total_cases": 1,
            "total_variants": 1,
            "total_uo_types": 1,
            "qc_checkpoints": 1,
            "confidence_score": 0.7,
        }
    _write_json(
        wf / "composition_data.json",
        {
            "schema_version": "4.0.0",
            "workflow_id": wf_id,
            "workflow_name": name,
            "category": "Build",
            "domain": "Test",
            "version": 1.0,
            "composition_date": "2026-01-01",
            "statistics": stats,
        },
    )
    if era == "canonical":
        _write_json(
            wf / "02_cases" / "case_C001.json",
            {
                "case_id": f"{wf_id}-C001",
                "metadata": {
                    "pmid": "123",
                    "doi": "10.1/x",
                    "authors": "A",
                    "year": 2020,
                    "journal": "J",
                    "title": "T",
                    "purpose": "P",
                    "organism": "O",
                    "scale": "bench",
                    "automation_level": "manual",
                    "core_technique": "T",
                    "fulltext_access": True,
                    "access_method": "pmc",
                    "access_tier": 1,
                },
                "steps": [
                    {
                        "step_number": 1,
                        "step_name": "S",
                        "description": "D",
                        "equipment": [{"name": "E", "model": "M", "manufacturer": "X"}],
                        "software": [],
                        "reagents": "R",
                        "conditions": "C",
                        "result_qc": "Q",
                        "notes": "N",
                    }
                ],
                "completeness": {},
                "flow_diagram": "A->B",
                "workflow_context": {},
            },
        )
    else:
        _write_json(
            wf / "02_cases" / "case_C001.json",
            {
                "case_id": f"{wf_id}-C001",
                "paper_id": "P001",
                "title": "T",
                "technique": "X",
                "organism": "O",
                "scale": "bench",
                "steps": [
                    {
                        "position": 1,
                        "name": "S",
                        "description": "D",
                        "equipment": ["E"],
                        "parameters": {},
                    }
                ],
            },
        )
    return wf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discover_workflows(tmp_path):
    """discover_workflows returns W* dirs, not _versions/ or plain files."""
    _make_workflow(tmp_path, "WB001", "Alpha")
    _make_workflow(tmp_path, "WB002", "Beta")
    _make_workflow(tmp_path, "WB003", "Gamma")
    # _versions/ dir — should be excluded
    versions_dir = tmp_path / "_versions"
    versions_dir.mkdir()
    (versions_dir / "composition_data.json").write_text("{}")
    # Non-workflow file
    (tmp_path / "README.md").write_text("hello")

    results = discover_workflows(tmp_path)
    names = [p.name for p in results]
    assert len(results) == 3
    assert all(n.startswith("W") for n in names)
    assert not any("_versions" in n for n in names)


def test_discover_workflows_excludes_versions(tmp_path):
    """_versions subdir inside a workflow dir is not discovered."""
    wf = _make_workflow(tmp_path, "WB005", "Test")
    versions_sub = wf / "_versions"
    versions_sub.mkdir()
    _write_json(versions_sub / "composition_data.json", {"workflow_id": "WB005-old"})

    results = discover_workflows(tmp_path)
    assert len(results) == 1
    assert results[0].name == "WB005_Test"


def test_audit_all_workflows(tmp_path):
    """audit_all_workflows returns dict keyed by workflow_id with conformance_score."""
    _make_workflow(tmp_path, "WB010", "Canonical", era="canonical")
    _make_workflow(tmp_path, "WB011", "Legacy", era="legacy")

    results = audit_all_workflows(tmp_path)
    assert len(results) == 2
    assert "WB010" in results
    assert "WB011" in results
    assert "conformance_score" in results["WB010"]
    assert "conformance_score" in results["WB011"]
    # Canonical should score higher than legacy
    assert results["WB010"]["conformance_score"] >= results["WB011"]["conformance_score"]


def test_audit_all_with_targets(tmp_path):
    """targets filter limits auditing to matching workflow IDs."""
    _make_workflow(tmp_path, "WB005", "Alpha")
    _make_workflow(tmp_path, "WB006", "Beta")
    _make_workflow(tmp_path, "WB007", "Gamma")

    results = audit_all_workflows(tmp_path, targets=["WB005"])
    assert len(results) == 1
    assert "WB005" in results


def test_detect_cross_workflow_drift():
    """detect_cross_workflow_drift flags deprecated statistics key usage."""
    # Build fake audit results — one with a violation about deprecated key
    results = {
        "WB050": {
            "scores": {
                "composition_data": {
                    "violations": ["deprecated statistics key 'total_cases' (use 'cases_collected')"],
                }
            }
        },
        "WB051": {
            "scores": {
                "composition_data": {
                    "violations": [],
                }
            }
        },
        "WB060": {
            "scores": {
                "composition_data": {
                    "violations": ["deprecated statistics key 'total_cases' (use 'cases_collected')"],
                }
            }
        },
    }
    drifts = detect_cross_workflow_drift(results)
    assert len(drifts) >= 1
    drift = drifts[0]
    assert drift["drift_type"] == "statistics_field"
    assert "total_cases" in drift["found_names"]
    assert "WB050" in drift["affected_workflows"]
    assert "WB060" in drift["affected_workflows"]


def test_generate_batch_summary(tmp_path):
    """generate_batch_summary produces required keys with correct types."""
    _make_workflow(tmp_path, "WB020", "Alpha", era="canonical")
    _make_workflow(tmp_path, "WB021", "Beta", era="legacy")

    results = audit_all_workflows(tmp_path)
    drifts = detect_cross_workflow_drift(results)
    summary = generate_batch_summary(results, drifts)

    required_keys = [
        "total_workflows",
        "mean_conformance",
        "schema_era_distribution",
        "conformance_histogram",
        "migration_candidates",
    ]
    for key in required_keys:
        assert key in summary, f"missing key: {key}"

    assert summary["total_workflows"] == 2
    assert isinstance(summary["mean_conformance"], float)
    assert isinstance(summary["schema_era_distribution"], dict)
    assert isinstance(summary["conformance_histogram"], dict)
    assert isinstance(summary["migration_candidates"], list)


def test_cli_main(tmp_path):
    """main() can be imported and runs without error."""
    _make_workflow(tmp_path, "WB030", "Test", era="canonical")

    summary = main([str(tmp_path), "--summary-only"])
    assert summary is not None
    assert summary["total_workflows"] == 1
    assert (tmp_path / "audit_summary.json").exists()
