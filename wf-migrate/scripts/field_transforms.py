"""Mechanical field transforms for legacy → canonical migration."""


def convert_parameters_to_conditions(params: dict) -> str:
    """Convert a parameters dict to a conditions string.

    Handles nested dicts by flattening with dot notation.
    Returns "key: value, key2: value2" format.
    """
    if not params:
        return ""

    def _flatten(d: dict, prefix: str = "") -> list[tuple[str, str]]:
        items = []
        for k, v in d.items():
            full_key = f"{prefix}.{k}" if prefix else k
            if isinstance(v, dict):
                items.extend(_flatten(v, full_key))
            else:
                items.append((full_key, str(v)))
        return items

    pairs = _flatten(params)
    return ", ".join(f"{k}: {v}" for k, v in pairs)


def parse_equipment(equipment) -> list[dict]:
    """Normalize equipment to list of {name, model, manufacturer}.

    Handles:
    - Flat strings: "Autoclave" → {name: "Autoclave", model: "", manufacturer: ""}
    - Partial dicts: {name: "X"} → {name: "X", model: "", manufacturer: ""}
    - Already structured: passthrough
    - Mixed lists
    """
    if not equipment:
        return []

    result = []
    for item in equipment:
        if isinstance(item, str):
            result.append({"name": item, "model": "", "manufacturer": ""})
        elif isinstance(item, dict):
            result.append({
                "name": item.get("name", ""),
                "model": item.get("model", ""),
                "manufacturer": item.get("manufacturer", ""),
            })
        else:
            result.append({"name": str(item), "model": "", "manufacturer": ""})
    return result


def normalize_software(software) -> list[dict]:
    """Normalize software to list of {name, version, developer}.

    Same pattern as parse_equipment.
    """
    if not software:
        return []

    result = []
    for item in software:
        if isinstance(item, str):
            result.append({"name": item, "version": "", "developer": ""})
        elif isinstance(item, dict):
            result.append({
                "name": item.get("name", ""),
                "version": item.get("version", ""),
                "developer": item.get("developer", ""),
            })
        else:
            result.append({"name": str(item), "version": "", "developer": ""})
    return result


def rename_step_fields(step: dict) -> dict:
    """Rename legacy step fields to canonical names.

    Mappings:
    - position → step_number
    - name → step_name
    - action → step_name AND description (if description missing)
    - parameters → conditions (via convert_parameters_to_conditions)

    Also:
    - Ensures all 9 canonical fields exist (with defaults for missing)
    - Normalizes equipment and software
    - Preserves extra keys (evidence_tag, duration, etc.)
    """
    CANONICAL_STEP_FIELDS = {
        "step_number": None,
        "step_name": "",
        "description": "",
        "equipment": [],
        "software": [],
        "reagents": "",
        "conditions": "",
        "result_qc": "",
        "notes": "",
    }

    # Work on a copy so we don't mutate the input
    src = dict(step)
    out = {}

    # Rename: position → step_number
    if "position" in src:
        out["step_number"] = src.pop("position")
    elif "step_number" in src:
        out["step_number"] = src.pop("step_number")

    # Rename: name → step_name
    if "name" in src:
        out["step_name"] = src.pop("name")
    elif "step_name" in src:
        out["step_name"] = src.pop("step_name")

    # Rename: action → step_name AND description (if description missing)
    if "action" in src:
        action_val = src.pop("action")
        if "step_name" not in out:
            out["step_name"] = action_val
        if "description" not in src and "description" not in out:
            out["description"] = action_val

    # Rename: parameters → conditions
    if "parameters" in src:
        params = src.pop("parameters")
        if isinstance(params, dict):
            out["conditions"] = convert_parameters_to_conditions(params)
        else:
            out["conditions"] = str(params) if params else ""
    elif "conditions" in src:
        out["conditions"] = src.pop("conditions")

    # Pass through description if present in src (not yet moved to out)
    if "description" in src:
        out["description"] = src.pop("description")

    # Normalize equipment
    equip_source = src.pop("equipment") if "equipment" in src else out.get("equipment", [])
    out["equipment"] = parse_equipment(equip_source)

    # Normalize software
    sw_source = src.pop("software") if "software" in src else out.get("software", [])
    out["software"] = normalize_software(sw_source)

    # Merge remaining src keys (extra/unknown keys preserved)
    out.update(src)

    # Apply canonical defaults for any missing fields
    for field, default in CANONICAL_STEP_FIELDS.items():
        if field not in out:
            # Use a fresh copy of mutable defaults
            out[field] = list(default) if isinstance(default, list) else default

    return out


def migrate_step(step: dict) -> dict:
    """Full migration of a single step dict. Convenience wrapper."""
    return rename_step_fields(step)
