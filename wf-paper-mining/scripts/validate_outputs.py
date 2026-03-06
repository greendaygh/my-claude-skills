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


def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return doi.strip().lower().replace("https://doi.org/", "")


def _cross_validate_paper_lists(
    papers_dir: Path,
    violations: list[DetailedViolation],
) -> None:
    """Cross-validate paper_list files: DOI overlap, paper_id overlap."""
    pl_files = sorted(papers_dir.glob("paper_list_*.json"))
    if len(pl_files) < 2:
        return

    # 4-A: DOI overlap across files
    doi_to_files: dict[str, list[str]] = {}
    for pl_file in pl_files:
        try:
            data = json.loads(pl_file.read_text())
            for p in data.get("papers", []):
                doi = p.get("doi", "")
                if doi:
                    norm = _norm_doi(doi)
                    doi_to_files.setdefault(norm, []).append(pl_file.name)
        except Exception:
            continue

    for norm_doi, files in doi_to_files.items():
        if len(files) > 1:
            violations.append(DetailedViolation(
                file="cross-file",
                field="doi_overlap",
                message=f"DOI {norm_doi} appears in multiple paper_lists: {files}",
                severity="error",
                value=norm_doi,
            ))

    # 4-B: paper_id overlap across files
    pid_to_info: dict[str, list[tuple[str, str, str]]] = {}
    for pl_file in pl_files:
        try:
            data = json.loads(pl_file.read_text())
            for p in data.get("papers", []):
                pid = p.get("paper_id", "")
                if pid:
                    doi = p.get("doi", "")
                    pmid = p.get("pmid", "")
                    pid_to_info.setdefault(pid, []).append(
                        (pl_file.name, doi or "", pmid or ""),
                    )
        except Exception:
            continue

    for pid, infos in pid_to_info.items():
        if len(infos) > 1:
            files = [x[0] for x in infos]
            dois = [x[1] for x in infos]
            pmids = [x[2] for x in infos]
            msg = (
                f"paper_id {pid} in multiple files with different DOI/PMID: {files}"
                if len(set(dois)) > 1 or len(set(pmids)) > 1
                else f"paper_id {pid} appears in multiple paper_lists: {files}"
            )
            violations.append(DetailedViolation(
                file="cross-file",
                field="paper_id_overlap",
                message=msg,
                severity="error",
                value=pid,
            ))


def _run_quick(output_dir: Path, run_id: str) -> dict:
    """Quick post-search validation: file exists, paper_id format, DOI overlap."""
    papers_dir = output_dir / "01_papers"
    pl_path = papers_dir / f"paper_list_{run_id}.json"

    if not pl_path.exists():
        return {"ok": False, "reason": f"paper_list_{run_id}.json not found"}

    try:
        data = json.loads(pl_path.read_text())
    except json.JSONDecodeError as e:
        return {"ok": False, "reason": f"invalid JSON: {e}"}

    papers = data.get("papers", [])
    if not papers:
        return {"ok": False, "reason": "no papers in paper_list"}

    # Check paper_id format
    import re
    bad_ids = [p["paper_id"] for p in papers if not re.match(r"^[A-Z]{2}\d{3}_P\d{3,}$", p.get("paper_id", ""))]
    if bad_ids:
        return {"ok": False, "reason": f"invalid paper_id format: {bad_ids}"}

    # Check DOI overlap with other paper_lists
    current_dois = {_norm_doi(p.get("doi", "")) for p in papers} - {""}
    other_pl_files = [f for f in sorted(papers_dir.glob("paper_list_*.json")) if f != pl_path]
    for other_file in other_pl_files:
        try:
            other_data = json.loads(other_file.read_text())
            other_dois = {_norm_doi(p.get("doi", "")) for p in other_data.get("papers", [])} - {""}
            overlap = current_dois & other_dois
            if overlap:
                return {"ok": False, "reason": f"DOI overlap with {other_file.name}: {list(overlap)[:3]}"}
        except Exception:
            continue

    return {"ok": True}


def _run_all(output_dir: Path, verbose: bool = False) -> list[DetailedViolation]:
    """Validate all known output files in a workflow output directory."""
    violations: list[DetailedViolation] = []

    papers_dir = output_dir / "01_papers"
    if papers_dir.exists():
        for pl_file in sorted(papers_dir.glob("paper_list_*.json")):
            _validate_file(pl_file, MiningPaperList, violations, verbose)
        _cross_validate_paper_lists(papers_dir, violations)

    extractions_dir = output_dir / "02_extractions"
    if extractions_dir.exists():
        for ext_file in sorted(extractions_dir.glob("*.json")):
            _validate_file(ext_file, ExtractionResult, violations, verbose)

    summaries_dir = output_dir / "03_summaries"
    if summaries_dir.exists():
        wf_id = output_dir.name
        resource_file = summaries_dir / f"{wf_id}_resource_summary.json"
        if not resource_file.exists():
            resource_file = summaries_dir / "resource_summary.json"
        _validate_file(resource_file, ResourceSummary, violations, verbose)
        variant_file = summaries_dir / f"{wf_id}_variants.json"
        if not variant_file.exists():
            variant_file = summaries_dir / "variant_summary.json"
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
    parser.add_argument("--quick", action="store_true",
                        help="Quick post-search validation (file exists, paper_id format, DOI overlap)")
    parser.add_argument("--run-id", type=str,
                        help="Run ID for --quick mode (e.g. 1, 2)")
    args = parser.parse_args()

    if args.quick:
        if not args.run_id:
            print(json.dumps({"ok": False, "reason": "--run-id required with --quick"}))
            sys.exit(1)
        result = _run_quick(args.output_dir, args.run_id)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0 if result["ok"] else 1)

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
