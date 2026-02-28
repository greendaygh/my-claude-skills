#!/usr/bin/env python3
"""
batch_tracker.py — Track batch workflow composition state for resume capability.

Maintains a lightweight state file (batch_state.json) that records which
workflows have been completed, failed, or are still pending. Supports
resuming from the last failure point.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


_DEFAULT_STATE_FILE = "batch_state.json"


class BatchTracker:
    """Track progress of batch workflow composition runs."""

    def __init__(self, output_dir: str | Path, workflow_ids: list[str],
                 state_file: str = _DEFAULT_STATE_FILE):
        self.output_dir = Path(output_dir)
        self.state_path = self.output_dir / state_file
        self.state: dict = {}
        self._load_or_create(workflow_ids)

    def _load_or_create(self, workflow_ids: list[str]):
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                self.state = json.load(f)
        else:
            self.state = {
                "batch_id": f"batch_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                "started": datetime.now(timezone.utc).isoformat(),
                "total": len(workflow_ids),
                "completed": [],
                "failed": {},
                "skipped": [],
                "pending": list(workflow_ids),
                "current": None,
            }
            self._save()

    def _save(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2, ensure_ascii=False)

    def get_pending(self) -> list[str]:
        """Return list of workflows not yet completed or failed."""
        return list(self.state.get("pending", []))

    def get_resumable(self) -> list[str]:
        """Return pending + failed workflows for resume mode."""
        pending = self.state.get("pending", [])
        failed_ids = list(self.state.get("failed", {}).keys())
        return failed_ids + pending

    def start(self, workflow_id: str):
        """Mark a workflow as currently running."""
        self.state["current"] = workflow_id
        if workflow_id in self.state["pending"]:
            self.state["pending"].remove(workflow_id)
        self.state.get("failed", {}).pop(workflow_id, None)
        self._save()
        print(f"[BATCH] Started: {workflow_id} "
              f"({self._progress_str()})", file=sys.stderr, flush=True)

    def complete(self, workflow_id: str):
        """Mark a workflow as successfully completed."""
        if workflow_id not in self.state["completed"]:
            self.state["completed"].append(workflow_id)
        self.state["current"] = None
        self._save()
        print(f"[BATCH] Completed: {workflow_id} "
              f"({self._progress_str()})", file=sys.stderr, flush=True)

    def fail(self, workflow_id: str, reason: str):
        """Mark a workflow as failed with a reason."""
        self.state["failed"][workflow_id] = {
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.state["current"] = None
        self._save()
        print(f"[BATCH] Failed: {workflow_id} — {reason} "
              f"({self._progress_str()})", file=sys.stderr, flush=True)

    def skip(self, workflow_id: str, reason: str = ""):
        """Mark a workflow as intentionally skipped."""
        if workflow_id not in self.state.get("skipped", []):
            self.state.setdefault("skipped", []).append(workflow_id)
        if workflow_id in self.state["pending"]:
            self.state["pending"].remove(workflow_id)
        self.state["current"] = None
        self._save()

    def finish(self):
        """Finalize batch run, record end time."""
        self.state["finished"] = datetime.now(timezone.utc).isoformat()
        self.state["current"] = None
        self._save()
        c = len(self.state["completed"])
        f = len(self.state["failed"])
        s = len(self.state.get("skipped", []))
        t = self.state["total"]
        print(f"[BATCH] Finished: {c}/{t} completed, {f} failed, {s} skipped",
              file=sys.stderr, flush=True)

    def summary(self) -> dict:
        """Return a summary of the current batch state."""
        return {
            "batch_id": self.state.get("batch_id", ""),
            "total": self.state.get("total", 0),
            "completed": len(self.state.get("completed", [])),
            "failed": len(self.state.get("failed", {})),
            "skipped": len(self.state.get("skipped", [])),
            "pending": len(self.state.get("pending", [])),
            "current": self.state.get("current"),
        }

    def _progress_str(self) -> str:
        s = self.summary()
        return f"{s['completed']}/{s['total']} done, {s['failed']} failed"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python batch_tracker.py <output_dir> [--resume]")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    state_path = output_dir / _DEFAULT_STATE_FILE

    if state_path.exists():
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        print(json.dumps(state, indent=2, ensure_ascii=False))
    else:
        print(f"No batch state found at {state_path}")
