"""List papers eligible for re-extraction (have full text file on disk).

CLI:
    python -m scripts.list_reextract_targets \
      --wf-id WB005 --root-dir ~/dev/wf-mining

    python -m scripts.list_reextract_targets \
      --wf-id WB005 --root-dir ~/dev/wf-mining --output targets.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def list_reextract_targets(wf_id: str, root_dir: Path) -> dict:
    """Find all papers that have full text files on disk."""
    state_path = root_dir / wf_id / "wf_state.json"
    if not state_path.exists():
        print(f"Error: wf_state.json not found at {state_path}", file=sys.stderr)
        sys.exit(1)

    state = json.loads(state_path.read_text())
    paper_status = state.get("paper_status", {})
    full_texts_dir = root_dir / wf_id / "01_papers" / "full_texts"

    targets = []
    for paper_id, info in sorted(paper_status.items()):
        txt_path = full_texts_dir / f"{paper_id}.txt"
        if txt_path.exists():
            targets.append({
                "paper_id": paper_id,
                "status": info.get("status", "unknown"),
                "full_text_path": str(txt_path),
            })

    return {
        "workflow_id": wf_id,
        "total_targets": len(targets),
        "targets": targets,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="List papers eligible for re-extraction",
    )
    parser.add_argument("--wf-id", required=True, help="Workflow ID (e.g. WB005)")
    parser.add_argument("--root-dir", required=True, help="Root mining directory")
    parser.add_argument("--output", default=None, help="Output file path (default: stdout)")
    args = parser.parse_args()

    result = list_reextract_targets(args.wf_id, Path(args.root_dir).expanduser())
    output_json = json.dumps(result, indent=2, ensure_ascii=False)

    if args.output:
        out_path = Path(args.output).expanduser()
        out_path.write_text(output_json + "\n")
        print(f"Written to {out_path} ({result['total_targets']} targets)", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
