"""Apply Panel B verdicts to paper_list and wf_state in one step.

Replaces the inline Python + per-paper apply-verdict loop in SKILL.md 5-1.
The orchestrator runs this script instead of reading paper_list and panel B files.

CLI:
    python -m scripts.apply_panel_b_verdicts \
        --wf-id WB030 \
        --panel-b-path ~/dev/wf-mining/WB030/reviews/panel_B_runs/run_1_2026-03-04.json \
        --paper-list-path ~/dev/wf-mining/WB030/01_papers/paper_list_1.json \
        --root-dir ~/dev/wf-mining
"""
from __future__ import annotations

import argparse
import json
import sys
from difflib import SequenceMatcher
from pathlib import Path

# Title similarity threshold: LLM subagents may auto-correct typos in titles,
# so we use fuzzy matching instead of exact prefix comparison.
_TITLE_SIMILARITY_THRESHOLD = 0.85


def _extract_verdicts(panel_b: dict) -> dict[str, str]:
    """Extract paper_id -> verdict mapping from various Panel B formats."""
    verdicts = panel_b.get("final_verdicts", panel_b.get("verdicts", {}))
    if not verdicts:
        # Try list-based formats: papers, reviews, results
        items = panel_b.get("papers", panel_b.get("reviews", panel_b.get("results", [])))
        if items:
            verdicts = {}
            for p in items:
                if "paper_id" not in p:
                    continue
                # Check multiple possible verdict locations
                v = p.get("verdict") or p.get("panel_b_verdict") or p.get("final_verdict")
                if not v:
                    # Check nested round_2.final_verdict (subagent variant format)
                    r2 = p.get("round_2", p.get("round_2_vote", {}))
                    if isinstance(r2, dict):
                        v = r2.get("final_verdict") or r2.get("verdict")
                verdicts[p["paper_id"]] = v or "accept"
    # Try summary.accepted_ids / rejected_ids format
    if not verdicts:
        summary = panel_b.get("summary", {})
        accepted_ids = summary.get("accepted_ids", [])
        rejected_ids = summary.get("rejected_ids", [])
        if accepted_ids or rejected_ids:
            verdicts = {}
            for pid in accepted_ids:
                verdicts[pid] = "accept"
            for pid in rejected_ids:
                verdicts[pid] = "reject"
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

    # Check title match if Panel B includes titles (fuzzy: LLM may auto-correct typos)
    items = panel_b.get("papers", panel_b.get("reviews", []))
    if items:
        for item in items:
            pid = item.get("paper_id", "")
            b_title = item.get("title", "")
            if pid in paper_map and b_title:
                list_title = paper_map[pid].get("title", "")
                if list_title:
                    ratio = SequenceMatcher(
                        None, b_title.strip().lower(), list_title.strip().lower()
                    ).ratio()
                    if ratio < _TITLE_SIMILARITY_THRESHOLD:
                        warnings.append(
                            f"{pid} title mismatch (similarity={ratio:.2f}): "
                            f"panel_b='{b_title[:40]}...' vs paper_list='{list_title[:40]}...'"
                        )

    # Check coverage: all paper_list papers should have a verdict
    for pid in paper_ids_in_list:
        if pid not in verdicts:
            warnings.append(f"paper_id {pid} in paper_list but missing from panel B")

    return warnings


def apply_verdicts(
    panel_b_path: Path,
    paper_list_path: Path,
    root_dir: Path,
    wf_id: str,
    cross_validate: bool = False,
) -> dict:
    """Apply Panel B verdicts to paper_list and wf_state.

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
                    p["panel_b_verdict"] = "reject"
                    break
        else:
            accepted += 1
            for p in paper_list["papers"]:
                if p["paper_id"] == paper_id:
                    p["panel_b_verdict"] = "accept"
                    break

    # Save updated paper_list
    paper_list_path.write_text(json.dumps(paper_list, indent=2, ensure_ascii=False))

    # Apply verdicts to wf_state via run_tracker
    if root_dir.exists():
        from .run_tracker import RunTracker
        tracker = RunTracker(root_dir, wf_id)
        tracker.apply_verdicts_from_file(panel_b_path)

    # Only paper_id coverage issues are hard failures; title mismatches are soft warnings
    hard_failures = [w for w in warnings if "title mismatch" not in w]
    ok = len(hard_failures) == 0
    return {"ok": ok, "accepted": accepted, "rejected": rejected, "warnings": warnings}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply Panel B verdicts to paper_list and run_registry"
    )
    parser.add_argument("--wf-id", required=True)
    parser.add_argument("--panel-b-path", type=Path, required=True)
    parser.add_argument("--paper-list-path", type=Path, required=True)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--root-dir", type=Path, help="Root directory (v2)")
    g.add_argument("--registry", type=Path, help="Legacy registry file path")
    parser.add_argument("--cross-validate", action="store_true",
                        help="Cross-validate Panel B paper_ids and titles against paper_list")
    args = parser.parse_args()

    root = args.root_dir or args.registry.expanduser().resolve().parent

    result = apply_verdicts(
        panel_b_path=args.panel_b_path,
        paper_list_path=args.paper_list_path,
        root_dir=root,
        wf_id=args.wf_id,
        cross_validate=args.cross_validate,
    )

    print(json.dumps(result, ensure_ascii=False))
    sys.exit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
