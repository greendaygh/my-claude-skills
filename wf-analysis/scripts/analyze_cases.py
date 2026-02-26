#!/usr/bin/env python3
"""
analyze_cases.py — Compare and analyze collected case cards to derive common patterns and variants.

Implements Phase 6: Step alignment, common step identification, variant derivation,
and parameter range extraction.

v1.10.2: Simplified — removed execution_logger, removed BATCH_SIZE complexity,
integrated variant identification logic directly (primary axis: core_technique,
secondary: scale/automation/organism, min 2 cases per variant).
"""

import json
import re
import os
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median, mode, StatisticsError


def load_cases(wf_dir: str | Path) -> list:
    """Load case cards from 02_cases directory.

    Args:
        wf_dir: workflow output directory path

    Returns:
        List of case card dicts.
    """
    cases_dir = Path(wf_dir) / "02_cases"
    case_files = sorted(cases_dir.glob("case_C*.json"))

    cases = []
    for cf in case_files:
        with open(cf, "r", encoding="utf-8") as f:
            cases.append(json.load(f))
    return cases


def align_steps(cases: list) -> dict:
    """
    Phase 6.1: Align steps across all cases by functional equivalence.

    Returns step_alignment structure with aligned positions.
    """
    alignment = {
        "generated": datetime.now().isoformat(),
        "total_cases": len(cases),
        "aligned_positions": [],
    }

    # Collect all step names/functions across cases
    all_steps_by_case = {}
    for case in cases:
        case_id = case["case_id"]
        all_steps_by_case[case_id] = [
            {
                "step_number": s["step_number"],
                "step_name": s["step_name"],
                "description": s.get("description", ""),
            }
            for s in case.get("steps", [])
        ]

    # Find maximum step count for alignment width
    max_steps = max(len(steps) for steps in all_steps_by_case.values()) if all_steps_by_case else 0

    # Create positional alignment (simple sequential alignment)
    # In practice, Claude would do semantic alignment during skill execution
    for pos in range(1, max_steps + 1):
        position_data = {
            "aligned_position": pos,
            "function": "",  # To be filled by semantic analysis
            "cases": {},
        }
        for case_id, steps in all_steps_by_case.items():
            if pos <= len(steps):
                step = steps[pos - 1]
                position_data["cases"][case_id] = {
                    "step_number": step["step_number"],
                    "step_name": step["step_name"],
                }
            else:
                position_data["cases"][case_id] = None

        alignment["aligned_positions"].append(position_data)

    return alignment


def identify_common_steps(alignment: dict, threshold_mandatory: float = 0.6) -> dict:
    """
    Phase 6.2: Identify common, conditional, and branch steps.

    Args:
        alignment: output from align_steps
        threshold_mandatory: fraction of cases needed for "mandatory" (default 60%)
    """
    total_cases = alignment["total_cases"]
    common_pattern = {
        "generated": datetime.now().isoformat(),
        "total_cases": total_cases,
        "threshold_mandatory": threshold_mandatory,
        "mandatory_steps": [],
        "conditional_steps": [],
        "branch_points": [],
        "optional_steps": [],
    }

    for pos_data in alignment.get("aligned_positions", []):
        cases_present = sum(1 for v in pos_data["cases"].values() if v is not None)
        presence_ratio = cases_present / total_cases if total_cases > 0 else 0

        # Collect unique step names at this position
        step_names = [
            v["step_name"] for v in pos_data["cases"].values() if v is not None
        ]
        name_counts = Counter(step_names)

        step_info = {
            "position": pos_data["aligned_position"],
            "function": pos_data.get("function", ""),
            "presence_ratio": round(presence_ratio, 2),
            "cases_present": cases_present,
            "step_name_variants": dict(name_counts),
        }

        if presence_ratio >= threshold_mandatory:
            if len(name_counts) <= 2:
                common_pattern["mandatory_steps"].append(step_info)
            else:
                # Multiple different techniques at this position = branch point
                step_info["branches"] = list(name_counts.keys())
                common_pattern["branch_points"].append(step_info)
        elif presence_ratio >= 0.3:
            common_pattern["conditional_steps"].append(step_info)
        else:
            common_pattern["optional_steps"].append(step_info)

    return common_pattern


def cluster_cases(cases: list) -> dict:
    """
    Phase 6.3: Cluster cases into variants based on shared characteristics.

    Variant identification logic (integrated from references/variant-identification.md):
    - Primary axis: core_technique (e.g., Gibson vs Golden Gate vs restriction)
    - Secondary axes: scale (tube vs plate), automation_level (manual vs automated), organism
    - Each cluster = variant, minimum 2 cases per variant
    """
    cluster_result = {
        "generated": datetime.now().isoformat(),
        "clustering_method": "technique-first hierarchical",
        "primary_axis": "core_technique",
        "secondary_axes": ["scale", "automation_level", "organism"],
        "total_cases": len(cases),
        "variants": [],
    }

    # Group by core technique (primary axis)
    by_technique = defaultdict(list)
    for case in cases:
        technique = case.get("metadata", {}).get("core_technique", "Unknown")
        by_technique[technique].append(case["case_id"])

    variant_num = 1
    for technique, case_ids in sorted(by_technique.items()):
        # Only create variant if we have at least 2 cases (minimum cluster size)
        if len(case_ids) < 2:
            print(f"Skipping variant for {technique}: only {len(case_ids)} case(s), minimum is 2")
            continue

        # Get representative metadata
        technique_cases = [c for c in cases if c["case_id"] in case_ids]
        scales = set(c.get("metadata", {}).get("scale", "Unknown") for c in technique_cases)
        auto_levels = set(c.get("metadata", {}).get("automation_level", "Unknown") for c in technique_cases)
        organisms = set(c.get("metadata", {}).get("organism", "Unknown") for c in technique_cases)

        variant = {
            "variant_id": f"V{variant_num}",
            "name": technique,
            "qualifier": ", ".join(sorted(auto_levels - {"Unknown", ""})),
            "case_ids": sorted(case_ids),
            "case_count": len(case_ids),
            "defining_features": {
                "core_technique": technique,
                "scales": sorted(scales - {"Unknown", ""}),
                "automation_levels": sorted(auto_levels - {"Unknown", ""}),
                "organisms": sorted(organisms - {"Unknown", ""}),
            },
        }
        cluster_result["variants"].append(variant)
        variant_num += 1

    print(f"Created {len(cluster_result['variants'])} variants from {len(cases)} cases")
    return cluster_result


