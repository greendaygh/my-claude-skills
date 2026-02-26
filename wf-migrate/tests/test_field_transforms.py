import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from field_transforms import (
    convert_parameters_to_conditions,
    parse_equipment,
    normalize_software,
    rename_step_fields,
    migrate_step,
)


# ---------------------------------------------------------------------------
# Parameters → conditions conversion
# ---------------------------------------------------------------------------

def test_convert_parameters_to_conditions():
    result = convert_parameters_to_conditions({"temp": "37C", "rpm": "200", "duration": "16h"})
    parts = [p.strip() for p in result.split(",")]
    assert "temp: 37C" in parts
    assert "rpm: 200" in parts
    assert "duration: 16h" in parts


def test_convert_parameters_empty():
    assert convert_parameters_to_conditions({}) == ""


def test_convert_parameters_nested():
    result = convert_parameters_to_conditions({"reaction": {"temp": "95C", "time": "5min"}})
    parts = [p.strip() for p in result.split(",")]
    assert "reaction.temp: 95C" in parts
    assert "reaction.time: 5min" in parts


# ---------------------------------------------------------------------------
# Equipment parsing
# ---------------------------------------------------------------------------

def test_parse_equipment_flat_strings():
    result = parse_equipment(["Autoclave", "Glass test tubes with caps"])
    assert result == [
        {"name": "Autoclave", "model": "", "manufacturer": ""},
        {"name": "Glass test tubes with caps", "model": "", "manufacturer": ""},
    ]


def test_parse_equipment_already_structured():
    inp = [{"name": "QuBit 2.0", "model": "QuBit 2.0", "manufacturer": "Thermo Fisher"}]
    assert parse_equipment(inp) == inp


def test_parse_equipment_partial_dict():
    result = parse_equipment([{"name": "Centrifuge", "manufacturer": "Eppendorf"}])
    assert result == [{"name": "Centrifuge", "model": "", "manufacturer": "Eppendorf"}]


def test_parse_equipment_empty():
    assert parse_equipment([]) == []


def test_parse_equipment_mixed():
    result = parse_equipment(["Autoclave", {"name": "QuBit", "model": "2.0", "manufacturer": "TF"}])
    assert result == [
        {"name": "Autoclave", "model": "", "manufacturer": ""},
        {"name": "QuBit", "model": "2.0", "manufacturer": "TF"},
    ]


# ---------------------------------------------------------------------------
# Software normalization
# ---------------------------------------------------------------------------

def test_normalize_software_flat_strings():
    result = normalize_software(["FIJI", "ImageJ"])
    assert result == [
        {"name": "FIJI", "version": "", "developer": ""},
        {"name": "ImageJ", "version": "", "developer": ""},
    ]


def test_normalize_software_already_structured():
    inp = [{"name": "FIJI", "version": "1.0", "developer": "NIH"}]
    assert normalize_software(inp) == inp


def test_normalize_software_empty_or_missing():
    assert normalize_software([]) == []
    assert normalize_software(None) == []


# ---------------------------------------------------------------------------
# Step field renaming
# ---------------------------------------------------------------------------

def test_rename_step_fields_position_name():
    step = {
        "position": 1,
        "name": "S1",
        "description": "D",
        "equipment": [],
        "parameters": {"temp": "37C"},
        "evidence_tag": "lit",
    }
    result = rename_step_fields(step)
    assert result["step_number"] == 1
    assert result["step_name"] == "S1"
    assert result["description"] == "D"
    assert result["evidence_tag"] == "lit"
    assert "temp: 37C" in result["conditions"]
    assert "position" not in result
    assert "name" not in result
    assert "parameters" not in result
    # All canonical fields present with defaults for missing
    assert result["reagents"] == ""
    assert result["software"] == []
    assert result["result_qc"] == ""
    assert result["notes"] == ""


def test_rename_step_fields_position_action():
    step = {
        "position": 1,
        "action": "Blood collection",
        "equipment": [],
    }
    result = rename_step_fields(step)
    assert result["step_number"] == 1
    assert result["step_name"] == "Blood collection"
    assert result["description"] == "Blood collection"
    assert "action" not in result
    assert "position" not in result


def test_rename_step_fields_canonical_passthrough():
    step = {
        "step_number": 1,
        "step_name": "S",
        "description": "D",
        "equipment": [],
        "software": [],
        "reagents": "",
        "conditions": "existing",
        "result_qc": "",
        "notes": "",
    }
    result = rename_step_fields(step)
    assert result["step_number"] == 1
    assert result["step_name"] == "S"
    assert result["conditions"] == "existing"


def test_rename_step_fields_missing_all():
    step = {"some_key": "value"}
    result = rename_step_fields(step)
    # All canonical fields added with defaults
    assert result["step_number"] is None
    assert result["step_name"] == ""
    assert result["description"] == ""
    assert result["equipment"] == []
    assert result["software"] == []
    assert result["reagents"] == ""
    assert result["conditions"] == ""
    assert result["result_qc"] == ""
    assert result["notes"] == ""
    # Unknown key preserved
    assert result["some_key"] == "value"


# ---------------------------------------------------------------------------
# Full step migration (convenience wrapper)
# ---------------------------------------------------------------------------

def test_migrate_step_legacy_complete():
    step = {
        "position": 3,
        "name": "Incubation",
        "description": "Incubate cells overnight",
        "equipment": ["Incubator", {"name": "Timer", "model": "T1", "manufacturer": "Lab"}],
        "parameters": {"temp": "37C", "CO2": "5%"},
        "software": ["FIJI"],
        "evidence_tag": "literature-consensus",
    }
    result = migrate_step(step)
    # Renamed fields
    assert result["step_number"] == 3
    assert result["step_name"] == "Incubation"
    assert result["description"] == "Incubate cells overnight"
    # Equipment normalized
    assert result["equipment"][0] == {"name": "Incubator", "model": "", "manufacturer": ""}
    assert result["equipment"][1] == {"name": "Timer", "model": "T1", "manufacturer": "Lab"}
    # Parameters converted
    assert "temp: 37C" in result["conditions"]
    assert "CO2: 5%" in result["conditions"]
    # Software normalized
    assert result["software"] == [{"name": "FIJI", "version": "", "developer": ""}]
    # Extra key preserved
    assert result["evidence_tag"] == "literature-consensus"
    # Legacy keys removed
    assert "position" not in result
    assert "name" not in result
    assert "parameters" not in result
    # All 9 canonical fields present
    for field in ("step_number", "step_name", "description", "equipment",
                  "software", "reagents", "conditions", "result_qc", "notes"):
        assert field in result
