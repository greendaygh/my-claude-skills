#!/usr/bin/env python3
"""validate.py — Deterministic validation for workflow composition outputs."""

import json
import re
import sys
from pathlib import Path

# Import shared DOI validator (graceful fallback if not available)
_HAS_DOI_VALIDATOR = False
try:
    _doi_validator_dir = str(Path(__file__).resolve().parent.parent.parent / "wf-audit" / "scripts")
    if _doi_validator_dir not in sys.path:
        sys.path.insert(0, _doi_validator_dir)
    from doi_validator import normalize_doi, is_valid_doi_format, validate_paper_dois
    _HAS_DOI_VALIDATOR = True
except ImportError:
    pass

def validate_case_card(case_path: Path) -> list[str]:
    """Validate a single case card JSON file. Returns list of error messages."""
    errors = []
    try:
        with open(case_path, 'r', encoding='utf-8') as f:
            case = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return [f"Cannot read {case_path.name}: {e}"]

    # Required top-level fields
    for field in ['case_id', 'metadata', 'steps', 'completeness']:
        if field not in case:
            errors.append(f"{case_path.name}: missing required field '{field}'")

    # Metadata required fields
    meta = case.get('metadata', {})
    for field in ['title', 'year', 'core_technique']:
        if not meta.get(field):
            errors.append(f"{case_path.name}: metadata.{field} is empty")

    # Steps validation
    steps = case.get('steps', [])
    if not steps:
        errors.append(f"{case_path.name}: no steps defined")
    for i, step in enumerate(steps):
        if not step.get('step_name'):
            errors.append(f"{case_path.name}: step {i+1} missing step_name")

    return errors


def validate_uo_mapping(mapping_path: Path) -> list[str]:
    """Validate UO mapping JSON. Returns list of error messages."""
    errors = []
    try:
        with open(mapping_path, 'r', encoding='utf-8') as f:
            mapping = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return [f"Cannot read uo_mapping.json: {e}"]

    mappings = mapping.get('mappings', mapping if isinstance(mapping, list) else [])
    if isinstance(mappings, dict):
        mappings = list(mappings.values()) if mappings else []

    for item in mappings if isinstance(mappings, list) else []:
        if isinstance(item, dict):
            if not item.get('uo_id'):
                errors.append(f"UO mapping entry missing uo_id")
            if not item.get('case_refs') and not item.get('source_cases'):
                errors.append(f"UO {item.get('uo_id', '?')}: no case_refs")

    return errors


def validate_variant_files(workflow_dir: Path) -> list[str]:
    """Validate variant JSON files have at least 2 supporting cases."""
    errors = []
    variant_dir = workflow_dir / '04_workflow'
    if not variant_dir.exists():
        return ["04_workflow/ directory not found"]

    variant_files = list(variant_dir.glob('variant_V*.json'))
    if not variant_files:
        errors.append("No variant files found in 04_workflow/")
        return errors

    for vf in variant_files:
        try:
            with open(vf, 'r', encoding='utf-8') as f:
                variant = json.load(f)
            cases = variant.get('case_ids', variant.get('supporting_cases', variant.get('case_refs', [])))
            if len(cases) < 2:
                errors.append(f"{vf.name}: only {len(cases)} supporting cases (min 2)")
        except (json.JSONDecodeError, FileNotFoundError):
            errors.append(f"Cannot read {vf.name}")

    return errors


