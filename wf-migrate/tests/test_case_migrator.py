import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from case_migrator import migrate_case_card, is_canonical


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


PAPER_INDEX = {
    "P001": {
        "pmid": "12345",
        "doi": "10.1/test",
        "title": "Paper on E. coli culture",
        "authors": "Smith et al.",
        "year": 2021,
        "journal": "Journal of Microbiology",
    }
}


# ---------------------------------------------------------------------------
# test_migrate_case_card_legacy_flat
# ---------------------------------------------------------------------------

def test_migrate_case_card_legacy_flat(tmp_path):
    """WB140-style: paper_id, technique, position+name steps, flat equipment strings."""
    case_data = {
        "case_id": "WB140-C001",
        "paper_id": "P001",
        "title": "Standard overnight E. coli liquid culture",
        "technique": "Overnight Batch Culture",
        "organism": "E. coli",
        "scale": "bench (test tube, 5 mL)",
        "steps": [
            {
                "position": 1,
                "name": "Media Preparation",
                "description": "Prepare LB liquid medium...",
                "parameters": {"media_type": "LB", "volume": "5 mL"},
                "equipment": ["Autoclave", "Glass test tubes with caps"],
                "duration": "30-60 min",
                "evidence_tag": "literature-direct",
            }
        ],
        "notes": "Standard protocol",
        "qc_checkpoints": [{"checkpoint": "OD check"}],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WB140")

    # case_id preserved
    assert result["case_id"] == "WB140-C001"

    # metadata block with all 14 fields
    assert "metadata" in result
    meta = result["metadata"]
    required_meta_fields = [
        "pmid", "doi", "authors", "year", "journal", "title",
        "purpose", "organism", "scale", "core_technique",
        "automation_level", "fulltext_access", "access_method", "access_tier",
    ]
    for field in required_meta_fields:
        assert field in meta, f"metadata missing field: {field}"

    # completeness block
    assert "completeness" in result
    assert "score" in result["completeness"]

    # flow_diagram
    assert "flow_diagram" in result
    assert isinstance(result["flow_diagram"], str)

    # workflow_context
    assert "workflow_context" in result
    assert result["workflow_context"]["workflow_id"] == "WB140"

    # steps migrated
    assert "steps" in result
    step = result["steps"][0]
    assert "step_number" in step
    assert step["step_number"] == 1
    assert "step_name" in step
    assert step["step_name"] == "Media Preparation"
    assert "conditions" in step
    assert "parameters" not in step
    assert "position" not in step
    assert "name" not in step

    # equipment structured
    assert isinstance(step["equipment"], list)
    assert isinstance(step["equipment"][0], dict)
    assert "name" in step["equipment"][0]
    assert step["equipment"][0]["name"] == "Autoclave"
    assert "model" in step["equipment"][0]
    assert "manufacturer" in step["equipment"][0]

    # top-level absorbed fields removed
    assert "paper_id" not in result
    assert "technique" not in result
    assert "title" not in result

    # organism/scale absorbed into metadata (removed from top level)
    assert "organism" not in result
    assert "scale" not in result


# ---------------------------------------------------------------------------
# test_migrate_case_card_wt_extended
# ---------------------------------------------------------------------------

def test_migrate_case_card_wt_extended(tmp_path):
    """WT050-style: variant_hint, action steps, structured equipment dicts."""
    case_data = {
        "case_id": "C001",
        "paper_id": "P001",
        "workflow_id": "WT050",
        "title": "Plasma/Serum Collection",
        "technique": "Protein precipitation",
        "variant_hint": "V1",
        "steps": [
            {
                "position": 1,
                "action": "Blood collection into K2-EDTA tubes",
                "equipment": [{"name": "Vacutainer", "manufacturer": "BD"}],
                "parameters": {"tube_type": "K2-EDTA", "volume": "4 mL"},
                "evidence_tag": "literature-direct",
            }
        ],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WT050")

    # metadata present
    assert "metadata" in result

    # steps migrated from action
    step = result["steps"][0]
    assert "step_name" in step
    assert step["step_name"] == "Blood collection into K2-EDTA tubes"
    assert "action" not in step

    # variant_hint preserved as extra field
    assert "variant_hint" in result
    assert result["variant_hint"] == "V1"


# ---------------------------------------------------------------------------
# test_migrate_case_card_wt_findings
# ---------------------------------------------------------------------------

def test_migrate_case_card_wt_findings(tmp_path):
    """WT120-style: workflow_steps instead of steps, key_findings field."""
    case_data = {
        "case_id": "C001",
        "paper_id": "P001",
        "organism": "E. coli",
        "title": "Fed-Batch Culture",
        "variant": "V1",
        "evidence_tag": "literature-direct",
        "key_findings": "Fed-batch increases yield by 3x",
        "workflow_steps": [
            {
                "position": 1,
                "action": "Inoculation",
                "parameters": {"inoculum_volume": "10 mL"},
            }
        ],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WT120")

    # steps populated from workflow_steps
    assert "steps" in result
    assert len(result["steps"]) == 1
    assert result["steps"][0]["step_name"] == "Inoculation"

    # workflow_steps key no longer present
    assert "workflow_steps" not in result

    # key_findings preserved
    assert "key_findings" in result
    assert result["key_findings"] == "Fed-batch increases yield by 3x"


# ---------------------------------------------------------------------------
# test_migrate_case_card_already_canonical
# ---------------------------------------------------------------------------

def test_migrate_case_card_already_canonical():
    """A v2_canonical card should be returned essentially unchanged."""
    canonical = {
        "case_id": "WB140-C001",
        "metadata": {
            "pmid": "123", "doi": "10.1/x", "authors": "A", "year": 2021,
            "journal": "J", "title": "T", "purpose": "P", "organism": "E. coli",
            "scale": "bench", "core_technique": "Culture",
            "automation_level": "manual", "fulltext_access": False,
            "access_method": "unknown", "access_tier": 3,
        },
        "completeness": {"score": 0.8, "notes": "Reviewed"},
        "flow_diagram": "Step A -> Step B",
        "workflow_context": {"workflow_id": "WB140", "migration_source": "wf-migrate v1.0.0"},
        "steps": [
            {
                "step_number": 1, "step_name": "Inoculation", "description": "D",
                "equipment": [], "software": [], "reagents": "",
                "conditions": "temp: 37C", "result_qc": "", "notes": "",
            }
        ],
    }

    result = migrate_case_card(canonical, PAPER_INDEX, workflow_id="WB140")

    # Core structure unchanged
    assert result["case_id"] == "WB140-C001"
    assert result["metadata"]["core_technique"] == "Culture"
    assert result["completeness"]["score"] == 0.8
    assert result["flow_diagram"] == "Step A -> Step B"
    assert result["steps"][0]["step_number"] == 1
    assert result["steps"][0]["step_name"] == "Inoculation"


# ---------------------------------------------------------------------------
# test_migrate_case_card_fixes_case_id
# ---------------------------------------------------------------------------

def test_migrate_case_card_fixes_case_id():
    """case_id 'C001' (missing prefix) should become 'WT050-C001'."""
    case_data = {
        "case_id": "C001",
        "paper_id": "P001",
        "title": "Test",
        "technique": "PCR",
        "steps": [],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WT050")

    assert result["case_id"] == "WT050-C001"


# ---------------------------------------------------------------------------
# test_migrate_case_card_preserves_extra_fields
# ---------------------------------------------------------------------------

def test_migrate_case_card_preserves_extra_fields():
    """Extra fields like variant_hint, evidence_tag, downstream_analysis are preserved."""
    case_data = {
        "case_id": "WT050-C001",
        "paper_id": "P001",
        "title": "Plasma collection",
        "technique": "Centrifugation",
        "variant_hint": "V2",
        "evidence_tag": "literature-consensus",
        "downstream_analysis": "proteomics",
        "steps": [],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WT050")

    assert result["variant_hint"] == "V2"
    assert result["evidence_tag"] == "literature-consensus"
    assert result["downstream_analysis"] == "proteomics"


# ---------------------------------------------------------------------------
# test_is_canonical
# ---------------------------------------------------------------------------

def test_is_canonical():
    """is_canonical() returns True for v2 cards with required sub-fields, False for legacy."""
    legacy = {
        "case_id": "WB140-C001",
        "paper_id": "P001",
        "title": "T",
        "steps": [],
    }
    assert is_canonical(legacy) is False

    canonical = {
        "case_id": "WB140-C001",
        "metadata": {},
        "completeness": {"score": 0.8},
        "flow_diagram": "",
        "workflow_context": {"workflow_id": "WB140"},
        "steps": [],
    }
    assert is_canonical(canonical) is True

    # partial — missing workflow_context
    partial = {
        "case_id": "WB140-C001",
        "metadata": {},
        "completeness": {"score": 0.5},
        "flow_diagram": "",
        "steps": [],
    }
    assert is_canonical(partial) is False

    # Keys present but missing required sub-fields
    incomplete_sub = {
        "case_id": "WB140-C001",
        "metadata": {},
        "completeness": {"notes": "no score"},
        "flow_diagram": "",
        "workflow_context": {"boundary_inputs": []},
        "steps": [],
    }
    assert is_canonical(incomplete_sub) is False


# ---------------------------------------------------------------------------
# test_dry_run_mode
# ---------------------------------------------------------------------------

def test_dry_run_mode():
    """dry_run=True returns {'migrated': dict, 'changes': list[str]}."""
    case_data = {
        "case_id": "C001",
        "paper_id": "P001",
        "title": "Test",
        "technique": "PCR",
        "steps": [
            {"position": 1, "name": "Amplification", "parameters": {"cycles": "30"}},
        ],
    }

    result = migrate_case_card(case_data, PAPER_INDEX, workflow_id="WT050", dry_run=True)

    assert isinstance(result, dict)
    assert "migrated" in result
    assert "changes" in result
    assert isinstance(result["changes"], list)
    assert len(result["changes"]) > 0

    # migrated dict is a valid canonical card
    migrated = result["migrated"]
    assert "metadata" in migrated
    assert "completeness" in migrated

    # changes should mention case_id fix and metadata addition
    changes_text = "\n".join(result["changes"])
    assert "C001" in changes_text or "case_id" in changes_text.lower()
    assert any("metadata" in c.lower() or "step" in c.lower() for c in result["changes"])
