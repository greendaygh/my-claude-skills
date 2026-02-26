#!/usr/bin/env python3
"""
populate_components.py — Rule-engine based 7-component population for workflow-composer v2.0.

Replaces Phase 8 LLM free-form component writing with deterministic aggregation.
Categorical fields use majority_vote, numeric fields use range_with_median.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from collections import Counter, defaultdict
from statistics import median, mode, StatisticsError

_SCRIPTS_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPTS_DIR.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from scripts import __version__

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"

# The 7 standard components per UO type
# HW UOs: input, output, equipment, consumables, material_and_method, result, discussion
# SW UOs: input, output, parameters, environment, method, result, discussion
COMPONENT_NAMES_HW = [
    "input",
    "output",
    "equipment",
    "consumables",
    "material_and_method",
    "result",
    "discussion",
]

COMPONENT_NAMES_SW = [
    "input",
    "output",
    "parameters",
    "environment",
    "method",
    "result",
    "discussion",
]

# Legacy alias for backward compatibility
COMPONENT_NAMES = COMPONENT_NAMES_HW


def load_v2_config() -> dict:
    with open(ASSETS_DIR / "v2_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_numeric_values(text: str) -> list[float]:
    """Extract numeric values from a text string."""
    matches = re.findall(r"-?\d+\.?\d*", str(text))
    values = []
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            pass
    return values


def _safe_mode(values: list) -> object:
    """Compute mode, returning most common value on tie."""
    if not values:
        return None
    try:
        return mode(values)
    except StatisticsError:
        counts = Counter(values)
        most_common = counts.most_common(1)
        return most_common[0][0] if most_common else None


def majority_vote(values: list, min_refs: int = 2) -> dict:
    """Aggregate categorical values using majority vote.

    Args:
        values: list of (value, case_id) tuples
        min_refs: minimum case references for consensus

    Returns:
        {"value": str, "evidence_tag": str, "case_refs": list, "confidence": float}
    """
    if not values:
        return {"value": "[미기재]", "evidence_tag": "catalog-default", "case_refs": [], "confidence": 0.0}

    # Count occurrences
    val_counts = Counter()
    val_cases = defaultdict(list)
    for val, case_id in values:
        if val and val != "[미기재]":
            val_counts[val] += 1
            val_cases[val].append(case_id)

    if not val_counts:
        all_case_ids = list(set(cid for _, cid in values))
        return {"value": "[미기재]", "evidence_tag": "catalog-default", "case_refs": all_case_ids, "confidence": 0.0}

    # Find majority
    total = sum(val_counts.values())
    winner, winner_count = val_counts.most_common(1)[0]
    confidence = round(winner_count / total, 2) if total > 0 else 0.0
    case_refs = sorted(set(val_cases[winner]))

    if len(case_refs) >= min_refs:
        evidence_tag = "literature-consensus" if confidence >= 0.6 else "literature-direct"
    else:
        evidence_tag = "expert-inference"

    return {
        "value": winner,
        "evidence_tag": evidence_tag,
        "case_refs": case_refs,
        "confidence": confidence,
        "alternatives": [
            {"value": v, "count": c, "case_refs": sorted(set(val_cases[v]))}
            for v, c in val_counts.most_common()[1:3]  # Top 2 alternatives
        ] if len(val_counts) > 1 else [],
    }


def range_with_median(values: list, min_refs: int = 2) -> dict:
    """Aggregate numeric values as range with median.

    Args:
        values: list of (numeric_value, case_id, unit_str) tuples
        min_refs: minimum case references for consensus

    Returns:
        {"min": float, "max": float, "median": float, "mode": float,
         "unit": str, "case_refs": list, "evidence_tag": str, "count": int}
    """
    if not values:
        return {"value": "[미기재]", "evidence_tag": "catalog-default", "case_refs": [], "count": 0}

    nums = []
    case_ids = []
    units = []
    for item in values:
        if len(item) == 3:
            val, case_id, unit = item
        else:
            val, case_id = item[:2]
            unit = ""
        if val is not None and str(val) != "[미기재]":
            try:
                nums.append(float(val))
                case_ids.append(case_id)
                if unit:
                    units.append(unit)
            except (ValueError, TypeError):
                pass

    if not nums:
        all_case_ids = list(set(item[1] for item in values))
        return {"value": "[미기재]", "evidence_tag": "catalog-default", "case_refs": all_case_ids, "count": 0}

    unique_cases = sorted(set(case_ids))
    unit = _safe_mode(units) if units else ""
    evidence_tag = "literature-consensus" if len(unique_cases) >= min_refs else "expert-inference"

    return {
        "min": min(nums),
        "max": max(nums),
        "median": round(median(nums), 2),
        "mode": _safe_mode(nums),
        "unit": unit,
        "count": len(nums),
        "case_refs": unique_cases,
        "evidence_tag": evidence_tag,
    }


def aggregate_equipment(cases: list, step_name: str = None) -> dict:
    """Aggregate equipment across cases for a given step.

    Returns:
        {"items": [...], "total_unique": int}
    """
    equipment_map = defaultdict(lambda: {"count": 0, "case_refs": [], "models": Counter(), "manufacturers": Counter()})

    for case in cases:
        case_id = case.get("case_id", "")
        for step in case.get("steps", []):
            if step_name and step.get("step_name", "").lower() != step_name.lower():
                continue

            eq_list = step.get("equipment", [])
            if isinstance(eq_list, str):
                if eq_list and eq_list != "[미기재]":
                    equipment_map[eq_list]["count"] += 1
                    equipment_map[eq_list]["case_refs"].append(case_id)
            elif isinstance(eq_list, list):
                for eq in eq_list:
                    if isinstance(eq, dict):
                        name = eq.get("name", "")
                        if name and name != "[미기재]":
                            equipment_map[name]["count"] += 1
                            equipment_map[name]["case_refs"].append(case_id)
                            model = eq.get("model", "")
                            if model and model != "[미기재]":
                                equipment_map[name]["models"][model] += 1
                            mfr = eq.get("manufacturer", "")
                            if mfr and mfr != "[미기재]":
                                equipment_map[name]["manufacturers"][mfr] += 1
                    elif isinstance(eq, str) and eq and eq != "[미기재]":
                        equipment_map[eq]["count"] += 1
                        equipment_map[eq]["case_refs"].append(case_id)

    items = []
    for name, data in sorted(equipment_map.items(), key=lambda x: -x[1]["count"]):
        item = {
            "name": name,
            "count": data["count"],
            "case_refs": sorted(set(data["case_refs"])),
            "evidence_tag": "literature-consensus" if data["count"] >= 2 else "expert-inference",
        }
        if data["models"]:
            item["model"] = data["models"].most_common(1)[0][0]
        else:
            item["model"] = "[미기재]"
        if data["manufacturers"]:
            item["manufacturer"] = data["manufacturers"].most_common(1)[0][0]
        else:
            item["manufacturer"] = "[미기재]"
        items.append(item)

    return {"items": items, "total_unique": len(items)}


def aggregate_numeric_params(cases: list, step_name: str) -> dict:
    """Aggregate numeric parameters across cases for a given step.

    Returns dict of parameter_name -> range_with_median result.
    """
    param_values = defaultdict(list)

    for case in cases:
        case_id = case.get("case_id", "")
        for step in case.get("steps", []):
            if step.get("step_name", "").lower() != step_name.lower():
                continue

            conditions = step.get("conditions", "")
            if isinstance(conditions, dict):
                for param_name, param_val in conditions.items():
                    if param_val and str(param_val) != "[미기재]":
                        nums = _extract_numeric_values(str(param_val))
                        unit = ""
                        # Try to extract unit
                        unit_match = re.search(r'[°℃Cc]\s*$|[Mm]in|[Hh]r|[Ss]ec|[Mm][Ll]|[Uu][Ll]|μ[Ll]|m[Mm]|n[Mm]|%|rpm|[Xx]g', str(param_val))
                        if unit_match:
                            unit = unit_match.group(0)
                        for n in nums:
                            param_values[param_name].append((n, case_id, unit))
            elif isinstance(conditions, str) and conditions != "[미기재]":
                nums = _extract_numeric_values(conditions)
                for n in nums:
                    param_values["conditions"].append((n, case_id, ""))

    result = {}
    for param_name, values in param_values.items():
        result[param_name] = range_with_median(values)

    return result


def aggregate_all_components(cases: list, variant: dict, uo_mapping: dict = None) -> dict:
    """Aggregate all 7 components for a variant's UO sequence.

    Args:
        cases: list of case card dicts for this variant
        variant: variant dict with defining_features
        uo_mapping: UO mapping data

    Returns:
        Dict of uo_position -> {component_name -> aggregated_data}
    """
    config = load_v2_config()
    phase8_config = config.get("phases", {}).get("phase_4_compose", config.get("phases", {}).get("phase8_components", {}))
    min_refs = phase8_config.get("min_case_refs_for_consensus", 2)

    components_by_uo = {}

    # Derive step order from case cards (protocol order, not alphabetical).
    # Use the case with the most steps as the canonical ordering reference,
    # then append any steps only found in other cases.
    ordered_step_names = []
    seen_steps = set()
    best_case = max(cases, key=lambda c: len(c.get("steps", []))) if cases else None
    if best_case:
        for step in best_case.get("steps", []):
            name = step.get("step_name", "")
            if name and name not in seen_steps:
                ordered_step_names.append(name)
                seen_steps.add(name)
    # Append steps from other cases that the best case doesn't have
    for case in cases:
        for step in case.get("steps", []):
            name = step.get("step_name", "")
            if name and name not in seen_steps:
                ordered_step_names.append(name)
                seen_steps.add(name)

    for i, step_name in enumerate(ordered_step_names, 1):
        if not step_name:
            continue

        uo_components = {}

        # material_and_method: majority vote on method descriptions
        method_values = []
        for case in cases:
            for step in case.get("steps", []):
                if step.get("step_name", "").lower() == step_name.lower():
                    desc = step.get("description", "")
                    if desc:
                        method_values.append((desc, case.get("case_id", "")))
        uo_components["material_and_method"] = majority_vote(method_values, min_refs)

        # equipment
        uo_components["equipment"] = aggregate_equipment(cases, step_name)

        # parameters: numeric aggregation
        uo_components["parameters"] = aggregate_numeric_params(cases, step_name)

        # input_output: majority vote
        input_values = []
        output_values = []
        for case in cases:
            for step in case.get("steps", []):
                if step.get("step_name", "").lower() == step_name.lower():
                    inp = step.get("input", step.get("input_material", ""))
                    out = step.get("output", step.get("output_material", ""))
                    if inp:
                        input_values.append((inp, case.get("case_id", "")))
                    if out:
                        output_values.append((out, case.get("case_id", "")))
        uo_components["input_output"] = {
            "input": majority_vote(input_values, min_refs),
            "output": majority_vote(output_values, min_refs),
        }

        # qc_checkpoint: collect QC items
        qc_items = []
        for case in cases:
            for step in case.get("steps", []):
                if step.get("step_name", "").lower() == step_name.lower():
                    qc = step.get("qc_checkpoint", step.get("qc", ""))
                    if qc and str(qc) != "[미기재]":
                        qc_items.append((str(qc), case.get("case_id", "")))
        uo_components["qc_checkpoint"] = majority_vote(qc_items, min_refs)

        # environment: temperature, atmosphere, etc.
        env_values = []
        for case in cases:
            for step in case.get("steps", []):
                if step.get("step_name", "").lower() == step_name.lower():
                    env = step.get("environment", step.get("conditions", ""))
                    if env and str(env) != "[미기재]":
                        env_values.append((str(env), case.get("case_id", "")))
        uo_components["environment"] = majority_vote(env_values, min_refs)

        # consumables
        consumable_values = []
        for case in cases:
            for step in case.get("steps", []):
                if step.get("step_name", "").lower() == step_name.lower():
                    cons = step.get("consumables", step.get("reagents", ""))
                    if cons and str(cons) != "[미기재]":
                        consumable_values.append((str(cons), case.get("case_id", "")))
        uo_components["consumables"] = majority_vote(consumable_values, min_refs)

        components_by_uo[step_name] = uo_components

    return components_by_uo


def validate_component_schema(component: dict, component_name: str) -> list[str]:
    """Validate a component against expected schema.

    Checks:
    - [미기재] fields that should have data
    - Missing evidence_tag
    - Empty case_refs on case-derived items

    Returns list of violation strings (empty = valid).
    """
    violations = []

    if isinstance(component, dict):
        value = component.get("value", component.get("items", None))
        evidence_tag = component.get("evidence_tag", "")
        case_refs = component.get("case_refs", [])

        # Check for missing evidence tag
        if value and str(value) != "[미기재]" and not evidence_tag:
            violations.append(f"{component_name}: has value but missing evidence_tag")

        # Check for literature-consensus without case_refs
        if evidence_tag == "literature-consensus" and not case_refs:
            violations.append(f"{component_name}: evidence_tag='literature-consensus' but empty case_refs")

    return violations


def save_components(wf_dir: str | Path, variant_id: str, components: dict) -> Path:
    """Save aggregated components to workflow directory."""
    wf_dir = Path(wf_dir)
    workflow_dir = wf_dir / "04_workflow"
    workflow_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "generated": datetime.now().isoformat(),
        "generator": f"populate_components v{__version__}",
        "variant_id": variant_id,
        "method": "rule_engine_v2",
        "components": components,
    }

    filepath = workflow_dir / f"components_{variant_id}.json"
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return filepath


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("=== populate_components.py self-test ===\n")

        # Test 1: majority_vote
        values = [("PCR", "C001"), ("PCR", "C002"), ("Gibson", "C003")]
        result = majority_vote(values)
        assert result["value"] == "PCR"
        assert result["confidence"] == round(2/3, 2)
        assert "C001" in result["case_refs"]
        print(f"Test 1 PASS: majority_vote → '{result['value']}' (conf={result['confidence']})")

        # Test 2: majority_vote with all [미기재]
        values_empty = [("[미기재]", "C001"), ("[미기재]", "C002")]
        result_empty = majority_vote(values_empty)
        assert result_empty["value"] == "[미기재]"
        assert result_empty["evidence_tag"] == "catalog-default"
        print(f"Test 2 PASS: majority_vote with [미기재] → '{result_empty['value']}'")

        # Test 3: range_with_median
        values_num = [(37.0, "C001", "°C"), (37.0, "C002", "°C"), (42.0, "C003", "°C")]
        result_num = range_with_median(values_num)
        assert result_num["min"] == 37.0
        assert result_num["max"] == 42.0
        assert result_num["median"] == 37.0
        assert result_num["unit"] == "°C"
        print(f"Test 3 PASS: range_with_median → {result_num['min']}-{result_num['max']} {result_num['unit']} (median={result_num['median']})")

        # Test 4: aggregate_equipment
        cases = [
            {"case_id": "C001", "steps": [
                {"step_name": "PCR", "equipment": [{"name": "Bio-Rad C1000", "model": "C1000", "manufacturer": "Bio-Rad"}]}
            ]},
            {"case_id": "C002", "steps": [
                {"step_name": "PCR", "equipment": [{"name": "Bio-Rad C1000", "model": "C1000", "manufacturer": "Bio-Rad"}]}
            ]},
            {"case_id": "C003", "steps": [
                {"step_name": "PCR", "equipment": [{"name": "Applied Biosystems Veriti", "model": "Veriti", "manufacturer": "Applied Biosystems"}]}
            ]},
        ]
        eq = aggregate_equipment(cases, "PCR")
        assert eq["total_unique"] == 2
        assert eq["items"][0]["name"] == "Bio-Rad C1000"  # Most common first
        assert eq["items"][0]["count"] == 2
        print(f"Test 4 PASS: aggregate_equipment → {eq['total_unique']} unique items")

        # Test 5: validate_component_schema
        good = {"value": "PCR", "evidence_tag": "literature-consensus", "case_refs": ["C001"]}
        bad = {"value": "PCR", "case_refs": ["C001"]}
        assert len(validate_component_schema(good, "method")) == 0
        assert len(validate_component_schema(bad, "method")) == 1
        print(f"Test 5 PASS: schema validation catches missing evidence_tag")

        # Test 6: Empty input handling
        empty_result = majority_vote([])
        assert empty_result["value"] == "[미기재]"
        empty_range = range_with_median([])
        assert empty_range["value"] == "[미기재]"
        print(f"Test 6 PASS: Empty input handling correct")

        print("\n=== All tests passed! ===")
    else:
        print("Usage: python populate_components.py --test")