def validate_composition_data(comp_path: Path) -> list[str]:
    """Validate composition_data.json against Schema v4.0.0."""
    errors = []
    try:
        with open(comp_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        return [f"Cannot read composition_data.json: {e}"]

    # Schema v4.0.0 required fields
    for field in ['schema_version', 'workflow_id', 'workflow_name', 'category',
                  'domain', 'version', 'composition_date', 'statistics']:
        if field not in data:
            errors.append(f"composition_data.json: missing required field '{field}'")

    # Validate schema_version
    sv = data.get('schema_version', '')
    if sv and not str(sv).startswith('4.'):
        errors.append(f"composition_data.json: schema_version '{sv}' is not v4.x")

    # Validate composition_date format (YYYY-MM-DD)
    cd = data.get('composition_date', '')
    if cd and not re.match(r'^\d{4}-\d{2}-\d{2}$', str(cd)):
        errors.append(f"composition_data.json: composition_date '{cd}' not YYYY-MM-DD format")

    # Validate category
    cat = data.get('category', '')
    if cat and cat not in ('Build', 'Test', 'Design', 'Learn'):
        errors.append(f"composition_data.json: category '{cat}' not one of Build/Test/Design/Learn")

    # Check for deprecated fields
    for old_field in ['generated', 'created_at', 'created_date', 'cluster_result']:
        if old_field in data:
            errors.append(f"composition_data.json: deprecated field '{old_field}' present")

    # Validate statistics standard field names
    stats = data.get('statistics', {})
    if isinstance(stats, dict):
        standard = ['papers_analyzed', 'cases_collected', 'variants_identified', 'total_uos']
        deprecated_map = {
            'total_papers': 'papers_analyzed', 'papers_screened': 'papers_analyzed',
            'total_cases': 'cases_collected', 'cases_extracted': 'cases_collected',
            'total_variants': 'variants_identified', 'variants_composed': 'variants_identified',
            'total_uo_types': 'total_uos', 'uo_types_used': 'total_uos',
        }
        for old, new in deprecated_map.items():
            if old in stats:
                errors.append(f"composition_data.json: statistics uses deprecated '{old}', use '{new}'")

    return errors


def validate_report_sections(report_path: Path, language: str = "en") -> dict:
    """Validate that a composition report contains all required sections.

    Args:
        report_path: Path to composition_report.md or composition_report_ko.md
        language: "en" for English, "ko" for Korean

    Returns:
        {"valid": bool, "missing_sections": [int], "renamed_sections": [...], "errors": [...]}
    """
    REQUIRED_SECTIONS_EN = {
        1: "Workflow Overview",
        2: "Literature Search Summary",
        3: "Case Summary",
        4: "Common Workflow Structure",
        5: "Variants",
        6: "Variant Comparison",
        7: "Parameter Ranges",
        8: "Equipment & Software Inventory",
        9: "Evidence and Confidence",
        10: "Modularity and Service Integration",
        11: "Limitations and Notes",
        12: "Catalog Feedback",
        13: "Execution Metrics",
    }

    # Alternate acceptable names for backward compatibility
    ALTERNATE_NAMES_EN = {
        6: ["QC Checkpoints"],
        7: ["UO Mapping Summary"],
    }

    REQUIRED_SECTIONS_KO = {
        1: "워크플로 개요",
        2: "문헌 검색 요약",
        3: "사례 요약",
        4: "공통 워크플로 구조",
        5: "변이형",
        6: "변이형 비교",
        7: "파라미터 범위",
        8: "장비 및 소프트웨어 목록",
        9: "근거 및 신뢰도",
        10: "모듈성 및 서비스 통합",
        11: "제한사항 및 참고",
        12: "카탈로그 피드백",
        13: "실행 메트릭",
    }

    sections = REQUIRED_SECTIONS_KO if language == "ko" else REQUIRED_SECTIONS_EN
    alternates = {} if language == "ko" else ALTERNATE_NAMES_EN

    errors = []
    missing_sections = []
    renamed_sections = []

    try:
        content = report_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as e:
        return {
            "valid": False,
            "missing_sections": list(sections.keys()),
            "renamed_sections": [],
            "errors": [f"Cannot read report: {e}"],
        }

    # Extract ## N. headings
    heading_pattern = re.compile(r'^## (\d+)\.\s+(.+)$', re.MULTILINE)
    found_headings = {}
    for match in heading_pattern.finditer(content):
        num = int(match.group(1))
        name = match.group(2).strip()
        found_headings[num] = name

    # Check for missing and renamed sections
    for num, expected_name in sections.items():
        if num not in found_headings:
            missing_sections.append(num)
            errors.append(f"Missing section {num}: '{expected_name}'")
        else:
            found_name = found_headings[num]
            alt_names = alternates.get(num, [])
            all_acceptable = [expected_name] + alt_names
            if not any(found_name.lower() == acc.lower() for acc in all_acceptable):
                renamed_sections.append({
                    "num": num,
                    "expected": expected_name,
                    "found": found_name,
                })

    # Check order (sections should appear in ascending order in the document)
    found_nums = sorted(found_headings.keys())
    prev_pos = -1
    for num in found_nums:
        pattern = f"## {num}."
        pos = content.find(pattern)
        if pos < prev_pos:
            errors.append(f"Section {num} appears out of order")
        prev_pos = pos

    # If majority of sections are renamed, report is structurally non-standard
    # (likely LLM wrote directly instead of using generate_output.py)
    total_required = len(sections)
    if len(renamed_sections) > total_required // 2:
        errors.append(
            f"Report structurally non-standard: {len(renamed_sections)}/{total_required} "
            f"sections have non-canonical names (likely not generated by generate_output.py)"
        )

    is_valid = len(missing_sections) == 0 and len(renamed_sections) <= total_required // 2

    return {
        "valid": is_valid,
        "missing_sections": missing_sections,
        "renamed_sections": renamed_sections,
        "errors": errors,
    }


def validate_workflow(wf_dir: str | Path) -> dict:
    """Run all validations on a workflow composition directory.

    Returns dict with 'valid' bool, 'errors' list, 'warnings' list, 'stats' dict.
    """
    wf_dir = Path(wf_dir)
    errors = []
    warnings = []
    stats = {'cases': 0, 'variants': 0, 'papers': 0}

    # Check directory exists
    if not wf_dir.exists():
        return {'valid': False, 'errors': [f"Directory not found: {wf_dir}"],
                'warnings': [], 'stats': stats}

    # Validate case cards
    case_dir = wf_dir / '02_cases'
    if case_dir.exists():
        case_files = sorted(case_dir.glob('case_C*.json'))
        stats['cases'] = len(case_files)
        for cf in case_files:
            errors.extend(validate_case_card(cf))
        if len(case_files) < 3:
            warnings.append(f"Only {len(case_files)} cases (recommend >= 5)")
    else:
        errors.append("02_cases/ directory not found")

    # Validate UO mapping
    uo_path = wf_dir / '04_workflow' / 'uo_mapping.json'
    if uo_path.exists():
        errors.extend(validate_uo_mapping(uo_path))
    else:
        errors.append("04_workflow/uo_mapping.json not found")

    # Validate variants
    errors.extend(validate_variant_files(wf_dir))
    stats['variants'] = len(list((wf_dir / '04_workflow').glob('variant_V*.json'))) if (wf_dir / '04_workflow').exists() else 0

    # Validate composition_data.json
    comp_path = wf_dir / 'composition_data.json'
    if comp_path.exists():
        errors.extend(validate_composition_data(comp_path))
    else:
        errors.append("composition_data.json not found")

    # Validate papers
    paper_path = wf_dir / '01_papers' / 'paper_list.json'
    if paper_path.exists():
        try:
            with open(paper_path, 'r', encoding='utf-8') as f:
                papers_data = json.load(f)
            paper_list = papers_data if isinstance(papers_data, list) else papers_data.get('papers', [])
            stats['papers'] = len(paper_list)

            # DOI validation gate (format-only, no network calls)
            if _HAS_DOI_VALIDATOR and paper_list:
                doi_result = validate_paper_dois(paper_list, verify_online=False)
                if doi_result['invalid'] > 0:
                    warnings.append(
                        f"DOI issues: {doi_result['invalid']} invalid format, "
                        f"{doi_result['no_doi']} missing DOI out of {doi_result['total']} papers"
                    )
        except Exception:
            warnings.append("Could not parse paper_list.json for stats")

    # Check required output files
    for fname in ['composition_report.md', 'composition_data.json']:
        if not (wf_dir / fname).exists():
            errors.append(f"Missing output file: {fname}")

    # Validate report sections (English — blocking errors)
    report_path = wf_dir / 'composition_report.md'
    if report_path.exists():
        section_result = validate_report_sections(report_path, language="en")
        if not section_result['valid']:
            for err in section_result['errors']:
                errors.append(f"Report section: {err}")

    # Validate Korean report sections (non-blocking warnings)
    ko_report_path = wf_dir / 'composition_report_ko.md'
    if ko_report_path.exists():
        ko_result = validate_report_sections(ko_report_path, language="ko")
        if not ko_result['valid']:
            for err in ko_result['errors']:
                warnings.append(f"Korean report section: {err}")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings,
        'stats': stats
    }


