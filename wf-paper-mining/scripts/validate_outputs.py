"""Batch Pydantic validation for wf-paper-mining outputs.

Validates paper_list_*.json, extraction results, and resource summaries.

CLI:
    python -m scripts.validate_outputs \
        --output-dir ~/dev/wf-mining/WB030 \
        --verbose
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from pydantic import ValidationError

from .models.paper_list import MiningPaperList
from .models.extraction import ExtractionResult
from .models.summary import ResourceSummary, VariantSummary
from .models.state import RunRegistry
from .models.base import DetailedViolation


def _validate_file(
    path: Path,
    model_class: type,
    violations: list[DetailedViolation],
    verbose: bool = False,
) -> bool:
    """Validate a single JSON file against a Pydantic model. Returns True if valid."""
    if not path.exists():
        return True
    try:
        data = json.loads(path.read_text())
        model_class.model_validate(data)
        if verbose:
            print(f"  OK: {path.name}", file=sys.stderr)
        return True
    except ValidationError as e:
        for err in e.errors():
            violations.append(DetailedViolation(
                file=str(path),
                field=".".join(str(loc) for loc in err["loc"]),
                message=err["msg"],
                severity="error",
                value=err.get("input"),
            ))
        if verbose:
            print(f"  FAIL: {path.name} ({len(e.errors())} errors)", file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        violations.append(DetailedViolation(
            file=str(path),
            field="<root>",
            message=f"Invalid JSON: {e}",
            severity="error",
        ))
        return False


def _run_all(output_dir: Path, verbose: bool = False) -> list[DetailedViolation]:
    """Validate all known output files in a workflow output directory."""
    violations: list[DetailedViolation] = []

    papers_dir = output_dir / "01_papers"
    if papers_dir.exists():
        for pl_file in sorted(papers_dir.glob("paper_list_*.json")):
            _validate_file(pl_file, MiningPaperList, violations, verbose)

    extractions_dir = output_dir / "02_extractions"
    if extractions_dir.exists():
        for ext_file in sorted(extractions_dir.glob("*_extraction.json")):
            _validate_file(ext_file, ExtractionResult, violations, verbose)

    summaries_dir = output_dir / "03_summaries"
    if summaries_dir.exists():
        wf_id = output_dir.name
        resource_file = summaries_dir / f"{wf_id}_resource_summary.json"
        _validate_file(resource_file, ResourceSummary, violations, verbose)
        variant_file = summaries_dir / f"{wf_id}_variants.json"
        _validate_file(variant_file, VariantSummary, violations, verbose)

    registry_file = output_dir.parent / "run_registry.json"
    if registry_file.exists():
        _validate_file(registry_file, RunRegistry, violations, verbose)

    return violations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate wf-paper-mining outputs using Pydantic models"
    )
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="Workflow output directory (e.g. ~/dev/wf-mining/WB030)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    violations = _run_all(args.output_dir, verbose=args.verbose)

    result = {
        "total_violations": len(violations),
        "violations": [v.model_dump() for v in violations],
    }

    if violations:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        sys.exit(1)
    else:
        print(json.dumps({"total_violations": 0, "status": "all_valid"}))
        sys.exit(0)


if __name__ == "__main__":
    main()
