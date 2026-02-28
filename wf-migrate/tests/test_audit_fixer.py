"""Tests for audit_fixer.py."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from audit_fixer import (
    load_pending_violations,
    get_case_violation_map,
    apply_targeted_fixes,
    update_audit_report,
)


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_audit_report(wf_dir, violations=None, resolved_violations=None):
    """Create a minimal audit_report.json."""
    scores = {
        "composition_data": {
            "score": 0.5,
            "violations": [],
            "detailed_violations": violations or [],
        }
    }
    report = {
        "audit_version": "2.0.0",
        "workflow_id": "WB005",
        "conformance_score": 0.65,
        "scores": scores,
    }
    if resolved_violations:
        report["migration_applied"] = {"migrated_at": "2026-01-01T00:00:00Z"}
        scores["composition_data"]["detailed_violations"].extend(resolved_violations)
    _write_json(wf_dir / "00_metadata" / "audit_report.json", report)
    return report


def test_load_pending_violations_basic(tmp_path):
    """Load pending violations from fresh audit report (no migration_applied)."""
    wf_dir = tmp_path / "WB005_Test"
    violations = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0", "error": "Input should be a valid string",
         "error_type": "wrong_type", "fix_hint": "..."},
        {"file": "composition_data.json", "record": "WB005",
         "path": "statistics.papers_analyzed", "error": "Field required",
         "error_type": "missing", "fix_hint": "..."},
    ]
    _make_audit_report(wf_dir, violations=violations)

    pending = load_pending_violations(wf_dir)
    assert "composition_data" in pending
    assert len(pending["composition_data"]) == 2


def test_load_pending_violations_filters_resolved(tmp_path):
    """Already-resolved violations should be filtered out."""
    wf_dir = tmp_path / "WB005_Test"
    violations = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0", "error": "wrong type",
         "error_type": "wrong_type", "fix_hint": "..."},
    ]
    resolved = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.1", "error": "wrong type",
         "error_type": "wrong_type", "fix_hint": "...",
         "fix_status": "resolved", "fix_action": "done", "fix_timestamp": "..."},
    ]
    _make_audit_report(wf_dir, violations=violations, resolved_violations=resolved)

    pending = load_pending_violations(wf_dir)
    assert len(pending.get("composition_data", [])) == 1


def test_load_pending_violations_missing_file(tmp_path):
    """No audit_report.json -> empty dict."""
    wf_dir = tmp_path / "WB005_Test"
    wf_dir.mkdir(parents=True, exist_ok=True)
    assert load_pending_violations(wf_dir) == {}


def test_get_case_violation_map(tmp_path):
    wf_dir = tmp_path / "WB005_Test"
    pending = {
        "case_cards": [
            {"file": "02_cases/case_C001.json", "record": "WB005-C001",
             "path": "completeness.score", "error": "Field required",
             "error_type": "missing"},
            {"file": "02_cases/case_C002.json", "record": "WB005-C002",
             "path": "workflow_context.workflow_id", "error": "Field required",
             "error_type": "missing"},
        ]
    }
    case_map = get_case_violation_map(pending)
    assert case_map == {"case_C001.json": True, "case_C002.json": True}


def test_apply_targeted_fixes_wrong_type(tmp_path):
    """wrong_type: boundary_inputs object -> string via name extraction."""
    wf_dir = tmp_path / "WB005_Test"
    _write_json(wf_dir / "composition_data.json", {
        "workflow_id": "WB005",
        "modularity": {
            "boundary_inputs": [
                {"name": "gDNA sample", "type": "material"},
                {"name": "Buffer", "type": "reagent"},
            ]
        }
    })

    pending = {
        "composition_data": [
            {"file": "composition_data.json", "record": "WB005",
             "path": "modularity.boundary_inputs.0",
             "error": "Input should be a valid string",
             "error_type": "wrong_type", "fix_hint": "..."},
            {"file": "composition_data.json", "record": "WB005",
             "path": "modularity.boundary_inputs.1",
             "error": "Input should be a valid string",
             "error_type": "wrong_type", "fix_hint": "..."},
        ]
    }

    results = apply_targeted_fixes(wf_dir, pending, dry_run=False)
    assert len(results) == 2
    assert all(r["fix_status"] == "resolved" for r in results)

    with open(wf_dir / "composition_data.json") as f:
        data = json.load(f)
    assert data["modularity"]["boundary_inputs"] == ["gDNA sample", "Buffer"]


def test_apply_targeted_fixes_missing_completeness_score(tmp_path):
    """missing: completeness.score -> add default 0.0."""
    wf_dir = tmp_path / "WB005_Test"
    _write_json(wf_dir / "02_cases" / "case_C001.json", {
        "case_id": "WB005-C001",
        "completeness": {"fulltext": False, "step_detail": "partial"},
        "workflow_context": {"service_context": "testing"},
    })

    pending = {
        "case_cards": [
            {"file": "02_cases/case_C001.json", "record": "WB005-C001",
             "path": "completeness.score", "error": "Field required",
             "error_type": "missing", "fix_hint": "..."},
        ]
    }

    results = apply_targeted_fixes(wf_dir, pending, dry_run=False)
    assert results[0]["fix_status"] == "resolved"

    with open(wf_dir / "02_cases" / "case_C001.json") as f:
        data = json.load(f)
    assert data["completeness"]["score"] == 0.0


def test_apply_targeted_fixes_missing_workflow_id(tmp_path):
    """missing: workflow_context.workflow_id -> extract from composition_data."""
    wf_dir = tmp_path / "WB005_Test"
    _write_json(wf_dir / "composition_data.json", {"workflow_id": "WB005"})
    _write_json(wf_dir / "02_cases" / "case_C001.json", {
        "case_id": "WB005-C001",
        "workflow_context": {"service_context": "testing"},
    })

    pending = {
        "case_cards": [
            {"file": "02_cases/case_C001.json", "record": "WB005-C001",
             "path": "workflow_context.workflow_id", "error": "Field required",
             "error_type": "missing", "fix_hint": "..."},
        ]
    }

    results = apply_targeted_fixes(wf_dir, pending, dry_run=False)
    assert results[0]["fix_status"] == "resolved"

    with open(wf_dir / "02_cases" / "case_C001.json") as f:
        data = json.load(f)
    assert data["workflow_context"]["workflow_id"] == "WB005"


def test_apply_targeted_fixes_dry_run(tmp_path):
    """dry_run: fix_status should be 'skipped', file unchanged."""
    wf_dir = tmp_path / "WB005_Test"
    _write_json(wf_dir / "composition_data.json", {
        "workflow_id": "WB005",
        "modularity": {"boundary_inputs": [{"name": "sample"}]}
    })

    pending = {
        "composition_data": [
            {"file": "composition_data.json", "record": "WB005",
             "path": "modularity.boundary_inputs.0",
             "error": "Input should be a valid string",
             "error_type": "wrong_type", "fix_hint": "..."},
        ]
    }

    results = apply_targeted_fixes(wf_dir, pending, dry_run=True)
    assert results[0]["fix_status"] == "skipped"

    with open(wf_dir / "composition_data.json") as f:
        data = json.load(f)
    assert isinstance(data["modularity"]["boundary_inputs"][0], dict)


def test_update_audit_report_records_status(tmp_path):
    """update_audit_report should write fix_status + migration_applied."""
    wf_dir = tmp_path / "WB005_Test"
    violations = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0",
         "error": "Input should be a valid string",
         "error_type": "wrong_type", "fix_hint": "..."},
        {"file": "composition_data.json", "record": "WB005",
         "path": "statistics.papers_analyzed",
         "error": "Field required",
         "error_type": "missing", "fix_hint": "..."},
    ]
    _make_audit_report(wf_dir, violations=violations)

    fix_results = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0",
         "error": "Input should be a valid string",
         "error_type": "wrong_type", "fix_hint": "...",
         "fix_status": "resolved", "fix_action": "object-to-string",
         "fix_timestamp": "2026-02-28T12:00:00Z"},
        {"file": "composition_data.json", "record": "WB005",
         "path": "statistics.papers_analyzed",
         "error": "Field required",
         "error_type": "missing", "fix_hint": "...",
         "fix_status": "unresolved", "fix_action": "no auto-fix available",
         "fix_timestamp": "2026-02-28T12:00:00Z"},
    ]

    report = update_audit_report(wf_dir, fix_results, pre_score=0.65)

    assert "migration_applied" in report
    ma = report["migration_applied"]
    assert ma["resolved"] == 1
    assert ma["unresolved"] == 1
    assert ma["pre_migration_score"] == 0.65
    assert ma["post_migration_score"] > 0.65

    dv = report["scores"]["composition_data"]["detailed_violations"]
    resolved_v = [v for v in dv if v.get("fix_status") == "resolved"]
    assert len(resolved_v) == 1
    assert resolved_v[0]["fix_action"] == "object-to-string"


def test_update_audit_report_idempotent(tmp_path):
    """Running update twice should not duplicate fix_status entries."""
    wf_dir = tmp_path / "WB005_Test"
    violations = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0",
         "error": "Input should be a valid string",
         "error_type": "wrong_type", "fix_hint": "..."},
    ]
    _make_audit_report(wf_dir, violations=violations)

    fix_results = [
        {"file": "composition_data.json", "record": "WB005",
         "path": "modularity.boundary_inputs.0",
         "error": "Input should be a valid string",
         "error_type": "wrong_type",
         "fix_status": "resolved", "fix_action": "done",
         "fix_timestamp": "2026-02-28T12:00:00Z"},
    ]

    update_audit_report(wf_dir, fix_results, pre_score=0.65)
    report = update_audit_report(wf_dir, fix_results, pre_score=0.65)

    dv = report["scores"]["composition_data"]["detailed_violations"]
    assert len(dv) == 1
    assert dv[0]["fix_status"] == "resolved"
