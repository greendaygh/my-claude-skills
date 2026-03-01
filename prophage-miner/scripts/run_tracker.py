"""Run state manager for prophage-miner repeated execution.

Tracks runs, known PMIDs, paper extraction status, and provides
sequential paper ID generation. All state persists to run_registry.json.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class RunTracker:
    """File-based state manager for repeated prophage mining runs."""

    def __init__(self, phage_dir: Path):
        self.phage_dir = Path(phage_dir)
        self.registry_path = self.phage_dir / "00_config" / "run_registry.json"
        self._registry = self._load_or_init()

    def _load_or_init(self) -> dict:
        if self.registry_path.exists():
            return json.loads(self.registry_path.read_text())
        return {
            "created": datetime.now(timezone.utc).isoformat(),
            "total_runs": 0,
            "total_papers": 0,
            "total_extracted": 0,
            "known_pmids": [],
            "runs": [],
            "paper_status": {},
        }

    def _save(self):
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(json.dumps(self._registry, indent=2, ensure_ascii=False))

    def get_known_pmids(self) -> set[str]:
        return set(self._registry.get("known_pmids", []))

    def get_next_paper_id(self) -> str:
        existing = self._registry.get("paper_status", {})
        if not existing:
            return "P001"
        max_num = max(int(pid[1:]) for pid in existing)
        return f"P{max_num + 1:03d}"

    def get_pending_extractions(self) -> list[str]:
        return [
            pid for pid, info in self._registry.get("paper_status", {}).items()
            if info.get("status") == "pending"
        ]

    def start_run(self) -> str:
        run_num = self._registry["total_runs"] + 1
        run_id = f"run_{run_num:03d}"
        self._registry["total_runs"] = run_num
        self._registry["runs"].append({
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "papers_added": 0,
            "papers_extracted": 0,
            "papers_failed": 0,
            "status": "running",
        })
        self._save()
        print(f"[run_tracker] Run {run_id} started", file=sys.stderr)
        return run_id

    def add_papers(self, run_id: str, papers: list[dict]):
        known = set(self._registry.get("known_pmids", []))
        added = 0
        for p in papers:
            pid = p["paper_id"]
            pmid = p["pmid"]
            if pmid not in known:
                known.add(pmid)
                self._registry["paper_status"][pid] = {
                    "pmid": pmid,
                    "status": "pending",
                    "run_id": run_id,
                }
                added += 1
        self._registry["known_pmids"] = sorted(known)
        self._registry["total_papers"] = len(self._registry["paper_status"])
        run_entry = self._find_run(run_id)
        if run_entry:
            run_entry["papers_added"] = added
        self._save()
        print(f"[run_tracker] {added} papers added to {run_id}", file=sys.stderr)

    def mark_extracted(self, paper_id: str):
        if paper_id in self._registry["paper_status"]:
            self._registry["paper_status"][paper_id]["status"] = "extracted"
            self._update_counts()
            self._save()

    def mark_extract_failed(self, paper_id: str, reason: str):
        if paper_id in self._registry["paper_status"]:
            self._registry["paper_status"][paper_id]["status"] = "failed"
            self._registry["paper_status"][paper_id]["error"] = reason
            self._update_counts()
            self._save()

    def complete_run(self, run_id: str):
        run_entry = self._find_run(run_id)
        if run_entry:
            run_papers = {
                pid: info for pid, info in self._registry["paper_status"].items()
                if info.get("run_id") == run_id
            }
            run_entry["papers_extracted"] = sum(
                1 for info in run_papers.values() if info["status"] == "extracted"
            )
            run_entry["papers_failed"] = sum(
                1 for info in run_papers.values() if info["status"] == "failed"
            )
            run_entry["status"] = "completed"
        self._update_counts()
        self._save()
        s = self.summary()
        print(
            f"[run_tracker] Run {run_id} completed | "
            f"Total: {s['total_papers']} papers, {s['total_extracted']} extracted, "
            f"{s['total_failed']} failed",
            file=sys.stderr,
        )

    def summary(self) -> dict:
        statuses = self._registry.get("paper_status", {})
        return {
            "total_runs": self._registry.get("total_runs", 0),
            "total_papers": len(statuses),
            "total_extracted": sum(1 for v in statuses.values() if v["status"] == "extracted"),
            "total_failed": sum(1 for v in statuses.values() if v["status"] == "failed"),
            "total_pending": sum(1 for v in statuses.values() if v["status"] == "pending"),
        }

    def _find_run(self, run_id: str) -> dict | None:
        for r in self._registry["runs"]:
            if r["run_id"] == run_id:
                return r
        return None

    def _update_counts(self):
        statuses = self._registry.get("paper_status", {})
        self._registry["total_papers"] = len(statuses)
        self._registry["total_extracted"] = sum(
            1 for v in statuses.values() if v["status"] == "extracted"
        )
