"""Variant file migration from legacy structures to canonical format.

Handles three known legacy patterns:
  Pattern A (WB005 style): unit_operations[].components.{Input,...}.details[].item
  Pattern B (WB040 style): top-level input/output, uo_sequence as string list
  Pattern C (WB010 style): uo_sequence[].components.{input,...}.items[].name

Canonical target (Variant Pydantic model):
  unit_operations[].{input,output,equipment,consumables,
                     material_and_method,result,discussion}
  Each component has .items[].name (or .measurements[].metric for result)
"""

import json
from pathlib import Path

_COMPONENT_KEY_MAP = {
    "Input": "input",
    "Output": "output",
    "Equipment": "equipment",
    "Consumables": "consumables",
    "Material_Method": "material_and_method",
    "Material_and_Method": "material_and_method",
    "material_method": "material_and_method",
    "Result": "result",
    "Discussion": "discussion",
    "input": "input",
    "output": "output",
    "equipment": "equipment",
    "consumables": "consumables",
    "material_and_method": "material_and_method",
    "result": "result",
    "discussion": "discussion",
    "parameters": "material_and_method",
}

_CANONICAL_COMPONENT_KEYS = {
    "input", "output", "equipment", "consumables",
    "material_and_method", "result", "discussion",
}

_EMPTY_COMPONENT = {"description": "", "items": []}


def _migrate_items_list(items_or_details: list) -> list:
    """Rename 'item' -> 'name' in detail/item lists."""
    migrated = []
    for entry in items_or_details:
        if not isinstance(entry, dict):
            migrated.append({"name": str(entry)})
            continue
        out = dict(entry)
        if "item" in out and "name" not in out:
            out["name"] = out.pop("item")
        migrated.append(out)
    return migrated


def _migrate_component(comp_data: dict, comp_key: str) -> tuple[dict, list[str]]:
    """Migrate a single component dict to canonical structure.

    Returns (canonical_component, list_of_changes).
    """
    if not isinstance(comp_data, dict):
        return dict(_EMPTY_COMPONENT), [f"{comp_key}: replaced non-dict with empty component"]

    changes = []
    out = dict(comp_data)

    if "details" in out and "items" not in out:
        out["items"] = _migrate_items_list(out.pop("details"))
        changes.append(f"{comp_key}: details->items")
    elif "items" in out:
        out["items"] = _migrate_items_list(out["items"])

    if "items" in out:
        for item in out["items"]:
            if isinstance(item, dict) and "item" in item and "name" not in item:
                item["name"] = item.pop("item")

    return out, changes


def _migrate_unit_operation(uo: dict, position: int) -> tuple[dict, list[str]]:
    """Migrate a single unit operation to canonical format.

    Handles flattening of 'components' dict and key renaming.
    """
    changes = []
    out = {}

    out["uo_id"] = uo.get("uo_id", uo.get("instance_label", f"UO{position:03d}"))
    out["uo_name"] = uo.get("uo_name", uo.get("name", ""))

    raw_pos = uo.get("step_position", uo.get("uo_order", uo.get("position", position)))
    try:
        out["step_position"] = int(raw_pos)
    except (ValueError, TypeError):
        out["step_position"] = position
        changes.append(f"step_position: '{raw_pos}' -> {position} (non-integer)")

    components = uo.get("components", {})
    if components and isinstance(components, dict):
        for legacy_key, comp_data in components.items():
            canonical_key = _COMPONENT_KEY_MAP.get(legacy_key, legacy_key.lower())
            if canonical_key not in _CANONICAL_COMPONENT_KEYS:
                out[canonical_key] = comp_data
                continue
            migrated_comp, comp_changes = _migrate_component(comp_data, canonical_key)
            out[canonical_key] = migrated_comp
            changes.extend(comp_changes)
            if legacy_key != canonical_key:
                changes.append(f"component: {legacy_key} -> {canonical_key}")
    else:
        for legacy_key in list(uo.keys()):
            canonical_key = _COMPONENT_KEY_MAP.get(legacy_key)
            if canonical_key and canonical_key in _CANONICAL_COMPONENT_KEYS:
                comp_data = uo[legacy_key]
                if isinstance(comp_data, dict):
                    migrated_comp, comp_changes = _migrate_component(comp_data, canonical_key)
                    out[canonical_key] = migrated_comp
                    changes.extend(comp_changes)
                else:
                    out[canonical_key] = comp_data

    for key in _CANONICAL_COMPONENT_KEYS:
        if key not in out:
            out[key] = dict(_EMPTY_COMPONENT)
            changes.append(f"{key}: added empty component stub")

    for key, value in uo.items():
        if key not in out and key not in ("components", "step_position",
                                           "uo_order", "position",
                                           "instance_label"):
            out[key] = value

    return out, changes