def save_validation_report(wf_dir: str | Path) -> dict:
    """Run validation and save report to 00_metadata/validation_report.json."""
    wf_dir = Path(wf_dir)
    result = validate_workflow(wf_dir)

    report_path = wf_dir / '00_metadata' / 'validation_report.json'
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    return result


if __name__ == '__main__':
    if '--test' in sys.argv:
        import tempfile

        print("=== validate.py self-test ===\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Test 1: Valid report with all 13 sections (correct names)
            section_names = {
                1: "Workflow Overview", 2: "Literature Search Summary",
                3: "Case Summary", 4: "Common Workflow Structure",
                5: "Variants", 6: "QC Checkpoints",
                7: "UO Mapping Summary", 8: "Equipment & Software Inventory",
                9: "Evidence and Confidence", 10: "Modularity and Service Integration",
                11: "Limitations and Notes", 12: "Catalog Feedback",
                13: "Execution Metrics",
            }
            valid_report = Path(tmpdir) / "valid_report.md"
            lines = ["# WB_TEST: Test — Report\n"]
            for i in range(1, 14):
                lines.append(f"## {i}. {section_names[i]}\n\nContent for section {i}.\n")
            valid_report.write_text("\n".join(lines), encoding="utf-8")

            result = validate_report_sections(valid_report, language="en")
            assert result["valid"], f"Expected valid, got: {result}"
            assert len(result["missing_sections"]) == 0
            print("Test 1 PASS: Valid 13-section report passes")

            # Test 2: Report missing sections 9-13
            partial_report = Path(tmpdir) / "partial_report.md"
            lines = ["# WB_TEST: Test — Report\n"]
            for i in range(1, 9):
                lines.append(f"## {i}. {section_names[i]}\n\nContent.\n")
            partial_report.write_text("\n".join(lines), encoding="utf-8")

            result = validate_report_sections(partial_report, language="en")
            assert not result["valid"], f"Expected invalid, got: {result}"
            assert set(result["missing_sections"]) == {9, 10, 11, 12, 13}
            print(f"Test 2 PASS: Partial report caught missing sections: {result['missing_sections']}")

            # Test 3: Report with renamed section
            renamed_report = Path(tmpdir) / "renamed_report.md"
            lines = ["# WB_TEST: Test — Report\n"]
            for i in range(1, 14):
                if i == 1:
                    lines.append("## 1. Executive Summary\n\nContent.\n")
                else:
                    lines.append(f"## {i}. {section_names[i]}\n\nContent.\n")
            renamed_report.write_text("\n".join(lines), encoding="utf-8")

            result = validate_report_sections(renamed_report, language="en")
            assert result["valid"]  # Present but renamed — not blocking
            assert len(result["renamed_sections"]) >= 1
            print(f"Test 3 PASS: Renamed section detected: {result['renamed_sections']}")

            # Test 4: Non-existent file
            result = validate_report_sections(Path(tmpdir) / "nonexistent.md")
            assert not result["valid"]
            assert len(result["missing_sections"]) == 13
            print("Test 4 PASS: Non-existent file caught")

            print("\n=== All tests passed! ===")
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python3 validate.py <workflow_dir>")
        print("       python3 validate.py --test")
        sys.exit(1)

    result = save_validation_report(sys.argv[1])
    status = "PASS" if result['valid'] else "FAIL"
    print(f"Validation: {status}")
    print(f"  Cases: {result['stats']['cases']}, Variants: {result['stats']['variants']}, Papers: {result['stats']['papers']}")
    if result['errors']:
        print(f"  Errors ({len(result['errors'])}):")
        for e in result['errors'][:10]:
            print(f"    - {e}")
    if result['warnings']:
        print(f"  Warnings ({len(result['warnings'])}):")
        for w in result['warnings']:
            print(f"    - {w}")

    sys.exit(0 if result['valid'] else 1)
