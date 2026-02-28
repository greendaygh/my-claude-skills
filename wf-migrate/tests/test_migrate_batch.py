import sys
import json
import argparse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from migrate_batch import (
    discover_migration_candidates,
    find_workflow_dir,
    migrate_batch,
    generate_batch_report,
    main,
)


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def _make_legacy_workflow(base, wf_id="WB140", name="Test"):
    wf = base / f"{wf_id}_{name}"
    _write_json(wf / "composition_data.json", {
        "schema_version": "4.0.0", "workflow_id": wf_id,
        "workflow_name": name, "category": "Build", "domain": "Test",
        "version": 1.0, "composition_date": "2026-01-01",
        "statistics": {"total_papers": 1, "total_cases": 1,
                       "total_variants": 1, "total_uo_types": 1,
                       "qc_checkpoints": 1, "confidence_score": 0.7}
    })
    _write_json(wf / "01_papers" / "paper_list.json", {
        "papers": [{"paper_id": "P001", "pmid": "111", "doi": "10.1/a",
                     "title": "T", "authors": "A", "year": 2020, "journal": "J"}]
    })
    _write_json(wf / "02_cases" / "case_C001.json", {
        "case_id": f"{wf_id}-C001", "paper_id": "P001", "title": "T",
        "technique": "X", "organism": "O", "scale": "bench",
        "steps": [{"position": 1, "name": "S", "description": "D",
                    "equipment": ["E"], "parameters": {"t": "37C"}}]
    })
    return wf


def test_discover_migration_candidates(tmp_path):
    base = tmp_path
    _write_json(base / "audit_summary.json", {
        "migration_candidates": [
            {"workflow_id": "WB140", "score": 0.42, "priority": "high"},
            {"workflow_id": "WT050", "score": 0.72, "priority": "low"},
            {"workflow_id": "WT120", "score": 0.25, "priority": "critical"},
        ]
    })

    # No filter → returns all
    all_candidates = discover_migration_candidates(base)
    assert len(all_candidates) == 3

    # min_priority="high" → includes critical + high
    high_candidates = discover_migration_candidates(base, min_priority="high")
    ids = {c["workflow_id"] for c in high_candidates}
    assert ids == {"WB140", "WT120"}


def test_discover_migration_candidates_no_audit(tmp_path):
    result = discover_migration_candidates(tmp_path)
    assert result == []


def test_find_workflow_dir(tmp_path):
    (tmp_path / "WB140_LiquidCulture").mkdir()
    (tmp_path / "WT050_Sample").mkdir()

    found = find_workflow_dir(tmp_path, "WB140")
    assert found is not None
    assert found.name == "WB140_LiquidCulture"

    not_found = find_workflow_dir(tmp_path, "WB999")
    assert not_found is None


def test_migrate_batch_with_targets(tmp_path):
    _make_legacy_workflow(tmp_path, "WB140", "LiquidCulture")
    _make_legacy_workflow(tmp_path, "WB150", "SolidCulture")

    result = migrate_batch(tmp_path, targets=["WB140"])

    # Only WB140 should have a migration_report.json
    assert (tmp_path / "WB140_LiquidCulture" / "00_metadata" / "migration_report.json").exists()
    assert not (tmp_path / "WB150_SolidCulture" / "00_metadata" / "migration_report.json").exists()

    assert result["total_workflows"] == 1


def test_migrate_batch_with_priority(tmp_path):
    _write_json(tmp_path / "audit_summary.json", {
        "migration_candidates": [
            {"workflow_id": "WB140", "score": 0.42, "priority": "high"},
            {"workflow_id": "WT050", "score": 0.72, "priority": "low"},
            {"workflow_id": "WT120", "score": 0.25, "priority": "critical"},
        ]
    })
    _make_legacy_workflow(tmp_path, "WB140", "LiquidCulture")
    _make_legacy_workflow(tmp_path, "WT050", "Sample")
    _make_legacy_workflow(tmp_path, "WT120", "CriticalFlow")

    result = migrate_batch(tmp_path, min_priority="high")

    assert (tmp_path / "WB140_LiquidCulture" / "00_metadata" / "migration_report.json").exists()
    assert (tmp_path / "WT120_CriticalFlow" / "00_metadata" / "migration_report.json").exists()
    assert not (tmp_path / "WT050_Sample" / "00_metadata" / "migration_report.json").exists()

    assert result["total_workflows"] == 2


def test_migrate_batch_dry_run(tmp_path):
    _make_legacy_workflow(tmp_path, "WB140", "LiquidCulture")
    case_path = tmp_path / "WB140_LiquidCulture" / "02_cases" / "case_C001.json"
    original_mtime = case_path.stat().st_mtime

    result = migrate_batch(tmp_path, targets=["WB140"], dry_run=True)

    # No case files modified
    assert case_path.stat().st_mtime == original_mtime
    # No migration_report.json written by migrator
    assert not (tmp_path / "WB140_LiquidCulture" / "00_metadata" / "migration_report.json").exists()
    # Batch report indicates dry_run
    assert result["dry_run"] is True


def test_generate_batch_migration_report():
    reports = [
        {"workflow_id": "WB140", "enriched_cases": 3,
         "skipped_cases": 0, "enrichment_version": "2.0.0"},
        {"workflow_id": "WT050", "enriched_cases": 2,
         "skipped_cases": 1, "enrichment_version": "2.0.0"},
    ]

    batch = generate_batch_report(reports)

    assert batch["total_workflows"] == 2
    assert batch["total_cases_enriched"] == 5
    assert batch["total_cases_skipped"] == 1
    assert batch["migration_version"] == "2.2.0"
    assert "migrated_at" in batch
    assert len(batch["per_workflow"]) == 2


def test_main_cli(tmp_path):
    _make_legacy_workflow(tmp_path, "WB140", "LiquidCulture")

    result = main([str(tmp_path), "--targets", "WB140", "--dry-run"])

    assert result is not None
    assert result["dry_run"] is True
    assert result["total_workflows"] == 1
    # No files modified in dry-run mode — case file untouched
    case_path = tmp_path / "WB140_LiquidCulture" / "02_cases" / "case_C001.json"
    with open(case_path) as f:
        data = json.load(f)
    assert "case_id" in data  # original structure preserved (not overwritten)