def _is_canonical_variant(data: dict) -> bool:
    """Check if variant file is already in canonical format."""
    uos = data.get("unit_operations", [])
    if not uos or not isinstance(uos, list):
        return False
    first_uo = uos[0]
    if not isinstance(first_uo, dict):
        return False
    if "components" in first_uo:
        return False
    return "input" in first_uo and "output" in first_uo


def migrate_variant_data(data: dict) -> tuple[dict, list[str]]:
    """Migrate variant JSON data to canonical format.

    Returns (migrated_data, list_of_changes).
    """
    changes = []
    out = dict(data)

    if "name" in out and "variant_name" not in out:
        out["variant_name"] = out.pop("name")
        changes.append("name -> variant_name")

    if "case_refs" in out and "case_ids" not in out:
        out["case_ids"] = out.pop("case_refs")
        changes.append("case_refs -> case_ids")
    elif "cases" in out and "case_ids" not in out:
        out["case_ids"] = out.pop("cases")
        changes.append("cases -> case_ids")
    elif "supporting_cases" in out and "case_ids" not in out:
        out["case_ids"] = out.pop("supporting_cases")
        changes.append("supporting_cases -> case_ids")

    raw_uos = out.get("unit_operations", [])
    if not raw_uos:
        raw_uos = out.pop("uo_sequence", [])
        if raw_uos:
            if raw_uos and isinstance(raw_uos[0], str):
                raw_uos = [{"uo_id": uid, "uo_name": uid, "step_position": i + 1}
                           for i, uid in enumerate(raw_uos)]
                changes.append("uo_sequence: string list -> unit_operations stubs")
            else:
                changes.append("uo_sequence -> unit_operations")
    if not raw_uos:
        raw_uos = out.pop("steps", [])
        if raw_uos:
            changes.append("steps -> unit_operations")

    if _is_canonical_variant({"unit_operations": raw_uos}):
        out["unit_operations"] = raw_uos
        return out, changes if changes else []

    migrated_uos = []
    for i, uo in enumerate(raw_uos, start=1):
        if not isinstance(uo, dict):
            continue
        migrated_uo, uo_changes = _migrate_unit_operation(uo, position=i)
        migrated_uos.append(migrated_uo)
        changes.extend(uo_changes)
    out["unit_operations"] = migrated_uos

    for key in ("uo_sequence", "steps"):
        out.pop(key, None)

    return out, changes


def migrate_variant_file(variant_path: Path, dry_run: bool = False) -> dict:
    """Migrate a single variant_V*.json file to canonical format.

    Args:
        variant_path: path to variant JSON file
        dry_run: if True, compute changes but don't write

    Returns:
        {"changes": list[str], "skipped": bool}
    """
    variant_path = Path(variant_path)
    with open(variant_path, encoding="utf-8") as f:
        data = json.load(f)

    if _is_canonical_variant(data):
        return {"changes": [], "skipped": True}

    migrated, changes = migrate_variant_data(data)

    if not changes:
        return {"changes": [], "skipped": True}

    if not dry_run:
        with open(variant_path, "w", encoding="utf-8") as f:
            json.dump(migrated, f, indent=2, ensure_ascii=False)

    return {"changes": changes, "skipped": False}
