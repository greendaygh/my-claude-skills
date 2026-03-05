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


def _extract_verdicts(panel_b: dict) -> dict[str, str]:
    """Extract paper_id -> verdict mapping from various Panel B formats."""
    verdicts = panel_b.get("final_verdicts", panel_b.get("verdicts", {}))
    if not verdicts:
        items = panel_b.get("papers", panel_b.get("reviews", []))
        if items:
            verdicts = {
                p["paper_id"]: p.get("verdict", p.get("panel_b_verdict", "accept"))
                for p in items if "paper_id" in p
            }
    # Normalize dict values to strings
    normalized: dict[str, str] = {}
    for pid, val in verdicts.items():
        if isinstance(val, dict):
            normalized[pid] = val.get("verdict", "accept")
        else:
            normalized[pid] = val
    return normalized


def _cross_validate(
    panel_b: dict,
    paper_list: dict,
    verdicts: dict[str, str],
) -> list[str]:
    """Cross-validate Panel B results against paper_list. Returns warnings."""
    warnings: list[str] = []
    paper_map = {p["paper_id"]: p for p in paper_list.get("papers", [])}
    paper_ids_in_list = set(paper_map.keys())

    # Check all Panel B paper_ids exist in paper_list
    for pid in verdicts:
        if pid not in paper_ids_in_list:
            warnings.append(f"paper_id {pid} in panel B but not in paper_list")

    # Check title match if Panel B includes titles
    items = panel_b.get("papers", panel_b.get("reviews", []))
    if items:
        for item in items:
            pid = item.get("paper_id", "")
            b_title = item.get("title", "")
            if pid in paper_map and b_title:
                list_title = paper_map[pid].get("title", "")
                if list_title:
                    bt = b_title.strip().lower()
                    lt = list_title.strip().lower()
                    # Use shorter title length for prefix comparison (handles truncated API titles)
                    cmp_len = min(len(bt), len(lt), 60)
                    if cmp_len > 10 and bt[:cmp_len] != lt[:cmp_len]:
                        warnings.append(
                            f"{pid} title mismatch: panel_b='{b_title[:40]}...' vs paper_list='{list_title[:40]}...'"
                        )

    # Check coverage: all paper_list papers should have a verdict
    for pid in paper_ids_in_list:
        if pid not in verdicts:
            warnings.append(f"paper_id {pid} in paper_list but missing from panel B")

    return warnings


def apply_verdicts(
    panel_b_path: Path,
    paper_list_path: Path,
    registry_path: Path,
    wf_id: str,
    cross_validate: bool = False,
) -> dict:
    """Apply Panel B verdicts to paper_list and registry.

    Returns a summary dict with counts.
    """
    panel_b = json.loads(panel_b_path.read_text())
    paper_list = json.loads(paper_list_path.read_text())

    verdicts = _extract_verdicts(panel_b)
    if not verdicts:
        return {"ok": True, "accepted": 0, "rejected": 0, "warnings": ["no verdicts found in panel B file"]}

    warnings: list[str] = []
    if cross_validate:
        warnings = _cross_validate(panel_b, paper_list, verdicts)

    paper_ids_in_list = {p["paper_id"] for p in paper_list.get("papers", [])}
    accepted = 0
    rejected = 0

    for paper_id, verdict in verdicts.items():
        if paper_id not in paper_ids_in_list:
            if not cross_validate:
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

    ok = len(warnings) == 0 or not cross_validate
    return {"ok": ok, "accepted": accepted, "rejected": rejected, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Panel B verdicts to paper_list and run_registry"
    )
    parser.add_argument("--wf-id", required=True)
    parser.add_argument("--panel-b-path", type=Path, required=True)
    parser.add_argument("--paper-list-path", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--cross-validate", action="store_true",
                        help="Cross-validate Panel B paper_ids and titles against paper_list")
    args = parser.parse_args()

    result = apply_verdicts(
        panel_b_path=args.panel_b_path,
        paper_list_path=args.paper_list_path,
        registry_path=args.registry,
        wf_id=args.wf_id,
        cross_validate=args.cross_validate,
    )

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