def _extract_numeric_values(text: str) -> list[float]:
    """Extract numeric values (int and float) from a condition string."""
    # Match integers and floats, including negative numbers
    matches = re.findall(r"-?\d+\.?\d*", text)
    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            pass
    return values


def _safe_mode(values: list[float]) -> float | None:
    """Compute the mode of a list, returning None if no unique mode exists."""
    if not values:
        return None
    try:
        return mode(values)
    except StatisticsError:
        # No unique mode — fall back to the most common value via Counter
        counts = Counter(values)
        most_common = counts.most_common(1)
        return most_common[0][0] if most_common else None


def extract_parameter_ranges(cases: list, alignment: dict) -> dict:
    """
    Phase 6.5: Extract parameter ranges from cases for each aligned step.

    Aggregates numeric statistics (min, max, mode, median, count) across all
    cases per step rather than storing raw condition strings per case. Each
    entry also stores the list of contributing case_ids for traceability.
    """
    parameter_ranges = {
        "generated": datetime.now().isoformat(),
        "parameters": [],
    }

    # Accumulate conditions per (step_number, step_name) across all cases
    step_data: dict[tuple[int, str], dict] = defaultdict(lambda: {
        "case_ids": [],
        "numeric_values": [],
        "core_techniques": [],
    })

    for case in cases:
        case_id = case["case_id"]
        core_technique = case.get("metadata", {}).get("core_technique", "")
        for step in case.get("steps", []):
            conditions = step.get("conditions", "")
            if conditions and conditions != "[미기재]":
                key = (step["step_number"], step["step_name"])
                entry = step_data[key]
                entry["case_ids"].append(case_id)
                entry["core_techniques"].append(core_technique)
                entry["numeric_values"].extend(_extract_numeric_values(conditions))

    # Build aggregated parameter entries sorted by step number
    for (step_number, step_name), data in sorted(step_data.items(), key=lambda x: x[0]):
        nums = data["numeric_values"]
        techniques = list(set(data["core_techniques"]))

        stats: dict = {
            "count": len(nums),
        }
        if nums:
            stats["min"] = min(nums)
            stats["max"] = max(nums)
            stats["median"] = median(nums)
            stats["mode"] = _safe_mode(nums)
        else:
            stats["min"] = None
            stats["max"] = None
            stats["median"] = None
            stats["mode"] = None

        param_entry = {
            "step_number": step_number,
            "step_name": step_name,
            "core_techniques": techniques,
            "case_ids": sorted(set(data["case_ids"])),
            "aggregated_stats": stats,
        }
        parameter_ranges["parameters"].append(param_entry)

    return parameter_ranges


def save_analysis_results(wf_dir: str | Path, alignment: dict, common_pattern: dict,
                          cluster_result: dict, parameter_ranges: dict):
    """Save all analysis outputs to 03_analysis directory."""
    analysis_dir = Path(wf_dir) / "03_analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    outputs = {
        "step_alignment.json": alignment,
        "common_pattern.json": common_pattern,
        "cluster_result.json": cluster_result,
        "parameter_ranges.json": parameter_ranges,
    }

    for filename, data in outputs.items():
        filepath = analysis_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    return {k: str(analysis_dir / k) for k in outputs}


def run_full_analysis(wf_dir: str | Path) -> dict:
    """
    Run the complete case analysis pipeline (Phase 6).

    Args:
        wf_dir: workflow output directory path

    Returns:
        Summary of analysis results
    """
    print("Loading case cards...")
    cases = load_cases(wf_dir)
    if not cases:
        return {"error": "No case cards found", "path": str(wf_dir)}

    print(f"Analyzing {len(cases)} cases...")

    print("Phase 6.1: Aligning steps across cases...")
    alignment = align_steps(cases)

    print("Phase 6.2: Identifying common steps...")
    common_pattern = identify_common_steps(alignment, threshold_mandatory=0.6)

    print("Phase 6.3: Clustering cases into variants...")
    cluster_result = cluster_cases(cases)

    print("Phase 6.5: Extracting parameter ranges...")
    parameter_ranges = extract_parameter_ranges(cases, alignment)

    print("Saving analysis results...")
    saved = save_analysis_results(wf_dir, alignment, common_pattern,
                                  cluster_result, parameter_ranges)

    print("Analysis complete!")
    return {
        "total_cases": len(cases),
        "aligned_positions": len(alignment["aligned_positions"]),
        "mandatory_steps": len(common_pattern["mandatory_steps"]),
        "branch_points": len(common_pattern["branch_points"]),
        "variants": len(cluster_result["variants"]),
        "parameters_extracted": len(parameter_ranges["parameters"]),
        "output_files": saved,
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python analyze_cases.py <workflow_output_dir>")
        sys.exit(1)

    result = run_full_analysis(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
