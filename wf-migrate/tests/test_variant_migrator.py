"""Tests for variant_migrator.py."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from variant_migrator import migrate_variant_data, migrate_variant_file, _is_canonical_variant


def test_pattern_a_components_flattening():
    """WB005 style: components.{Input,...}.details[].item -> input.items[].name."""
    data = {
        "variant_id": "V1",
        "variant_name": "UV Spectrophotometry",
        "workflow_id": "WB005",
        "case_ids": ["C001"],
        "unit_operations": [
            {
                "uo_id": "UHW400",
                "uo_name": "Sample Prep",
                "step_position": 1,
                "components": {
                    "Input": {
                        "description": "Extracted nucleic acid",
                        "details": [
                            {"item": "gDNA in buffer", "case_refs": ["C001"], "evidence_tag": "sample"}
                        ]
                    },
                    "Output": {
                        "description": "Ready sample",
                        "details": [{"item": "Measured aliquot", "case_refs": ["C001"]}]
                    },
                    "Equipment": {"description": "NanoDrop", "details": []},
                    "Consumables": {"description": "None", "details": []},
                    "Material_Method": {"description": "Apply 1 uL"},
                    "Result": {"description": "Absorbance reading"},
                    "Discussion": {"description": "A260/A280 ratios"},
                }
            }
        ]
    }

    migrated, changes = migrate_variant_data(data)

    uo = migrated["unit_operations"][0]
    assert "components" not in uo
    assert "input" in uo
    assert "output" in uo
    assert "material_and_method" in uo
    assert uo["input"]["items"][0]["name"] == "gDNA in buffer"
    assert uo["output"]["items"][0]["name"] == "Measured aliquot"
    assert uo["step_position"] == 1
    assert len(changes) > 0


def test_pattern_a_string_step_position():
    """step_position as string should be converted to int."""
    data = {
        "variant_id": "V2",
        "variant_name": "Test",
        "workflow_id": "WB005",
        "unit_operations": [
            {
                "uo_id": "UO001",
                "uo_name": "Step",
                "step_position": "2b",
                "components": {
                    "Input": {"description": "D", "details": []},
                    "Output": {"description": "D", "details": []},
                }
            }
        ]
    }

    migrated, changes = migrate_variant_data(data)

    uo = migrated["unit_operations"][0]
    assert isinstance(uo["step_position"], int)
    assert any("non-integer" in c for c in changes)


def test_pattern_b_uo_sequence_strings():
    """WB040 style: uo_sequence as string list, top-level input/output."""
    data = {
        "variant_id": "V2",
        "name": "Spin Column",
        "workflow_id": "WB040",
        "case_refs": ["WB040-C001", "WB040-C002"],
        "uo_sequence": ["UO001", "UO002", "UO003"],
    }

    migrated, changes = migrate_variant_data(data)

    assert migrated["variant_name"] == "Spin Column"
    assert "name" not in migrated
    assert migrated["case_ids"] == ["WB040-C001", "WB040-C002"]
    assert "case_refs" not in migrated
    assert len(migrated["unit_operations"]) == 3
    assert migrated["unit_operations"][0]["uo_id"] == "UO001"
    assert any("uo_sequence" in c for c in changes)


def test_pattern_c_uo_sequence_objects():
    """WB010 style: uo_sequence as object array with components."""
    data = {
        "variant_id": "V5",
        "variant_name": "Microchip",
        "workflow_id": "WB010",
        "case_ids": ["C001"],
        "uo_sequence": [
            {
                "instance_label": "UO001a",
                "uo_name": "Primer Design",
                "components": {
                    "input": {"description": "Template", "items": [{"name": "DNA"}]},
                    "output": {"description": "Primers", "items": [{"name": "Oligos"}]},
                    "parameters": {"description": "Tm 60C"},
                }
            }
        ]
    }

    migrated, changes = migrate_variant_data(data)

    assert "uo_sequence" not in migrated
    assert len(migrated["unit_operations"]) == 1
    uo = migrated["unit_operations"][0]
    assert uo["uo_id"] == "UO001a"
    assert uo["input"]["items"][0]["name"] == "DNA"
    assert "material_and_method" in uo


def test_already_canonical_skipped():
    """Canonical variant data should not be modified."""
    data = {
        "variant_id": "V1",
        "variant_name": "Test",
        "workflow_id": "WB005",
        "unit_operations": [
            {
                "uo_id": "UO001",
                "uo_name": "Step",
                "step_position": 1,
                "input": {"description": "D", "items": []},
                "output": {"description": "D", "items": []},
                "equipment": {"description": "D", "items": []},
                "consumables": {"description": "D", "items": []},
                "material_and_method": {"description": "D"},
                "result": {"description": "D"},
                "discussion": {"description": "D"},
            }
        ]
    }

    assert _is_canonical_variant(data) is True
    migrated, changes = migrate_variant_data(data)
    assert changes == []


def test_migrate_variant_file_roundtrip(tmp_path):
    """Test file-level migration writes correctly."""
    data = {
        "variant_id": "V1",
        "variant_name": "Test",
        "workflow_id": "WB005",
        "unit_operations": [
            {
                "uo_id": "UO001",
                "uo_name": "Step",
                "step_position": 1,
                "components": {
                    "Input": {"description": "D", "details": [{"item": "sample"}]},
                    "Output": {"description": "D", "details": []},
                }
            }
        ]
    }

    vf = tmp_path / "variant_V1_Test.json"
    with open(vf, "w") as f:
        json.dump(data, f)

    result = migrate_variant_file(vf, dry_run=False)
    assert not result["skipped"]
    assert len(result["changes"]) > 0

    with open(vf) as f:
        written = json.load(f)
    assert "components" not in written["unit_operations"][0]
    assert written["unit_operations"][0]["input"]["items"][0]["name"] == "sample"


def test_top_level_renames():
    """name->variant_name, cases->case_ids, supporting_cases->case_ids."""
    data = {
        "variant_id": "V1",
        "name": "My Variant",
        "workflow_id": "WB005",
        "supporting_cases": ["C001", "C002"],
        "unit_operations": [
            {"uo_id": "UO001", "uo_name": "S", "step_position": 1,
             "components": {"Input": {"description": "", "details": []}}}
        ]
    }

    migrated, changes = migrate_variant_data(data)

    assert migrated["variant_name"] == "My Variant"
    assert "name" not in migrated
    assert migrated["case_ids"] == ["C001", "C002"]
    assert "supporting_cases" not in migrated


def test_empty_component_stubs():
    """Missing canonical components should get empty stubs."""
    data = {
        "variant_id": "V1",
        "variant_name": "Minimal",
        "workflow_id": "WB005",
        "unit_operations": [
            {
                "uo_id": "UO001",
                "uo_name": "Step",
                "step_position": 1,
                "components": {
                    "Input": {"description": "D", "details": []},
                }
            }
        ]
    }

    migrated, changes = migrate_variant_data(data)
    uo = migrated["unit_operations"][0]

    for key in ("input", "output", "equipment", "consumables",
                "material_and_method", "result", "discussion"):
        assert key in uo, f"Missing canonical component: {key}"
