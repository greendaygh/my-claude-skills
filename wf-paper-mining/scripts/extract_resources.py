"""Extraction save/validate/summary for wf-paper-mining subagent use."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .models.extraction import ExtractionResult


def _cmd_save(paper_id: str, workflow_id: str, output_dir: Path) -> None:
    data = json.load(sys.stdin)
    ExtractionResult.model_validate(data)
    out_path = output_dir / f"{paper_id}_extraction.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out_path.parent, prefix=".tmp_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, out_path)
    except Exception:
        os.unlink(tmp)
        raise
    print(json.dumps({"saved": paper_id, "valid": True}))


def _cmd_validate(extraction_path: Path) -> None:
    data = json.loads(extraction_path.read_text(encoding="utf-8"))
    try:
        ExtractionResult.model_validate(data)
        print(json.dumps({"valid": True, "errors": []}))
    except ValidationError as e:
        print(json.dumps({"valid": False, "errors": [str(x) for x in e.errors()]}))
    except Exception as e:
        print(json.dumps({"valid": False, "errors": [str(e)]}))


def _cmd_summary(input_dir: Path, workflow_id: str) -> None:
    counts: dict[str, int] = {
        "workflows": 0,
        "hardware_uos": 0,
        "software_uos": 0,
        "equipment": 0,
        "consumables": 0,
        "reagents": 0,
        "samples": 0,
        "uo_connections": 0,
        "qc_checkpoints": 0,
        "new_uo_candidates": 0,
        "papers": 0,
    }
    for p in sorted(input_dir.glob("*_extraction.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            ExtractionResult.model_validate(data)
            counts["papers"] += 1
            counts["workflows"] += len(data.get("workflows", []))
            counts["hardware_uos"] += len(data.get("hardware_uos", []))
            counts["software_uos"] += len(data.get("software_uos", []))
            counts["equipment"] += len(data.get("equipment", []))
            counts["consumables"] += len(data.get("consumables", []))
            counts["reagents"] += len(data.get("reagents", []))
            counts["samples"] += len(data.get("samples", []))
            counts["uo_connections"] += len(data.get("uo_connections", []))
            counts["qc_checkpoints"] += len(data.get("qc_checkpoints", []))
            counts["new_uo_candidates"] += len(data.get("new_uo_candidates", []))
        except Exception:
            pass
    summary = {"workflow_id": workflow_id, "counts": counts}
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Extraction save/validate/summary")
    subparsers = parser.add_subparsers(dest="command", required=True)

    save_p = subparsers.add_parser("save")
    save_p.add_argument("--paper-id", required=True)
    save_p.add_argument("--workflow-id", required=True)
    save_p.add_argument("--output", type=Path, required=True)

    val_p = subparsers.add_parser("validate")
    val_p.add_argument("--extraction", type=Path, required=True)

    sum_p = subparsers.add_parser("summary")
    sum_p.add_argument("--input", type=Path, required=True)
    sum_p.add_argument("--workflow-id", required=True)

    args = parser.parse_args()

    if args.command == "save":
        _cmd_save(args.paper_id, args.workflow_id, args.output)
    elif args.command == "validate":
        _cmd_validate(args.extraction)
    elif args.command == "summary":
        _cmd_summary(args.input, args.workflow_id)


if __name__ == "__main__":
    main()
