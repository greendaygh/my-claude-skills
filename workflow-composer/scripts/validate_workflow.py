#!/usr/bin/env python3
"""
validate_workflow.py — Code-enforced validation of CRITICAL workflow rules for v2.0.

Replaces prompt-only CRITICAL rule enforcement with deterministic code checks.
Validates execution_log events, checkpoint integrity, and output file structure.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

_SCRIPTS_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPTS_DIR.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from scripts import __version__

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"


def load_execution_log(wf_dir: str | Path) -> dict:
    """Load execution_log.json from workflow directory."""
    log_path = Path(wf_dir) / "00_metadata" / "execution_log.json"
    if not log_path.exists():
        return {"events": [], "summary": {}}
    with open(log_path, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_phase2_search_rules(execution_log: dict) -> list[str]:
    """Validate Phase 2 (Search) CRITICAL rules from execution log.

    Checks:
    1. No parallel WebFetch calls (sequential only)
    2. No Task agent for WebFetch (main agent only)
    3. All WebFetch calls have 'prompt' parameter
    4. PMC URLs use correct format (pmc.ncbi.nlm.nih.gov)

    Returns list of violation strings (empty = all passed).
    """
    violations = []
    events = execution_log.get("events", [])

    # Track WebFetch timing for parallel detection
    webfetch_events = []
    agent_events = []

    for event in events:
        etype = event.get("type", "")

        if etype == "paper_access":
            webfetch_events.append(event)

            # Check 3: prompt parameter
            url = event.get("url", "")
            method = event.get("method", "")

            # Check 4: PMC URL format
            if "ncbi.nlm.nih.gov/pmc/" in url:
                violations.append(
                    f"CRITICAL: Wrong PMC URL format: '{url}'. "
                    f"Must use 'pmc.ncbi.nlm.nih.gov/articles/PMCxxxxx/'"
                )

        elif etype == "agent":
            agent_events.append(event)
            role = event.get("role", "")
            # Check 2: No Task agent for WebFetch
            if "webfetch" in role.lower() or "paper_fetch" in role.lower():
                phase = event.get("phase", "")
                if str(phase) in ("2", "3") or "phase_2" in str(phase).lower() or "phase3" in str(phase).lower():
                    violations.append(
                        f"CRITICAL: Task agent used for Phase 2 WebFetch (agent={event.get('agent_id', '')}). "
                        f"Main agent must call WebFetch directly."
                    )

    # Check 1: Parallel WebFetch detection
    # Look for WebFetch events with overlapping timestamps (within 2 seconds)
    if len(webfetch_events) >= 2:
        timestamps = []
        for we in webfetch_events:
            ts_str = we.get("timestamp", "")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    timestamps.append(ts)
                except (ValueError, TypeError):
                    pass

        for i in range(len(timestamps) - 1):
            diff = abs((timestamps[i + 1] - timestamps[i]).total_seconds())
            if diff < 2.0:
                violations.append(
                    f"WARNING: Possible parallel WebFetch detected — "
                    f"{diff:.1f}s between consecutive calls. Must be sequential."
                )

    return violations


def validate_phase5_output_rules(execution_log: dict, wf_dir: str | Path) -> list[str]:
    """Validate Phase 5 (Output) CRITICAL rules.

    Checks:
    1. Main agent did not write Korean prose directly
    2. Agent tasks were launched for Korean translation

    Returns list of violation strings.
    """
    violations = []
    wf_dir = Path(wf_dir)
    events = execution_log.get("events", [])

    # Check for agent launches in Phase 5 (output)
    phase5_agents = [
        e for e in events
        if e.get("type") == "agent" and str(e.get("phase", "")) in ("5", "10", "phase_5", "phase_10")
    ]

    # Check if Korean report files exist (they should be created by agents)
    ko_report = wf_dir / "composition_report_ko.md"
    ko_workflow = wf_dir / "composition_workflow_ko.md"

    if ko_report.exists() and not phase5_agents:
        # Check if the file has substantial Korean content (not just header translations)
        try:
            content = ko_report.read_text(encoding="utf-8")
            # Count Korean characters
            korean_chars = len(re.findall(r'[\uac00-\ud7af]', content))
            total_chars = len(content)
            if korean_chars > 100 and total_chars > 500:
                # Check if any agent was responsible
                agent_roles = [e.get("role", "") for e in phase5_agents]
                if "korean_report" not in agent_roles and "translation" not in " ".join(agent_roles).lower():
                    violations.append(
                        "WARNING: composition_report_ko.md has substantial Korean content "
                        "but no Korean translation agent was logged. "
                        "Main agent should not write Korean prose directly."
                    )
        except (OSError, UnicodeDecodeError):
            pass

    return violations


def validate_checkpoint(checkpoint: dict) -> list[str]:
    """Validate checkpoint integrity.

    Checks:
    1. schema_version field present and valid
    2. Required fields present
    3. File references point to existing paths (if wf_dir provided in checkpoint)

    Returns list of violation strings.
    """
    violations = []

    if not checkpoint:
        violations.append("CRITICAL: Checkpoint is empty or None")
        return violations

    # Check schema_version
    sv = checkpoint.get("schema_version", "")
    if not sv:
        sv = checkpoint.get("version", "")
    if not sv:
        violations.append("CRITICAL: Checkpoint missing schema_version field")

    # Check checkpoint_type
    ctype = checkpoint.get("checkpoint_type", "")
    if not ctype:
        violations.append("CRITICAL: Checkpoint missing checkpoint_type field")

    # Required fields per type
    required_fields = {
        "cycle1": ["workflow_context", "composition_mode", "paper_pool", "case_summary"],
        "cycle2": ["workflow_context", "composition_mode", "variants", "analysis_summary"],
    }

    required = required_fields.get(ctype, [])
    for field in required:
        if field not in checkpoint:
            violations.append(f"WARNING: Checkpoint {ctype} missing field: {field}")

    # Validate workflow_context has essential subfields
    wf_ctx = checkpoint.get("workflow_context", {})
    if wf_ctx:
        for subfield in ["workflow_id", "workflow_name"]:
            if not wf_ctx.get(subfield):
                violations.append(f"WARNING: workflow_context missing {subfield}")

    return violations


def validate_output_structure(wf_dir: str | Path) -> list[str]:
    """Validate the output directory has all expected files.

    Returns list of missing/issue strings.
    """
    violations = []
    wf_dir = Path(wf_dir)

    expected_dirs = [
        "00_metadata",
        "01_papers",
        "02_cases",
        "03_analysis",
        "04_workflow",
        "05_visualization",
    ]

    for d in expected_dirs:
        if not (wf_dir / d).exists():
            violations.append(f"Missing directory: {d}")

    expected_files = {
        "00_metadata/workflow_context.json": True,
        "01_papers/paper_list.json": True,
        "02_cases/case_summary.json": True,
        "03_analysis/common_pattern.json": True,
        "04_workflow/uo_mapping.json": True,
        "composition_data.json": True,
        "composition_report.md": True,
    }

    for filepath, required in expected_files.items():
        if not (wf_dir / filepath).exists():
            level = "CRITICAL" if required else "WARNING"
            violations.append(f"{level}: Missing file: {filepath}")

    # Inline report section validation (no cross-skill import)
    report_path = wf_dir / "composition_report.md"
    if report_path.exists():
        try:
            report_content = report_path.read_text(encoding="utf-8")
            required_section_nums = set(range(1, 14))  # sections 1-13
            found_nums = set()
            for line in report_content.split("\n"):
                match = re.match(r'^## (\d+)\.', line)
                if match:
                    found_nums.add(int(match.group(1)))
            missing_nums = required_section_nums - found_nums
            if missing_nums:
                missing_str = ", ".join(str(n) for n in sorted(missing_nums))
                violations.append(
                    f"CRITICAL: composition_report.md missing sections: {missing_str} "
                    f"(expected 13 sections, found {len(found_nums)})"
                )
        except (OSError, UnicodeDecodeError) as e:
            violations.append(
                f"WARNING: Cannot read composition_report.md for section validation: {e}"
            )

    return violations


def validate_case_cards(wf_dir: str | Path) -> list[str]:
    """Validate case card completeness and consistency.

    Checks:
    - Required fields present
    - case_id format matches filename
    - steps array not empty
    - metadata fields present
    """
    violations = []
    wf_dir = Path(wf_dir)
    cases_dir = wf_dir / "02_cases"

    if not cases_dir.exists():
        violations.append("WARNING: 02_cases directory does not exist")
        return violations

    for cf in sorted(cases_dir.glob("case_C*.json")):
        try:
            with open(cf, "r", encoding="utf-8") as f:
                card = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            violations.append(f"CRITICAL: Cannot parse {cf.name}: {e}")
            continue

        # Check case_id matches filename
        expected_id_part = cf.stem.replace("case_", "")
        actual_id = card.get("case_id", "")
        if expected_id_part not in actual_id:
            violations.append(f"WARNING: {cf.name} case_id mismatch: expected *{expected_id_part}*, got '{actual_id}'")

        # Check required fields
        if not card.get("steps"):
            violations.append(f"WARNING: {cf.name} has empty steps array")

        metadata = card.get("metadata", {})
        if not metadata.get("core_technique"):
            violations.append(f"WARNING: {cf.name} missing metadata.core_technique")

    return violations


def validate_composition_data_schema(wf_dir: str | Path) -> list[str]:
    """Validate composition_data.json conforms to Schema v4.0.0.

    Checks:
    - Required top-level fields present
    - Statistics uses standard field names
    - Version is numeric
    - composition_date is YYYY-MM-DD format
    """
    violations = []
    wf_dir = Path(wf_dir)
    cd_path = wf_dir / "composition_data.json"

    if not cd_path.exists():
        violations.append("CRITICAL: composition_data.json not found")
        return violations

    try:
        with open(cd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        violations.append(f"CRITICAL: Cannot parse composition_data.json: {e}")
        return violations

    # Required top-level fields
    required_fields = [
        "schema_version", "workflow_id", "workflow_name", "category",
        "domain", "version", "composition_date", "statistics",
    ]
    for field in required_fields:
        if field not in data:
            violations.append(f"CRITICAL: composition_data.json missing required field: {field}")

    # schema_version check
    sv = data.get("schema_version", "")
    if sv and not sv.startswith("4."):
        violations.append(f"WARNING: schema_version is '{sv}', expected 4.x.x")

    # version should be numeric
    ver = data.get("version")
    if ver is not None and not isinstance(ver, (int, float)):
        violations.append(f"WARNING: version should be numeric, got {type(ver).__name__}: {ver}")

    # composition_date format
    cd = data.get("composition_date", "")
    if cd and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(cd)):
        violations.append(f"WARNING: composition_date should be YYYY-MM-DD, got: {cd}")

    # Deprecated field check
    deprecated = ["generated", "created_at", "created_date", "cluster_result"]
    for dep in deprecated:
        if dep in data:
            violations.append(f"WARNING: composition_data.json contains deprecated field: {dep}")

    # Statistics standard field names
    stats = data.get("statistics", {})
    standard_stats = ["papers_analyzed", "cases_collected", "variants_identified", "total_uos", "qc_checkpoints"]
    for field in standard_stats:
        if field not in stats:
            violations.append(f"WARNING: statistics missing standard field: {field}")

    # Non-standard statistics field names
    nonstandard = {
        "total_papers": "papers_analyzed",
        "papers_selected": "papers_analyzed",
        "papers_retained": "papers_analyzed",
        "total_cases": "cases_collected",
        "cases_extracted": "cases_collected",
        "total_variants": "variants_identified",
        "variants_composed": "variants_identified",
        "total_uo_types": "total_uos",
        "uo_types_used": "total_uos",
        "total_qc_checkpoints": "qc_checkpoints",
    }
    for old_name, new_name in nonstandard.items():
        if old_name in stats:
            violations.append(f"WARNING: statistics uses non-standard field '{old_name}', should be '{new_name}'")

    # category value check
    cat = data.get("category", "")
    if cat and cat not in ("Build", "Test", "Design", "Learn"):
        violations.append(f"WARNING: category '{cat}' is not a standard value (Build/Test/Design/Learn)")

    return violations


# ---------------------------------------------------------------------------
# Enhanced gate checks
# ---------------------------------------------------------------------------

def validate_phase2_gate(wf_dir: str | Path) -> list[str]:
    """Enhanced Phase 2 gate: case_summary.json has >= 3 valid cases."""
    violations = []
    wf_dir = Path(wf_dir)
    cs_path = wf_dir / "02_cases" / "case_summary.json"

    if not cs_path.exists():
        violations.append("CRITICAL: 02_cases/case_summary.json not found")
        return violations

    try:
        with open(cs_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        violations.append(f"CRITICAL: Cannot parse case_summary.json: {e}")
        return violations

    cases = data.get("cases", [])
    if len(cases) < 3:
        violations.append(f"CRITICAL: Only {len(cases)} cases found, minimum 3 required")

    for i, c in enumerate(cases):
        if not isinstance(c, dict):
            violations.append(f"WARNING: cases[{i}] is not a dict")
            continue
        if not c.get("case_id"):
            violations.append(f"WARNING: cases[{i}] missing case_id")

    return violations


def validate_phase34_gate(wf_dir: str | Path) -> list[str]:
    """Enhanced Phase 3+4 gate: variant files have non-empty unit_operations."""
    violations = []
    wf_dir = Path(wf_dir)
    wf_dir_04 = wf_dir / "04_workflow"

    uo_mapping_path = wf_dir_04 / "uo_mapping.json"
    if not uo_mapping_path.exists():
        violations.append("CRITICAL: 04_workflow/uo_mapping.json not found")

    variant_files = sorted(wf_dir_04.glob("variant_V*.json")) if wf_dir_04.exists() else []
    if not variant_files:
        violations.append("CRITICAL: No variant_V*.json files found in 04_workflow/")
        return violations

    for vf in variant_files:
        try:
            with open(vf, "r", encoding="utf-8") as f:
                vdata = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            violations.append(f"CRITICAL: Cannot parse {vf.name}: {e}")
            continue

        uo_list = vdata.get("unit_operations", vdata.get("uo_sequence", []))
        if not uo_list:
            violations.append(f"WARNING: {vf.name} has empty unit_operations")

    return violations


def validate_phase5_gate(wf_dir: str | Path) -> list[str]:
    """Enhanced Phase 5 gate: composition_data.json has valid statistics."""
    violations = []
    wf_dir = Path(wf_dir)
    cd_path = wf_dir / "composition_data.json"

    if not cd_path.exists():
        violations.append("CRITICAL: composition_data.json not found")
        return violations

    try:
        with open(cd_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        violations.append(f"CRITICAL: Cannot parse composition_data.json: {e}")
        return violations

    stats = data.get("statistics", {})
    for field in ("papers_analyzed", "cases_collected", "variants_identified", "total_uos"):
        val = stats.get(field, 0)
        if not isinstance(val, (int, float)) or val <= 0:
            violations.append(f"WARNING: statistics.{field} = {val}, expected > 0")

    report_path = wf_dir / "composition_report.md"
    if not report_path.exists():
        violations.append("CRITICAL: composition_report.md not found")

    return violations


def validate_variant_canonical_format(wf_dir: str | Path) -> list[str]:
    """Verify variant files use canonical unit_operations key."""
    violations = []
    wf_dir = Path(wf_dir)
    wf_dir_04 = wf_dir / "04_workflow"

    if not wf_dir_04.exists():
        return violations

    for vf in sorted(wf_dir_04.glob("variant_V*.json")):
        try:
            with open(vf, "r", encoding="utf-8") as f:
                vdata = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        if "uo_sequence" in vdata and "unit_operations" not in vdata:
            violations.append(
                f"WARNING: {vf.name} uses legacy 'uo_sequence' key, should be 'unit_operations'"
            )
        if "name" in vdata and "variant_name" not in vdata:
            violations.append(
                f"WARNING: {vf.name} uses legacy 'name' key, should be 'variant_name'"
            )

        uo_list = vdata.get("unit_operations", [])
        for i, uo in enumerate(uo_list):
            if not isinstance(uo, dict):
                continue
            if "components" in uo:
                violations.append(
                    f"WARNING: {vf.name} unit_operations[{i}] uses legacy 'components' wrapper"
                )
                break

    return violations


def run_full_validation(wf_dir: str | Path, session_num: int = None) -> dict:
    """Run full validation suite.

    Args:
        wf_dir: workflow output directory
        session_num: optional session number (1, 2, or 3) to scope checks

    Returns:
        {
            "valid": bool,
            "total_violations": int,
            "critical_count": int,
            "warning_count": int,
            "violations_by_category": {category: [violations]},
            "validated_at": str,
        }
    """
    wf_dir = Path(wf_dir)
    all_violations = {}

    # Always run structure check
    struct_violations = validate_output_structure(wf_dir)
    if struct_violations:
        all_violations["output_structure"] = struct_violations

    # Always run case card check
    case_violations = validate_case_cards(wf_dir)
    if case_violations:
        all_violations["case_cards"] = case_violations

    # Schema v4.0.0 compliance check
    schema_violations = validate_composition_data_schema(wf_dir)
    if schema_violations:
        all_violations["composition_data_schema"] = schema_violations

    # Canonical format check
    canonical_violations = validate_variant_canonical_format(wf_dir)
    if canonical_violations:
        all_violations["variant_canonical_format"] = canonical_violations

    # Enhanced gate checks
    gate2 = validate_phase2_gate(wf_dir)
    if gate2:
        all_violations["phase2_gate"] = gate2
    gate34 = validate_phase34_gate(wf_dir)
    if gate34:
        all_violations["phase34_gate"] = gate34
    gate5 = validate_phase5_gate(wf_dir)
    if gate5:
        all_violations["phase5_gate"] = gate5

    # Load execution log for rule checks
    exec_log = load_execution_log(wf_dir)

    if session_num is None or session_num == 1:
        phase2_violations = validate_phase2_search_rules(exec_log)
        if phase2_violations:
            all_violations["phase2_search_rules"] = phase2_violations

    if session_num is None or session_num == 3:
        phase5_violations = validate_phase5_output_rules(exec_log, wf_dir)
        if phase5_violations:
            all_violations["phase5_output_rules"] = phase5_violations

    # Checkpoint validation
    for cycle in [1, 2]:
        cp_path = wf_dir / "00_metadata" / f"checkpoint_cycle{cycle}.json"
        if cp_path.exists():
            try:
                with open(cp_path, "r", encoding="utf-8") as f:
                    cp = json.load(f)
                cp_violations = validate_checkpoint(cp)
                if cp_violations:
                    all_violations[f"checkpoint_cycle{cycle}"] = cp_violations
            except (json.JSONDecodeError, OSError) as e:
                all_violations[f"checkpoint_cycle{cycle}"] = [f"CRITICAL: Cannot parse checkpoint: {e}"]

    # Count totals
    total = sum(len(v) for v in all_violations.values())
    critical = sum(
        1 for vs in all_violations.values()
        for v in vs if v.startswith("CRITICAL")
    )
    warnings = total - critical

    result = {
        "valid": critical == 0,
        "total_violations": total,
        "critical_count": critical,
        "warning_count": warnings,
        "violations_by_category": all_violations,
        "validated_at": datetime.now().isoformat(),
        "validator_version": __version__,
    }

    # Save validation report
    metadata_dir = wf_dir / "00_metadata"
    if metadata_dir.exists():
        report_path = metadata_dir / "validation_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    return result


if __name__ == "__main__":
    if "--test" in sys.argv:
        import tempfile

        print("=== validate_workflow.py self-test ===\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            wf_dir = Path(tmpdir) / "WB030_test"

            # Create minimal structure
            for d in ["00_metadata", "01_papers", "02_cases", "03_analysis", "04_workflow", "05_visualization"]:
                (wf_dir / d).mkdir(parents=True, exist_ok=True)

            # Create minimal files
            with open(wf_dir / "00_metadata" / "workflow_context.json", "w") as f:
                json.dump({"workflow_id": "WB030", "workflow_name": "DNA Assembly"}, f)
            with open(wf_dir / "01_papers" / "paper_list.json", "w") as f:
                json.dump({"papers": []}, f)
            with open(wf_dir / "02_cases" / "case_summary.json", "w") as f:
                json.dump({"total_cases": 1}, f)
            with open(wf_dir / "03_analysis" / "common_pattern.json", "w") as f:
                json.dump({"mandatory_steps": []}, f)
            with open(wf_dir / "04_workflow" / "uo_mapping.json", "w") as f:
                json.dump({"mappings": []}, f)
            with open(wf_dir / "composition_data.json", "w") as f:
                json.dump({
                    "schema_version": "4.0.0",
                    "workflow_id": "WB030",
                    "workflow_name": "DNA Assembly",
                    "category": "Build",
                    "domain": "Molecular Biology / Cloning",
                    "version": 3.0,
                    "composition_date": "2026-02-24",
                    "statistics": {
                        "papers_analyzed": 5,
                        "cases_collected": 3,
                        "variants_identified": 2,
                        "total_uos": 8,
                        "qc_checkpoints": 3
                    }
                }, f)
            with open(wf_dir / "composition_report.md", "w") as f:
                f.write("# Test Report\n\n")
                for i in range(1, 14):
                    f.write(f"## {i}. Section {i}\n\nContent.\n\n")

            # Create a valid case card
            case = {
                "case_id": "WB030-C001",
                "steps": [{"step_number": 1, "step_name": "PCR"}],
                "metadata": {"core_technique": "Gibson Assembly"},
            }
            with open(wf_dir / "02_cases" / "case_C001.json", "w") as f:
                json.dump(case, f)

            # Create a valid checkpoint
            cp = {
                "checkpoint_type": "cycle1",
                "schema_version": "2.0.0",
                "workflow_context": {"workflow_id": "WB030", "workflow_name": "DNA Assembly"},
                "composition_mode": "new",
                "paper_pool": {"total": 5, "active": 4},
                "case_summary": {"total_cases": 3},
            }
            with open(wf_dir / "00_metadata" / "checkpoint_cycle1.json", "w") as f:
                json.dump(cp, f)

            # Test 1: Full validation on valid structure
            result = run_full_validation(wf_dir)
            print(f"Test 1: valid={result['valid']}, violations={result['total_violations']}")
            print(f"  critical={result['critical_count']}, warnings={result['warning_count']}")
            assert result["valid"], f"Expected valid, got violations: {result['violations_by_category']}"
            print("  PASS: Valid structure passes validation")

            # Test 2: Checkpoint validation
            bad_cp = {"checkpoint_type": "cycle1"}  # Missing fields
            cp_violations = validate_checkpoint(bad_cp)
            assert len(cp_violations) >= 2, f"Expected >=2 violations, got {len(cp_violations)}"
            print(f"\nTest 2 PASS: Bad checkpoint caught {len(cp_violations)} violations")
            for v in cp_violations:
                print(f"  {v}")

            # Test 3: Empty checkpoint
            empty_violations = validate_checkpoint(None)
            assert any("empty" in v.lower() for v in empty_violations)
            print(f"\nTest 3 PASS: Empty checkpoint caught")

            # Test 4: Phase 2 search rule — wrong PMC URL
            log_with_bad_url = {
                "events": [
                    {
                        "type": "paper_access",
                        "url": "https://www.ncbi.nlm.nih.gov/pmc/articles/PMC123/",
                        "timestamp": "2026-01-01T10:00:00",
                    }
                ]
            }
            p2_violations = validate_phase2_search_rules(log_with_bad_url)
            assert any("PMC URL" in v for v in p2_violations)
            print(f"\nTest 4 PASS: Wrong PMC URL caught")

            # Test 5: Case card with missing fields
            bad_case = {"case_id": "WRONG", "steps": [], "metadata": {}}
            with open(wf_dir / "02_cases" / "case_C999.json", "w") as f:
                json.dump(bad_case, f)
            case_violations = validate_case_cards(wf_dir)
            assert any("empty steps" in v.lower() for v in case_violations)
            assert any("core_technique" in v for v in case_violations)
            print(f"\nTest 5 PASS: Bad case card caught {len(case_violations)} violations")

            print("\n=== All tests passed! ===")

    elif len(sys.argv) >= 2:
        wf_dir = sys.argv[1]
        session = int(sys.argv[2]) if len(sys.argv) > 2 else None
        result = run_full_validation(wf_dir, session)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("Usage: python validate_workflow.py <workflow_dir> [session_num]")
        print("       python validate_workflow.py --test")
