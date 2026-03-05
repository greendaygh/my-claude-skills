"""RunTracker: multi-workflow paper state + run lifecycle management.

CLI usage:
    python -m scripts.run_tracker start-run --wf-id WB030 --registry ~/dev/wf-mining/run_registry.json
    python -m scripts.run_tracker add-papers --wf-id WB030 --papers '[{"paper_id":"P001","doi":"10.1038/..."}]' --run-id 1 --registry ...
    python -m scripts.run_tracker mark-fetched --wf-id WB030 --paper-id P001 --registry ...
    python -m scripts.run_tracker mark-extracted --wf-id WB030 --paper-id P001 --registry ...
    python -m scripts.run_tracker mark-failed --wf-id WB030 --paper-id P001 --reason "timeout" --registry ...
    python -m scripts.run_tracker apply-verdict --wf-id WB030 --paper-id P001 --verdict accept --registry ...
    python -m scripts.run_tracker apply-verdicts --wf-id WB030 --result ~/dev/wf-mining/WB030/runs/run_result_1.json --registry ...
    python -m scripts.run_tracker complete-run --wf-id WB030 --run-id 1 --registry ...
    python -m scripts.run_tracker summary --registry ...

All CLI commands output a single JSON line to stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models.state import (
    GlobalStats, PaperStatus, RunRecord, RunRegistry,
    SaturationMetrics, StableCache, WorkflowEntry,
)


class RunTracker:
    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path)
        self._load()

    def _load(self) -> None:
        if self.registry_path.exists():
            data = json.loads(self.registry_path.read_text())
            self._registry = RunRegistry.model_validate(data)
        else:
            now = datetime.now(timezone.utc).isoformat()
            self._registry = RunRegistry(
                created=now,
                last_updated=now,
                global_stats=GlobalStats(),
            )

    def _save(self) -> None:
        """Atomic write: write to tmp file, then rename."""
        self._registry.last_updated = datetime.now(timezone.utc).isoformat()
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self.registry_path.parent,
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(self._registry.model_dump_json(indent=2))
            os.replace(tmp_path, self.registry_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _ensure_workflow(self, wf_id: str, domain: str = "") -> WorkflowEntry:
        if wf_id not in self._registry.workflows:
            self._registry.workflows[wf_id] = WorkflowEntry(domain=domain)
        return self._registry.workflows[wf_id]

    # --- Run lifecycle ---

    def start_run(self, wf_id: str, domain: str = "") -> int:
        wf = self._ensure_workflow(wf_id, domain)
        run_id = len(wf.runs) + 1
        self._registry.global_stats.total_runs += 1
        self._save()
        return run_id

    def complete_run(self, wf_id: str, run_id: int,
                     papers_searched: int = 0, papers_selected: int = 0,
                     papers_accepted: int = 0, new_extractions: int = 0,
                     new_variants: int = 0, panels_run: list[str] | None = None,
                     panel_mode: str = "full",
                     domain: str = "") -> dict:
        wf = self._ensure_workflow(wf_id)
        if domain and not wf.domain:
            wf.domain = domain
        # Prevent duplicate run entries
        wf.runs = [r for r in wf.runs if r.run_id != run_id]
        record = RunRecord(
            run_id=run_id,
            run_date=datetime.now(timezone.utc).isoformat(),
            papers_searched=papers_searched,
            papers_selected=papers_selected,
            papers_accepted=papers_accepted,
            new_extractions=new_extractions,
            new_variants=new_variants,
            panels_run=panels_run or [],
            panel_mode=panel_mode,
        )
        wf.runs.append(record)
        self._registry.global_stats.total_runs = sum(
            len(w.runs) for w in self._registry.workflows.values()
        )
        self._registry.global_stats.total_extracted = sum(
            1 for w in self._registry.workflows.values()
            for ps in w.paper_status.values()
            if ps.status == "extracted"
        )
        self._save()
        return record.model_dump()

    # --- Paper state management ---

    def get_known_dois(self, wf_id: str) -> list[str]:
        wf = self._registry.workflows.get(wf_id)
        if not wf:
            return []
        return list(wf.known_dois)

    def add_papers(self, wf_id: str, run_id: int, papers: list[dict]) -> int:
        """Add papers to workflow. Returns count of newly added papers."""
        wf = self._ensure_workflow(wf_id)
        added = 0
        for p in papers:
            paper_id = p["paper_id"]
            doi = p.get("doi", "")
            if paper_id not in wf.paper_status:
                wf.paper_status[paper_id] = PaperStatus(
                    doi=doi, status="pending", run_id=run_id,
                )
                if doi and doi not in wf.known_dois:
                    wf.known_dois.append(doi)
                added += 1
                self._registry.global_stats.total_papers += 1
        self._save()
        return added

    def get_pending_extractions(self, wf_id: str) -> list[str]:
        wf = self._registry.workflows.get(wf_id)
        if not wf:
            return []
        return [
            pid for pid, ps in wf.paper_status.items()
            if ps.status in ("pending", "fetched")
        ]

    def mark_fetched(self, wf_id: str, paper_id: str) -> None:
        wf = self._ensure_workflow(wf_id)
        if paper_id in wf.paper_status:
            wf.paper_status[paper_id].status = "fetched"
            self._save()

    def mark_extracted(self, wf_id: str, paper_id: str) -> None:
        wf = self._ensure_workflow(wf_id)
        if paper_id in wf.paper_status:
            wf.paper_status[paper_id].status = "extracted"
            self._registry.global_stats.total_extracted += 1
            self._save()

    def mark_failed(self, wf_id: str, paper_id: str, reason: str = "") -> None:
        wf = self._ensure_workflow(wf_id)
        if paper_id in wf.paper_status:
            wf.paper_status[paper_id].status = "failed"
            wf.paper_status[paper_id].error = reason
            self._save()

    # --- Verdict processing ---

    def apply_verdict(self, wf_id: str, paper_id: str, verdict: str, reason: str = "") -> None:
        wf = self._ensure_workflow(wf_id)
        if paper_id not in wf.paper_status:
            return
        ps = wf.paper_status[paper_id]
        ps.panel_verdict = verdict
        if verdict == "accept":
            if ps.status not in ("extracted",):
                ps.status = "extracted"
        elif verdict == "reject":
            ps.status = "rejected"
            ps.error = reason or "rejected by panel"
        elif verdict == "flag_reextract":
            ps.status = "pending"
        self._save()

    def apply_verdicts_from_file(self, wf_id: str, result_path: Path) -> dict:
        """Apply verdicts from a run_result JSON file."""
        data = json.loads(result_path.read_text())
        verdicts = data.get("verdicts", data.get("final_verdicts", {}))
        # Handle Panel B output format: {"papers": [{"paper_id": ..., "verdict": ...}]}
        if not verdicts:
            items = data.get("papers", data.get("reviews", []))
            if items:
                verdicts = {
                    p["paper_id"]: p.get("verdict", p.get("panel_b_verdict", "accept"))
                    for p in items if "paper_id" in p
                }
        for paper_id, verdict_info in verdicts.items():
            if isinstance(verdict_info, str):
                self.apply_verdict(wf_id, paper_id, verdict_info)
            elif isinstance(verdict_info, dict):
                self.apply_verdict(
                    wf_id, paper_id,
                    verdict_info.get("verdict", "accept"),
                    verdict_info.get("reason", ""),
                )
        return {"applied": len(verdicts)}

    # --- Saturation detection ---

    def check_saturation(self, wf_id: str) -> tuple[str, str]:
        wf = self._registry.workflows.get(wf_id)
        if not wf or not wf.saturation:
            return ("search", "first_run")
        sat = wf.saturation
        ratio = sat.overlap_ratio_last_run
        total = sat.total_unique_papers
        if ratio >= 0.85 and total >= 30:
            return ("skip", "saturated")
        if ratio >= 0.70:
            return ("mutate", "moderate")
        if ratio >= 0.50:
            return ("search", "diminishing")
        return ("search", "productive")

    def update_saturation(self, wf_id: str, searched: int, new_count: int) -> None:
        wf = self._ensure_workflow(wf_id)
        if not wf.saturation:
            wf.saturation = SaturationMetrics(
                total_unique_papers=new_count,
                overlap_ratio_last_run=0.0,
                saturation_level="productive",
            )
        else:
            overlap = 1.0 - (new_count / max(searched, 1))
            wf.saturation.overlap_ratio_last_run = round(max(0.0, min(1.0, overlap)), 3)
            wf.saturation.total_unique_papers += new_count
            action, level = self.check_saturation(wf_id)
            wf.saturation.saturation_level = level if level in (
                "productive", "diminishing", "moderate", "saturated"
            ) else "productive"
        self._save()

    # --- Execution condition ---

    def determine_execution(self, wf_id: str) -> dict:
        wf = self._registry.workflows.get(wf_id)
        if not wf:
            return {"action": "execute", "is_first_run": True, "run_count": 0}
        run_count = len(wf.runs)
        action_str, reason = self.check_saturation(wf_id)
        if action_str == "skip":
            return {"action": "skip", "reason": reason, "run_count": run_count}
        return {
            "action": "execute",
            "is_first_run": run_count == 0,
            "run_count": run_count,
            "saturation_action": action_str,
            "saturation_reason": reason,
        }

    def determine_panel_mode(self, wf_id: str) -> str:
        wf = self._registry.workflows.get(wf_id)
        if not wf:
            return "full"
        run_count = len(wf.runs)
        if run_count < 5:
            return "full"
        recent = wf.runs[-2:] if len(wf.runs) >= 2 else wf.runs
        recent_rejects = sum(
            1 for r in recent
            for pid, ps in wf.paper_status.items()
            if ps.panel_verdict == "reject" and ps.run_id == r.run_id
        )
        if recent_rejects > 0:
            return "full"
        return "quick"

    # --- Statistics ---

    def summary(self) -> dict:
        total_wf = len(self._registry.workflows)
        total_papers = self._registry.global_stats.total_papers
        total_extracted = self._registry.global_stats.total_extracted
        total_runs = self._registry.global_stats.total_runs
        per_wf = {}
        for wf_id, wf in self._registry.workflows.items():
            statuses = {}
            for ps in wf.paper_status.values():
                statuses[ps.status] = statuses.get(ps.status, 0) + 1
            per_wf[wf_id] = {
                "runs": len(wf.runs),
                "papers": len(wf.paper_status),
                "statuses": statuses,
                "saturation": wf.saturation.saturation_level if wf.saturation else "unknown",
            }
        return {
            "total_workflows": total_wf,
            "total_papers": total_papers,
            "total_extracted": total_extracted,
            "total_runs": total_runs,
            "workflows": per_wf,
        }


# ========== CLI ==========

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("start-run")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--domain", default="")
    p.add_argument("--registry", required=True)

    p = sub.add_parser("add-papers")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--papers", required=True, help="JSON array string")
    p.add_argument("--registry", required=True)

    p = sub.add_parser("mark-fetched")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--registry", required=True)

    p = sub.add_parser("mark-extracted")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--registry", required=True)

    p = sub.add_parser("mark-failed")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--registry", required=True)

    p = sub.add_parser("apply-verdict")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--reason", default="")
    p.add_argument("--registry", required=True)

    p = sub.add_parser("apply-verdicts")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--result", required=True)
    p.add_argument("--registry", required=True)

    p = sub.add_parser("complete-run")
    p.add_argument("--wf-id", required=True)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--papers-searched", type=int, default=0)
    p.add_argument("--papers-selected", type=int, default=0)
    p.add_argument("--papers-accepted", type=int, default=0)
    p.add_argument("--new-extractions", type=int, default=0)
    p.add_argument("--new-variants", type=int, default=0)
    p.add_argument("--panels-run", default="")
    p.add_argument("--panel-mode", default="full")
    p.add_argument("--domain", default="")
    p.add_argument("--registry", required=True)

    p = sub.add_parser("summary")
    p.add_argument("--registry", required=True)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    tracker = RunTracker(Path(args.registry))
    result: Any = None

    if args.command == "start-run":
        run_id = tracker.start_run(args.wf_id, args.domain)
        result = {"run_id": run_id}

    elif args.command == "add-papers":
        papers = json.loads(args.papers)
        added = tracker.add_papers(args.wf_id, args.run_id, papers)
        result = {"added": added}

    elif args.command == "mark-fetched":
        tracker.mark_fetched(args.wf_id, args.paper_id)
        result = {"status": "fetched", "paper_id": args.paper_id}

    elif args.command == "mark-extracted":
        tracker.mark_extracted(args.wf_id, args.paper_id)
        result = {"status": "extracted", "paper_id": args.paper_id}

    elif args.command == "mark-failed":
        tracker.mark_failed(args.wf_id, args.paper_id, args.reason)
        result = {"status": "failed", "paper_id": args.paper_id}

    elif args.command == "apply-verdict":
        tracker.apply_verdict(args.wf_id, args.paper_id, args.verdict, args.reason)
        result = {"verdict": args.verdict, "paper_id": args.paper_id}

    elif args.command == "apply-verdicts":
        result = tracker.apply_verdicts_from_file(args.wf_id, Path(args.result))

    elif args.command == "complete-run":
        panels = [p.strip() for p in args.panels_run.split(",") if p.strip()] if args.panels_run else []
        result = tracker.complete_run(
            args.wf_id, args.run_id,
            papers_searched=args.papers_searched,
            papers_selected=args.papers_selected,
            papers_accepted=args.papers_accepted,
            new_extractions=args.new_extractions,
            new_variants=args.new_variants,
            panels_run=panels,
            panel_mode=args.panel_mode,
            domain=getattr(args, "domain", ""),
        )

    elif args.command == "summary":
        result = tracker.summary()

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
