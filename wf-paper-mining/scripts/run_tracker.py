"""RunTracker: per-workflow state management + run lifecycle (v2.0).

v2.0: Each workflow has its own wf_state.json file instead of a single registry.

CLI usage:
    python -m scripts.run_tracker start-run --wf-id WB030 --root-dir ~/dev/wf-mining
    python -m scripts.run_tracker add-papers --wf-id WB030 --papers '[{"paper_id":"P001","doi":"10.1038/..."}]' --run-id 1 --root-dir ...
    python -m scripts.run_tracker mark-fetched --wf-id WB030 --paper-id P001 --root-dir ...
    python -m scripts.run_tracker mark-extracted --wf-id WB030 --paper-id P001 --root-dir ...
    python -m scripts.run_tracker mark-failed --wf-id WB030 --paper-id P001 --reason "timeout" --root-dir ...
    python -m scripts.run_tracker apply-verdict --wf-id WB030 --paper-id P001 --verdict accept --root-dir ...
    python -m scripts.run_tracker apply-verdicts --wf-id WB030 --result ~/dev/wf-mining/WB030/runs/run_result_1.json --root-dir ...
    python -m scripts.run_tracker complete-run --wf-id WB030 --run-id 1 --root-dir ...
    python -m scripts.run_tracker summary --root-dir ...

Legacy mode (--registry) auto-detects and loads from the old single-file format.

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
    PaperStatus, RegistryIndex, RunRecord, WorkflowIndexEntry,
    WorkflowState, SaturationMetrics,
    # Legacy imports for fallback
    GlobalStats, RunRegistry, WorkflowEntry,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RunTracker:
    """Per-workflow state tracker (v2.0).

    Primary mode: RunTracker(root_dir, wf_id)
      - Reads/writes {root_dir}/{wf_id}/wf_state.json
      - Updates {root_dir}/registry_index.json

    Legacy mode: RunTracker(root_dir, wf_id, legacy_registry=Path)
      - Reads from single run_registry.json (read-only fallback)
    """

    def __init__(self, root_dir: Path, wf_id: str,
                 legacy_registry: Path | None = None):
        self.root_dir = Path(root_dir)
        self.wf_id = wf_id
        self._state_path = self.root_dir / wf_id / "wf_state.json"
        self._index_path = self.root_dir / "registry_index.json"
        self._legacy_registry = legacy_registry
        self._load()

    def _load(self) -> None:
        if self._state_path.exists():
            data = json.loads(self._state_path.read_text())
            self._state = WorkflowState.model_validate(data)
        elif self._legacy_registry and self._legacy_registry.exists():
            # Fallback: extract this workflow from legacy registry
            reg_data = json.loads(self._legacy_registry.read_text())
            old_reg = RunRegistry.model_validate(reg_data)
            wf_entry = old_reg.workflows.get(self.wf_id)
            if wf_entry:
                self._state = WorkflowState(
                    workflow_id=self.wf_id,
                    domain=wf_entry.domain,
                    runs=wf_entry.runs,
                    paper_status=wf_entry.paper_status,
                    known_dois=wf_entry.known_dois,
                    saturation=wf_entry.saturation,
                    stable_cache=wf_entry.stable_cache,
                    last_error=wf_entry.last_error,
                )
            else:
                self._state = WorkflowState(workflow_id=self.wf_id)
            print(
                f"[run_tracker] Loaded {self.wf_id} from legacy registry. "
                f"Run migrate_registry to convert to v2 format.",
                file=sys.stderr,
            )
        else:
            self._state = WorkflowState(workflow_id=self.wf_id)

    def _save(self) -> None:
        """Atomic write: wf_state.json + index update."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=self._state_path.parent, suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(self._state.model_dump_json(indent=2))
            os.replace(tmp_path, self._state_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise
        self._update_index()

    def _update_index(self) -> None:
        """Update only this workflow's entry in registry_index.json."""
        if self._index_path.exists():
            try:
                idx = RegistryIndex.model_validate(
                    json.loads(self._index_path.read_text())
                )
            except Exception:
                idx = RegistryIndex(created=_now())
        else:
            idx = RegistryIndex(created=_now())

        extracted = sum(
            1 for ps in self._state.paper_status.values()
            if ps.status == "extracted"
        )
        idx.workflows[self.wf_id] = WorkflowIndexEntry(
            domain=self._state.domain,
            run_count=len(self._state.runs),
            paper_count=len(self._state.paper_status),
            extracted_count=extracted,
            last_updated=_now(),
        )
        idx.last_updated = _now()

        fd, tmp_path = tempfile.mkstemp(
            dir=self._index_path.parent, suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                f.write(idx.model_dump_json(indent=2))
            os.replace(tmp_path, self._index_path)
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # --- Run lifecycle ---

    def start_run(self, domain: str = "") -> int:
        if domain and not self._state.domain:
            self._state.domain = domain
        run_id = len(self._state.runs) + 1
        # Add placeholder RunRecord so that papers added with this run_id
        # pass the _validate_run_id_references validator on next load.
        placeholder = RunRecord(run_id=run_id, run_date=_now())
        self._state.runs.append(placeholder)
        self._save()
        return run_id

    def complete_run(self, run_id: int,
                     papers_searched: int = 0, papers_selected: int = 0,
                     papers_accepted: int = 0, new_extractions: int = 0,
                     new_variants: int = 0, panels_run: list[str] | None = None,
                     panel_mode: str = "full",
                     domain: str = "") -> dict:
        if domain and not self._state.domain:
            self._state.domain = domain
        # Prevent duplicate run entries
        self._state.runs = [r for r in self._state.runs if r.run_id != run_id]
        record = RunRecord(
            run_id=run_id,
            run_date=_now(),
            papers_searched=papers_searched,
            papers_selected=papers_selected,
            papers_accepted=papers_accepted,
            new_extractions=new_extractions,
            new_variants=new_variants,
            panels_run=panels_run or [],
            panel_mode=panel_mode,
        )
        self._state.runs.append(record)
        self._save()
        return record.model_dump()

    # --- Paper state management ---

    def get_known_dois(self) -> list[str]:
        return list(self._state.known_dois)

    def add_papers(self, run_id: int, papers: list[dict]) -> int:
        """Add papers to workflow. Returns count of newly added papers."""
        added = 0
        doi_set = set(self._state.known_dois)
        for p in papers:
            paper_id = p["paper_id"]
            doi = p.get("doi", "")
            if paper_id not in self._state.paper_status:
                self._state.paper_status[paper_id] = PaperStatus(
                    doi=doi, status="pending", run_id=run_id,
                )
                if doi and doi not in doi_set:
                    self._state.known_dois.append(doi)
                    doi_set.add(doi)
                added += 1
        self._save()
        return added

    def get_pending_extractions(self) -> list[str]:
        return [
            pid for pid, ps in self._state.paper_status.items()
            if ps.status in ("pending", "fetched")
        ]

    def mark_fetched(self, paper_id: str) -> None:
        if paper_id in self._state.paper_status:
            self._state.paper_status[paper_id].status = "fetched"
            self._save()

    def mark_extracted(self, paper_id: str) -> None:
        if paper_id in self._state.paper_status:
            self._state.paper_status[paper_id].status = "extracted"
            self._save()

    def mark_failed(self, paper_id: str, reason: str = "") -> None:
        if paper_id in self._state.paper_status:
            self._state.paper_status[paper_id].status = "failed"
            self._state.paper_status[paper_id].error = reason
            self._save()

    # --- Verdict processing ---

    def _apply_verdict_nosave(self, paper_id: str, verdict: str,
                              reason: str = "") -> None:
        if paper_id not in self._state.paper_status:
            return
        ps = self._state.paper_status[paper_id]
        verdict = verdict.lower()
        ps.panel_verdict = verdict
        if verdict == "accept":
            if ps.status not in ("extracted",):
                ps.status = "extracted"
        elif verdict == "reject":
            ps.status = "rejected"
            ps.error = reason or "rejected by panel"
        elif verdict == "flag_reextract":
            ps.status = "pending"

    def apply_verdict(self, paper_id: str, verdict: str,
                      reason: str = "") -> None:
        self._apply_verdict_nosave(paper_id, verdict, reason)
        self._save()

    def apply_verdicts_from_file(self, result_path: Path) -> dict:
        """Apply verdicts from a run_result JSON file. Single _save at end."""
        data = json.loads(result_path.read_text())
        # Handle top-level list format (subagent may omit wrapper dict)
        if isinstance(data, list):
            data = {"papers": data}
        verdicts = data.get("verdicts", data.get("final_verdicts", {}))
        if not verdicts:
            items = data.get("papers", data.get("reviews", []))
            if items:
                verdicts = {
                    p["paper_id"]: p.get("verdict", p.get("panel_b_verdict", "accept"))
                    for p in items if "paper_id" in p
                }
        for paper_id, verdict_info in verdicts.items():
            if isinstance(verdict_info, str):
                self._apply_verdict_nosave(paper_id, verdict_info)
            elif isinstance(verdict_info, dict):
                self._apply_verdict_nosave(
                    paper_id,
                    verdict_info.get("verdict", "accept"),
                    verdict_info.get("reason", ""),
                )
        self._save()
        return {"applied": len(verdicts)}

    # --- Saturation detection ---

    def check_saturation(self) -> tuple[str, str]:
        sat = self._state.saturation
        if not sat:
            return ("search", "first_run")
        ratio = sat.overlap_ratio_last_run
        total = sat.total_unique_papers
        if ratio >= 0.85 and total >= 30:
            return ("skip", "saturated")
        if ratio >= 0.70:
            return ("mutate", "moderate")
        if ratio >= 0.50:
            return ("search", "diminishing")
        return ("search", "productive")

    def update_saturation(self, searched: int, new_count: int) -> None:
        if not self._state.saturation:
            self._state.saturation = SaturationMetrics(
                total_unique_papers=new_count,
                overlap_ratio_last_run=0.0,
                saturation_level="productive",
            )
        else:
            overlap = 1.0 - (new_count / max(searched, 1))
            self._state.saturation.overlap_ratio_last_run = round(
                max(0.0, min(1.0, overlap)), 3,
            )
            self._state.saturation.total_unique_papers += new_count
            _, level = self.check_saturation()
            self._state.saturation.saturation_level = level if level in (
                "productive", "diminishing", "moderate", "saturated"
            ) else "productive"
        self._save()

    # --- Execution condition ---

    def determine_execution(self) -> dict:
        run_count = len(self._state.runs)
        if run_count == 0:
            return {"action": "execute", "is_first_run": True, "run_count": 0}
        action_str, reason = self.check_saturation()
        if action_str == "skip":
            return {"action": "skip", "reason": reason, "run_count": run_count}
        return {
            "action": "execute",
            "is_first_run": False,
            "run_count": run_count,
            "saturation_action": action_str,
            "saturation_reason": reason,
        }

    def determine_panel_mode(self) -> str:
        run_count = len(self._state.runs)
        if run_count < 5:
            return "full"
        recent = self._state.runs[-2:] if len(self._state.runs) >= 2 else self._state.runs
        recent_rejects = sum(
            1 for r in recent
            for pid, ps in self._state.paper_status.items()
            if ps.panel_verdict == "reject" and ps.run_id == r.run_id
        )
        if recent_rejects > 0:
            return "full"
        return "quick"

    # --- Statistics ---

    def summary(self) -> dict:
        """Summary for this single workflow."""
        statuses: dict[str, int] = {}
        for ps in self._state.paper_status.values():
            statuses[ps.status] = statuses.get(ps.status, 0) + 1
        return {
            "workflow_id": self.wf_id,
            "domain": self._state.domain,
            "runs": len(self._state.runs),
            "papers": len(self._state.paper_status),
            "statuses": statuses,
            "saturation": (
                self._state.saturation.saturation_level
                if self._state.saturation else "unknown"
            ),
        }

    @staticmethod
    def global_summary(root_dir: Path) -> dict:
        """Aggregate summary from registry_index.json."""
        index_path = root_dir / "registry_index.json"
        if index_path.exists():
            idx = RegistryIndex.model_validate(
                json.loads(index_path.read_text())
            )
        else:
            # Scan wf_state.json files
            idx = RegistryIndex(created=_now(), last_updated=_now())
            for wf_dir in sorted(root_dir.iterdir()):
                state_file = wf_dir / "wf_state.json"
                if wf_dir.is_dir() and state_file.exists():
                    ws = WorkflowState.model_validate(
                        json.loads(state_file.read_text())
                    )
                    extracted = sum(
                        1 for ps in ws.paper_status.values()
                        if ps.status == "extracted"
                    )
                    idx.workflows[ws.workflow_id] = WorkflowIndexEntry(
                        domain=ws.domain,
                        run_count=len(ws.runs),
                        paper_count=len(ws.paper_status),
                        extracted_count=extracted,
                    )

        total_papers = sum(w.paper_count for w in idx.workflows.values())
        total_extracted = sum(w.extracted_count for w in idx.workflows.values())
        total_runs = sum(w.run_count for w in idx.workflows.values())
        return {
            "total_workflows": len(idx.workflows),
            "total_papers": total_papers,
            "total_extracted": total_extracted,
            "total_runs": total_runs,
            "workflows": {
                wf_id: {
                    "runs": e.run_count,
                    "papers": e.paper_count,
                    "extracted": e.extracted_count,
                    "domain": e.domain,
                }
                for wf_id, e in idx.workflows.items()
            },
        }


# ========== CLI ==========

def _resolve_args(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """Resolve root_dir and legacy_registry from CLI args."""
    if hasattr(args, "root_dir") and args.root_dir:
        return Path(args.root_dir).expanduser().resolve(), None

    # Legacy fallback: --registry points to single file
    if hasattr(args, "registry") and args.registry:
        reg_path = Path(args.registry).expanduser().resolve()
        root = reg_path.parent
        # Check if it's the old format
        if reg_path.name == "run_registry.json":
            return root, reg_path
        return root, None

    raise ValueError("Either --root-dir or --registry is required")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="run_tracker")
    sub = parser.add_subparsers(dest="command", required=True)

    # Common args helper
    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--wf-id", required=True)
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--root-dir", help="Root directory (v2)")
        g.add_argument("--registry", help="Legacy registry file path")

    p = sub.add_parser("start-run")
    _add_common(p)
    p.add_argument("--domain", default="")

    p = sub.add_parser("add-papers")
    _add_common(p)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--papers", required=True, help="JSON array string")

    p = sub.add_parser("mark-fetched")
    _add_common(p)
    p.add_argument("--paper-id", required=True)

    p = sub.add_parser("mark-extracted")
    _add_common(p)
    p.add_argument("--paper-id", required=True)

    p = sub.add_parser("mark-failed")
    _add_common(p)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--reason", default="")

    p = sub.add_parser("apply-verdict")
    _add_common(p)
    p.add_argument("--paper-id", required=True)
    p.add_argument("--verdict", required=True)
    p.add_argument("--reason", default="")

    p = sub.add_parser("apply-verdicts")
    _add_common(p)
    p.add_argument("--result", required=True)

    p = sub.add_parser("complete-run")
    _add_common(p)
    p.add_argument("--run-id", type=int, required=True)
    p.add_argument("--papers-searched", type=int, default=0)
    p.add_argument("--papers-selected", type=int, default=0)
    p.add_argument("--papers-accepted", type=int, default=0)
    p.add_argument("--new-extractions", type=int, default=0)
    p.add_argument("--new-variants", type=int, default=0)
    p.add_argument("--panels-run", default="")
    p.add_argument("--panel-mode", default="full")
    p.add_argument("--domain", default="")

    p = sub.add_parser("summary")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--root-dir", help="Root directory (v2)")
    g.add_argument("--registry", help="Legacy registry file path")

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    result: Any = None

    if args.command == "summary":
        root_dir, _ = _resolve_args(args)
        result = RunTracker.global_summary(root_dir)
        print(json.dumps(result, ensure_ascii=False))
        return

    root_dir, legacy = _resolve_args(args)
    tracker = RunTracker(root_dir, args.wf_id, legacy_registry=legacy)

    if args.command == "start-run":
        run_id = tracker.start_run(args.domain)
        result = {"run_id": run_id}

    elif args.command == "add-papers":
        papers = json.loads(args.papers)
        added = tracker.add_papers(args.run_id, papers)
        result = {"added": added}

    elif args.command == "mark-fetched":
        tracker.mark_fetched(args.paper_id)
        result = {"status": "fetched", "paper_id": args.paper_id}

    elif args.command == "mark-extracted":
        tracker.mark_extracted(args.paper_id)
        result = {"status": "extracted", "paper_id": args.paper_id}

    elif args.command == "mark-failed":
        tracker.mark_failed(args.paper_id, args.reason)
        result = {"status": "failed", "paper_id": args.paper_id}

    elif args.command == "apply-verdict":
        tracker.apply_verdict(args.paper_id, args.verdict, args.reason)
        result = {"verdict": args.verdict, "paper_id": args.paper_id}

    elif args.command == "apply-verdicts":
        result = tracker.apply_verdicts_from_file(Path(args.result))

    elif args.command == "complete-run":
        panels = [p.strip() for p in args.panels_run.split(",") if p.strip()] if args.panels_run else []
        result = tracker.complete_run(
            args.run_id,
            papers_searched=args.papers_searched,
            papers_selected=args.papers_selected,
            papers_accepted=args.papers_accepted,
            new_extractions=args.new_extractions,
            new_variants=args.new_variants,
            panels_run=panels,
            panel_mode=args.panel_mode,
            domain=getattr(args, "domain", ""),
        )

    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
