import sys
import json
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from workflow_migrator import migrate_workflow, update_statistics


def _write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_legacy_workflow(base, wf_id="WB140", name="Test"):
    """Create a legacy workflow with 2 case cards and paper_list."""
    wf = base / f"{wf_id}_{name}"
    _write_json(wf / "composition_data.json", {
        "schema_version": "4.0.0", "workflow_id": wf_id,
        "workflow_name": name, "category": "Build", "domain": "Test",
        "version": 1.0, "composition_date": "2026-01-01",
        "statistics": {"total_papers": 2, "total_cases": 2,
                       "total_variants": 1, "total_uo_types": 2,
                       "qc_checkpoints": 1, "confidence_score": 0.8}
    })
    _write_json(wf / "01_papers" / "paper_list.json", {
        "papers": [
            {"paper_id": "P001", "pmid": "111", "doi": "10.1/a", "title": "Paper 1",
             "authors": "A", "year": 2020, "journal": "J1"},
            {"paper_id": "P002", "pmid": "222", "doi": "10.2/b", "title": "Paper 2",
             "authors": "B", "year": 2021, "journal": "J2"}
        ]
    })
    for i in [1, 2]:
        _write_json(wf / "02_cases" / f"case_C{i:03d}.json", {
            "case_id": f"{wf_id}-C{i:03d}", "paper_id": f"P{i:03d}",
            "title": f"Case {i}", "technique": "Culture", "organism": "E. coli", "scale": "bench",
            "steps": [{"position": 1, "name": "Step1", "description": "D",
                        "equipment": ["Autoclave"], "parameters": {"temp": "37C"},
                        "evidence_tag": "literature-direct"}]
        })
    return wf


def test_migrate_workflow_creates_backups(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)
    migrate_workflow(wf_dir)
    backup_dir = wf_dir / "_versions" / "pre_migration" / "02_cases"
    assert backup_dir.exists(), "_versions/pre_migration/02_cases/ should be created"
    backed_up = list(backup_dir.glob("case_C*.json"))
    assert len(backed_up) == 2, "Both original case files should be backed up"


def test_migrate_workflow_updates_cases(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)
    migrate_workflow(wf_dir)
    case_path = wf_dir / "02_cases" / "case_C001.json"
    with open(case_path) as f:
        case = json.load(f)
    assert "metadata" in case, "Migrated case should have metadata block"
    assert len(case["steps"]) == 1
    step = case["steps"][0]
    assert "step_number" in step, "step should have step_number (renamed from position)"
    assert "position" not in step, "position field should be gone after migration"
    equip = step.get("equipment", [])
    assert len(equip) == 1
    assert isinstance(equip[0], dict), "equipment items should be structured objects"
    assert "name" in equip[0]


def test_migrate_workflow_updates_statistics(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)
    migrate_workflow(wf_dir)
    with open(wf_dir / "composition_data.json") as f:
        comp = json.load(f)
    stats = comp["statistics"]
    assert "papers_analyzed" in stats, "total_papers should become papers_analyzed"
    assert "cases_collected" in stats, "total_cases should become cases_collected"
    assert "total_papers" not in stats, "deprecated total_papers should be removed"
    assert "total_cases" not in stats, "deprecated total_cases should be removed"
    assert stats["papers_analyzed"] == 2
    assert stats["cases_collected"] == 2


def test_migrate_workflow_preserves_canonical(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)
    # First migration → makes cases canonical
    migrate_workflow(wf_dir)

    # Record mtimes after first migration
    case_path = wf_dir / "02_cases" / "case_C001.json"
    mtime_after_first = case_path.stat().st_mtime

    # Second migration → should not re-write canonical files
    import time
    time.sleep(0.05)
    migrate_workflow(wf_dir)
    mtime_after_second = case_path.stat().st_mtime

    assert mtime_after_first == mtime_after_second, (
        "Canonical case files should not be rewritten on second migration"
    )


def test_migrate_workflow_dry_run(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)

    # Capture original file contents
    case_path = wf_dir / "02_cases" / "case_C001.json"
    original_content = case_path.read_text()

    report = migrate_workflow(wf_dir, dry_run=True)

    # Files should be unchanged
    assert case_path.read_text() == original_content, "dry_run should not modify files"
    assert not (wf_dir / "_versions").exists(), "dry_run should not create backup dirs"

    # Report should describe changes
    assert "total_changes" in report, "report should contain total_changes"
    assert isinstance(report.get("per_case_changes"), dict)
    # Should have changes listed for the cases
    total = report["total_changes"]
    assert total > 0, "Should report non-zero changes for legacy cases"


def test_migrate_workflow_report(tmp_path):
    wf_dir = _make_legacy_workflow(tmp_path)
    migrate_workflow(wf_dir)

    report_path = wf_dir / "00_metadata" / "migration_report.json"
    assert report_path.exists(), "migration_report.json should be created in 00_metadata/"

    with open(report_path) as f:
        report = json.load(f)

    assert report.get("workflow_id") == "WB140"
    assert "migrated_cases" in report
    assert "total_changes" in report
    assert "timestamp" in report


def test_update_statistics_field_names():
    stats = {"total_papers": 5, "total_cases": 3, "qc_checkpoints": 2}
    updated, changes = update_statistics(stats)

    assert updated.get("papers_analyzed") == 5
    assert updated.get("cases_collected") == 3
    assert updated.get("qc_checkpoints") == 2
    assert "total_papers" not in updated
    assert "total_cases" not in updated

    change_strs = " ".join(changes)
    assert "total_papers" in change_strs and "papers_analyzed" in change_strs
    assert "total_cases" in change_strs and "cases_collected" in change_strs
