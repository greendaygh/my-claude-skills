"""Apply Panel B verdicts to paper_list and run_registry in one step.

Replaces the inline Python + per-paper apply-verdict loop in SKILL.md 5-1.
The orchestrator runs this script instead of reading paper_list and panel B files.

CLI:
    python -m scripts.apply_panel_b_verdicts \
        --wf-id WB030 \
        --panel-b-path ~/dev/wf-mining/WB030/reviews/panel_B_runs/run_1_2026-03-04.json \
        --paper-list-path ~/dev/wf-mining/WB030/01_papers/paper_list_1.json \
        --registry ~/dev/wf-mining/run_registry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def apply_verdicts(
    panel_b_path: Path,
    paper_list_path: Path,
    registry_path: Path,
    wf_id: str,
) -> dict:
    """Apply Panel B verdicts to paper_list and registry.

    Returns a summary dict with counts.
    """
    panel_b = json.loads(panel_b_path.read_text())
    paper_list = json.loads(paper_list_path.read_text())

    verdicts = panel_b.get("final_verdicts", panel_b.get("verdicts", {}))
    # Also support papers[].verdict or reviews[].verdict array format
    if not verdicts:
        items = panel_b.get("papers", panel_b.get("reviews", []))
        if items:
            verdicts = {p["paper_id"]: p.get("verdict", "accept") for p in items if "paper_id" in p}
    if not verdicts:
        return {"ok": True, "accepted": 0, "rejected": 0, "warnings": ["no verdicts found in panel B file"]}

    paper_ids_in_list = {p["paper_id"] for p in paper_list.get("papers", [])}
    accepted = 0
    rejected = 0
    warnings = []

    for paper_id, verdict_val in verdicts.items():
        # Support both string ("accept") and dict ({"verdict": "accept"}) formats
        if isinstance(verdict_val, dict):
            verdict = verdict_val.get("verdict", "accept")
        else:
            verdict = verdict_val

        if paper_id not in paper_ids_in_list:
            warnings.append(f"paper_id {paper_id} in panel B but not in paper_list")
            continue

        if verdict == "reject":
            rejected += 1
            for p in paper_list["papers"]:
                if p["paper_id"] == paper_id:
                    p["extraction_status"] = "rejected"
                    break
        else:
            accepted += 1

    # Save updated paper_list
    paper_list_path.write_text(json.dumps(paper_list, indent=2, ensure_ascii=False))

    # Apply verdicts to registry via run_tracker
    if registry_path.exists():
        from .run_tracker import RunTracker
        tracker = RunTracker(registry_path)
        tracker.apply_verdicts_from_file(wf_id, panel_b_path)

    return {"ok": True, "accepted": accepted, "rejected": rejected, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Panel B verdicts to paper_list and run_registry"
    )
    parser.add_argument("--wf-id", required=True)
    parser.add_argument("--panel-b-path", type=Path, required=True)
    parser.add_argument("--paper-list-path", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    args = parser.parse_args()

    result = apply_verdicts(
        panel_b_path=args.panel_b_path,
        paper_list_path=args.paper_list_path,
        registry_path=args.registry,
        wf_id=args.wf_id,
    )

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
