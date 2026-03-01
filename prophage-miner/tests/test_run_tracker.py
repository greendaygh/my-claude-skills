"""Tests for run_tracker.py - Run state management and PMID deduplication."""

import json
from pathlib import Path

import pytest

from scripts.run_tracker import RunTracker


class TestRunTrackerInit:
    def test_start_run_creates_registry(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        assert run_id == "run_001"
        reg = tmp_phage_dir / "00_config" / "run_registry.json"
        assert reg.exists()

    def test_init_loads_existing_registry(self, tmp_phage_dir):
        tracker1 = RunTracker(tmp_phage_dir)
        tracker1.start_run()
        tracker1.complete_run("run_001")
        tracker2 = RunTracker(tmp_phage_dir)
        assert tracker2.get_known_pmids() == set()
        assert tracker2.summary()["total_runs"] == 1


class TestKnownPmids:
    def test_get_known_pmids_empty(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        assert tracker.get_known_pmids() == set()

    def test_add_papers_updates_known_pmids(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        papers = [
            {"paper_id": "P001", "pmid": "111"},
            {"paper_id": "P002", "pmid": "222"},
        ]
        tracker.add_papers(run_id, papers)
        assert tracker.get_known_pmids() == {"111", "222"}

    def test_add_papers_across_runs(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        r1 = tracker.start_run()
        tracker.add_papers(r1, [{"paper_id": "P001", "pmid": "111"}])
        tracker.complete_run(r1)
        r2 = tracker.start_run()
        tracker.add_papers(r2, [{"paper_id": "P002", "pmid": "222"}])
        assert tracker.get_known_pmids() == {"111", "222"}


class TestPaperIdSequence:
    def test_get_next_paper_id_sequential(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        assert tracker.get_next_paper_id() == "P001"
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [{"paper_id": "P001", "pmid": "111"}])
        assert tracker.get_next_paper_id() == "P002"

    def test_get_next_paper_id_after_many(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        papers = [{"paper_id": f"P{i:03d}", "pmid": str(i)} for i in range(1, 51)]
        tracker.add_papers(run_id, papers)
        assert tracker.get_next_paper_id() == "P051"


class TestExtractionStatus:
    def test_get_pending_extractions(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [
            {"paper_id": "P001", "pmid": "111"},
            {"paper_id": "P002", "pmid": "222"},
        ])
        pending = tracker.get_pending_extractions()
        assert set(pending) == {"P001", "P002"}

    def test_mark_extracted_updates_status(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [{"paper_id": "P001", "pmid": "111"}])
        tracker.mark_extracted("P001")
        assert tracker.get_pending_extractions() == []

    def test_mark_failed_records_reason(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [{"paper_id": "P001", "pmid": "111"}])
        tracker.mark_extract_failed("P001", "PMC timeout")
        status = tracker._registry["paper_status"]["P001"]
        assert status["status"] == "failed"
        assert status["error"] == "PMC timeout"

    def test_failed_not_in_pending(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [{"paper_id": "P001", "pmid": "111"}])
        tracker.mark_extract_failed("P001", "error")
        assert "P001" not in tracker.get_pending_extractions()


class TestRunLifecycle:
    def test_complete_run_records_stats(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()
        tracker.add_papers(run_id, [
            {"paper_id": "P001", "pmid": "111"},
            {"paper_id": "P002", "pmid": "222"},
        ])
        tracker.mark_extracted("P001")
        tracker.mark_extract_failed("P002", "timeout")
        tracker.complete_run(run_id)
        runs = tracker._registry["runs"]
        assert len(runs) == 1
        assert runs[0]["papers_added"] == 2
        assert runs[0]["papers_extracted"] == 1
        assert runs[0]["papers_failed"] == 1

    def test_multiple_runs_sequential(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        r1 = tracker.start_run()
        tracker.add_papers(r1, [{"paper_id": "P001", "pmid": "111"}])
        tracker.mark_extracted("P001")
        tracker.complete_run(r1)
        r2 = tracker.start_run()
        assert r2 == "run_002"
        tracker.add_papers(r2, [{"paper_id": "P002", "pmid": "222"}])
        tracker.mark_extracted("P002")
        tracker.complete_run(r2)
        assert tracker.summary()["total_runs"] == 2
        assert tracker.summary()["total_papers"] == 2


class TestPersistence:
    def test_cross_session_persistence(self, tmp_phage_dir):
        tracker1 = RunTracker(tmp_phage_dir)
        run_id = tracker1.start_run()
        tracker1.add_papers(run_id, [{"paper_id": "P001", "pmid": "111"}])
        tracker1.mark_extracted("P001")
        tracker1.complete_run(run_id)

        tracker2 = RunTracker(tmp_phage_dir)
        assert tracker2.get_known_pmids() == {"111"}
        assert tracker2.get_next_paper_id() == "P002"
        assert tracker2.summary()["total_runs"] == 1
        assert tracker2.summary()["total_extracted"] == 1


class TestSummary:
    def test_summary_counts(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        r1 = tracker.start_run()
        tracker.add_papers(r1, [
            {"paper_id": "P001", "pmid": "111"},
            {"paper_id": "P002", "pmid": "222"},
            {"paper_id": "P003", "pmid": "333"},
        ])
        tracker.mark_extracted("P001")
        tracker.mark_extracted("P002")
        tracker.mark_extract_failed("P003", "error")
        tracker.complete_run(r1)

        s = tracker.summary()
        assert s["total_runs"] == 1
        assert s["total_papers"] == 3
        assert s["total_extracted"] == 2
        assert s["total_failed"] == 1

    def test_summary_empty(self, tmp_phage_dir):
        tracker = RunTracker(tmp_phage_dir)
        s = tracker.summary()
        assert s["total_runs"] == 0
        assert s["total_papers"] == 0
