#!/usr/bin/env python3
"""
map_unit_operations.py — Map common workflow patterns to standardized Unit Operations.

Implements Phase 7: Multi-signal matching of workflow steps to UO catalog.
"""

import json
from pathlib import Path
from datetime import datetime

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"


def load_uo_catalog():
    """Load unit operation catalog from assets."""
    uo_path = ASSETS_DIR / "uo_catalog.json"
    with open(uo_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_common_pattern(wf_dir: str | Path) -> dict:
    """Load common pattern from analysis results."""
    pattern_path = Path(wf_dir) / "03_analysis" / "common_pattern.json"
    with open(pattern_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_cluster_result(wf_dir: str | Path) -> dict:
    """Load cluster result from analysis results."""
    cluster_path = Path(wf_dir) / "03_analysis" / "cluster_result.json"
    with open(cluster_path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_mapping_score(step_info: dict, uo_info: dict) -> dict:
    """
    Compute multi-signal matching score between a workflow step and a UO.

    Signals:
      - equipment/software match (weight 0.35)
      - function match (weight 0.30)
      - input/output type match (weight 0.20)
      - context match (weight 0.15)

    Returns dict with individual scores and combined score.
    Note: In practice, Claude performs semantic matching during skill execution.
    This function provides the scoring framework.
    """
    scores = {
        "equipment": 0.0,
        "function": 0.0,
        "io": 0.0,
        "context": 0.0,
    }

    # Equipment/Software signal
    step_equipment = step_info.get("equipment_keywords", [])
    uo_equipment = uo_info.get("equipment", "").lower() + " " + uo_info.get("software", "").lower()
    for kw in step_equipment:
        if kw.lower() in uo_equipment:
            scores["equipment"] = max(scores["equipment"], 0.9)

    # Function signal
    step_function = step_info.get("function", "").lower()
    uo_desc = uo_info.get("description", "").lower()
    uo_name = uo_info.get("name", "").lower()
    if step_function and (step_function in uo_desc or step_function in uo_name):
        scores["function"] = 0.8

    # Combined weighted score
    combined = (
        0.35 * scores["equipment"]
        + 0.30 * scores["function"]
        + 0.20 * scores["io"]
        + 0.15 * scores["context"]
    )

    return {
        "signals": scores,
        "combined_score": round(combined, 3),
    }


def create_uo_mapping_entry(
    step_function: str,
    uo_id: str,
    uo_name: str,
    instance_label: str,
    mapping_score: float,
    evidence_tag: str,
    supporting_cases: list,
    signals: dict = None,
) -> dict:
    """Create a standardized UO mapping entry."""
    return {
        "step_function": step_function,
        "mapped_uo": {
            "uo_id": uo_id,
            "uo_name": uo_name,
            "instance_label": instance_label,
            "mapping_score": mapping_score,
            "evidence_tag": evidence_tag,
            "supporting_cases": supporting_cases,
            "signals": signals or {},
        },
    }


def create_qc_checkpoint(
    qc_id: str,
    position: str,
    measurement_items: list,
) -> dict:
    """Create a QC checkpoint entry."""
    return {
        "qc_id": qc_id,
        "position": position,
        "measurement_items": measurement_items,
    }


def save_uo_mapping(wf_dir: str | Path, mapping: dict):
    """Save UO mapping to 04_workflow directory."""
    workflow_dir = Path(wf_dir) / "04_workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    filepath = workflow_dir / "uo_mapping.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(mapping, f, indent=2, ensure_ascii=False)

    return filepath


def save_variant_composition(wf_dir: str | Path, variant_id: str,
                             variant_name: str, composition: dict):
    """Save a variant's complete UO composition."""
    workflow_dir = Path(wf_dir) / "04_workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    safe_name = variant_name.lower().replace(" ", "_").replace("/", "_")
    filename = f"variant_{variant_id}_{safe_name}.json"

    filepath = workflow_dir / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(composition, f, indent=2, ensure_ascii=False)

    return filepath


def save_qc_checkpoints(wf_dir: str | Path, checkpoints: list):
    """Save QC checkpoints to 04_workflow directory."""
    workflow_dir = Path(wf_dir) / "04_workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "generated": datetime.now().isoformat(),
        "total_checkpoints": len(checkpoints),
        "checkpoints": checkpoints,
    }

    filepath = workflow_dir / "qc_checkpoints.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return filepath


def build_mapping_framework(wf_dir: str | Path) -> dict:
    """
    Build the UO mapping framework from analysis results.

    This creates the structure; actual semantic mapping is done by Claude
    during skill execution using the UO catalog and case data.
    """
    uo_catalog = load_uo_catalog()
    common_pattern = load_common_pattern(wf_dir)
    cluster_result = load_cluster_result(wf_dir)

    mapping = {
        "generated": datetime.now().isoformat(),
        "workflow_dir": str(wf_dir),
        "uo_catalog_size": len(uo_catalog.get("unit_operations", {})),
        "common_steps": len(common_pattern.get("mandatory_steps", [])),
        "variants": len(cluster_result.get("variants", [])),
        "mappings": [],
        "unmapped_steps": [],
    }

    return mapping


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python map_unit_operations.py <workflow_output_dir>")
        sys.exit(1)

    result = build_mapping_framework(sys.argv[1])
    print(json.dumps(result, indent=2, ensure_ascii=False))
