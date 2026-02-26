#!/usr/bin/env python3
"""
collect_case.py — Extract structured case cards from papers for workflow composition.

This script provides utilities for creating, validating, and managing case cards.
Each paper = 1 case card, extracted following the case-collection-guide.md principles.

v1.2.0: Added upgrade_metadata support, get_next_case_number() utility.
"""

import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime


def get_next_case_number(workflow_dir: str | Path) -> int:
    """Get the next case number by counting existing case files in 02_cases/."""
    cases_dir = Path(workflow_dir) / "02_cases"
    if not cases_dir.exists():
        return 1
    existing = sorted(cases_dir.glob("case_C*.json"))
    if not existing:
        return 1
    # Extract highest number from filenames like case_C001.json
    numbers = []
    for f in existing:
        match = re.search(r"C(\d+)", f.stem)
        if match:
            numbers.append(int(match.group(1)))
    return max(numbers) + 1 if numbers else 1


def load_case_template():
    """Load the case card template from assets."""
    template_path = Path(__file__).parent.parent / "assets" / "case_template.json"
    with open(template_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_case_card(
    workflow_id: str,
    case_number: int,
    metadata: dict,
    steps: list,
    flow_diagram: str = "",
    workflow_context: dict = None,
    completeness: dict = None,
    upgrade_metadata: dict = None,
) -> dict:
    """
    Create a case card from extracted paper data.

    Args:
        workflow_id: e.g., "WB030"
        case_number: sequential number (1, 2, 3, ...)
        metadata: paper metadata dict
        steps: list of step dicts
        flow_diagram: string representation of step flow
        workflow_context: modularity context (upstream/downstream workflows, boundary I/O)
        completeness: completeness assessment dict
        upgrade_metadata: (v1.2.0) upgrade-specific metadata — set when case is added during upgrade

    Returns:
        Complete case card dict
    """
    case_id = f"{workflow_id}-C{case_number:03d}"

    default_completeness = {
        "fulltext": False,
        "step_detail": "minimal",
        "equipment_info": "none",
        "qc_criteria": False,
        "supplementary": False,
    }
    if completeness:
        default_completeness.update(completeness)

    default_workflow_context = {
        "service_context": "",
        "paper_workflows": [],
        "upstream_workflow": {"workflow_id": "", "workflow_name": "", "output_to_this": ""},
        "downstream_workflow": {"workflow_id": "", "workflow_name": "", "input_from_this": ""},
        "boundary_inputs": [],
        "boundary_outputs": [],
    }
    if workflow_context:
        default_workflow_context.update(workflow_context)

    card = {
        "case_id": case_id,
        "metadata": {
            "pmid": metadata.get("pmid", ""),
            "doi": metadata.get("doi", ""),
            "authors": metadata.get("authors", ""),
            "year": metadata.get("year"),
            "journal": metadata.get("journal", ""),
            "title": metadata.get("title", ""),
            "purpose": metadata.get("purpose", ""),
            "organism": metadata.get("organism", ""),
            "scale": metadata.get("scale", ""),
            "automation_level": metadata.get("automation_level", ""),
            "core_technique": metadata.get("core_technique", ""),
            "fulltext_access": metadata.get("fulltext_access", False),
            "access_method": metadata.get("access_method", ""),
            "access_tier": metadata.get("access_tier", None),
        },
        "steps": steps,
        "flow_diagram": flow_diagram,
        "workflow_context": default_workflow_context,
        "completeness": default_completeness,
    }

    # v1.2.0: Add upgrade metadata if provided
    if upgrade_metadata:
        card["upgrade_metadata"] = {
            "added_in_upgrade": upgrade_metadata.get("added_in_upgrade", True),
            "upgrade_version": upgrade_metadata.get("upgrade_version", None),
            "upgrade_date": upgrade_metadata.get("upgrade_date", datetime.now().isoformat()),
            "previous_version": upgrade_metadata.get("previous_version", None),
        }

    return card


def validate_step(step: dict) -> list:
    """
    Validate a single step for completeness.
    Returns list of warnings.
    """
    warnings = []
    required_fields = ["step_number", "step_name", "description"]
    optional_fields = ["equipment", "reagents", "conditions", "result_qc", "notes"]

    for field in required_fields:
        if field not in step or not step[field]:
            warnings.append(f"Missing required field: {field}")

    for field in optional_fields:
        if field not in step:
            warnings.append(f"Missing optional field: {field} (should be '[미기재]' if unknown)")

    return warnings


def validate_case_card(card: dict) -> dict:
    """
    Validate a complete case card.
    Returns validation report.
    """
    report = {
        "case_id": card.get("case_id", "UNKNOWN"),
        "valid": True,
        "warnings": [],
        "errors": [],
    }

    # Check metadata
    if not card.get("metadata", {}).get("pmid") and not card.get("metadata", {}).get("doi"):
        report["warnings"].append("No PMID or DOI — paper may be hard to trace")

    if not card.get("metadata", {}).get("core_technique"):
        report["warnings"].append("No core_technique — needed for variant clustering")

    # Check steps
    steps = card.get("steps", [])
    if not steps:
        report["errors"].append("No steps extracted")
        report["valid"] = False
    else:
        for step in steps:
            step_warnings = validate_step(step)
            if step_warnings:
                report["warnings"].extend(
                    [f"Step {step.get('step_number', '?')}: {w}" for w in step_warnings]
                )

    # Check workflow context (modularity)
    wf_ctx = card.get("workflow_context", {})
    if not wf_ctx.get("paper_workflows"):
        report["warnings"].append("No paper_workflows — record all workflows described in the paper")
    if not wf_ctx.get("boundary_inputs") and not wf_ctx.get("boundary_outputs"):
        report["warnings"].append("No boundary I/O — define what enters/exits this workflow for modularity")

    # Check access tracking
    access_method = card.get("metadata", {}).get("access_method")
    if not access_method:
        report["warnings"].append("No access_method — record how paper was accessed")
    access_tier = card.get("metadata", {}).get("access_tier")
    if not access_tier:
        report["warnings"].append("No access_tier — record paper access tier (1-4)")

    # Check for QC steps
    has_qc = any("qc" in str(s.get("result_qc", "")).lower() or
                  "verif" in str(s.get("description", "")).lower() or
                  "confirm" in str(s.get("description", "")).lower()
                  for s in steps)
    if not has_qc:
        report["warnings"].append("No QC steps identified — review paper for implicit QC")

    # Check flow diagram
    if not card.get("flow_diagram"):
        report["warnings"].append("No flow diagram — should show step sequence")

    return report


def save_case_card(card: dict, output_dir: str | Path) -> Path:
    """Save case card to the 02_cases directory."""
    output_dir = Path(output_dir) / "02_cases"
    output_dir.mkdir(parents=True, exist_ok=True)

    case_id = card["case_id"]
    # Extract case number from case_id (e.g., "WB030-C001" -> "C001")
    case_num = case_id.split("-")[-1]
    filename = f"case_{case_num}.json"

    filepath = output_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(card, f, indent=2, ensure_ascii=False)

    return filepath


def generate_case_summary(cases_dir: str | Path, pool_status_filter: str | None = None) -> dict:
    """
    Generate a summary of all case cards in a directory.
    Saves case_summary.json.

    Args:
        cases_dir: workflow output directory (parent of 02_cases/)
        pool_status_filter: if set (e.g., "active"), only include cases whose
            source paper has this pool_status. Requires paper_list.json to exist.
            If None, includes all cases (backward-compatible).
    """
    cases_dir_path = Path(cases_dir)
    actual_cases_dir = cases_dir_path / "02_cases"
    case_files = sorted(actual_cases_dir.glob("case_C*.json"))

    # Build pool_status lookup from paper_list.json if filter is requested
    _paper_pool_status = {}
    if pool_status_filter:
        paper_list_path = cases_dir_path / "01_papers" / "paper_list.json"
        if paper_list_path.exists():
            try:
                with open(paper_list_path, "r", encoding="utf-8") as f:
                    pl = json.load(f)
                for p in pl.get("papers", []):
                    pmid = str(p.get("pmid", "")).strip()
                    doi = str(p.get("doi", "")).strip().lower()
                    status = p.get("pool_status", "active")
                    if pmid:
                        _paper_pool_status[pmid] = status
                    if doi:
                        _paper_pool_status[doi] = status
            except (json.JSONDecodeError, OSError):
                pass

    summary = {
        "total_cases": 0,
        "generated": datetime.now().isoformat(),
        "by_technique": {},
        "by_organism": {},
        "by_scale": {},
        "by_automation": {},
        "by_year": {},
        "completeness_stats": {
            "fulltext_count": 0,
            "detailed_count": 0,
            "qc_criteria_count": 0,
        },
        "access_stats": {
            "tier1_count": 0,
            "tier2_count": 0,
            "tier3_count": 0,
            "tier4_count": 0,
        },
        "modularity": {
            "co_occurring_workflows": {},
            "upstream_workflows": {},
            "downstream_workflows": {},
            "boundary_input_types": {},
            "boundary_output_types": {},
        },
        "cases": [],
    }

    for cf in case_files:
        with open(cf, "r", encoding="utf-8") as f:
            card = json.load(f)

        meta = card.get("metadata", {})

        # Apply pool_status filter if requested
        if pool_status_filter and _paper_pool_status:
            pmid = str(meta.get("pmid", "")).strip()
            doi = str(meta.get("doi", "")).strip().lower()
            paper_status = _paper_pool_status.get(pmid) or _paper_pool_status.get(doi, "active")
            if paper_status != pool_status_filter:
                continue
        comp = card.get("completeness", {})

        case_brief = {
            "case_id": card["case_id"],
            "authors": meta.get("authors", ""),
            "year": meta.get("year"),
            "core_technique": meta.get("core_technique", ""),
            "organism": meta.get("organism", ""),
            "step_count": len(card.get("steps", [])),
        }
        summary["cases"].append(case_brief)

        # Tally distributions
        technique = meta.get("core_technique", "Unknown")
        summary["by_technique"][technique] = summary["by_technique"].get(technique, 0) + 1

        organism = meta.get("organism", "Unknown")
        summary["by_organism"][organism] = summary["by_organism"].get(organism, 0) + 1

        scale = meta.get("scale", "Unknown")
        summary["by_scale"][scale] = summary["by_scale"].get(scale, 0) + 1

        auto = meta.get("automation_level", "Unknown")
        summary["by_automation"][auto] = summary["by_automation"].get(auto, 0) + 1

        year = str(meta.get("year", "Unknown"))
        summary["by_year"][year] = summary["by_year"].get(year, 0) + 1

        # Tally access tier
        tier = meta.get("access_tier")
        if tier:
            tier_key = f"tier{tier}_count"
            summary["access_stats"][tier_key] = (
                summary["access_stats"].get(tier_key, 0) + 1
            )

        if comp.get("fulltext"):
            summary["completeness_stats"]["fulltext_count"] += 1
        if comp.get("step_detail") == "detailed":
            summary["completeness_stats"]["detailed_count"] += 1
        if comp.get("qc_criteria"):
            summary["completeness_stats"]["qc_criteria_count"] += 1

        # Aggregate modularity data
        wf_ctx = card.get("workflow_context", {})
        for wf_id in wf_ctx.get("paper_workflows", []):
            summary["modularity"]["co_occurring_workflows"][wf_id] = (
                summary["modularity"]["co_occurring_workflows"].get(wf_id, 0) + 1
            )

        upstream = wf_ctx.get("upstream_workflow", {})
        if upstream.get("workflow_id"):
            uid = upstream["workflow_id"]
            summary["modularity"]["upstream_workflows"][uid] = (
                summary["modularity"]["upstream_workflows"].get(uid, 0) + 1
            )

        downstream = wf_ctx.get("downstream_workflow", {})
        if downstream.get("workflow_id"):
            did = downstream["workflow_id"]
            summary["modularity"]["downstream_workflows"][did] = (
                summary["modularity"]["downstream_workflows"].get(did, 0) + 1
            )

        for bi in wf_ctx.get("boundary_inputs", []):
            summary["modularity"]["boundary_input_types"][bi] = (
                summary["modularity"]["boundary_input_types"].get(bi, 0) + 1
            )

        for bo in wf_ctx.get("boundary_outputs", []):
            summary["modularity"]["boundary_output_types"][bo] = (
                summary["modularity"]["boundary_output_types"].get(bo, 0) + 1
            )

    summary["total_cases"] = len(summary["cases"])

    summary_path = actual_cases_dir / "case_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    return summary


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python collect_case.py <workflow_output_dir>")
        print("  Generates case_summary.json from existing case cards.")
        sys.exit(1)

    wf_dir = sys.argv[1]
    summary = generate_case_summary(wf_dir)
    print(f"Summary generated: {summary['total_cases']} cases")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
