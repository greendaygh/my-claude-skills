"""Report generation for workflow compositions.

Generates:
- composition_report.md (13 mandatory sections)
- composition_workflow.md (5 mandatory sections)
- Korean translations (*_ko.md)
"""

import json
from datetime import datetime, timezone
from pathlib import Path


# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> dict | list:
    """Load JSON file, returning empty dict on failure."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_cases(wf_dir: Path) -> list[dict]:
    """Load all case cards from 02_cases/."""
    cases_dir = wf_dir / "02_cases"
    if not cases_dir.exists():
        return []
    cases = []
    for f in sorted(cases_dir.glob("case_C*.json")):
        try:
            cases.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return cases


def _load_variants(wf_dir: Path) -> list[dict]:
    """Load variant files from 04_workflow/."""
    variants_dir = wf_dir / "04_workflow"
    if not variants_dir.exists():
        return []
    variants = []
    for f in sorted(variants_dir.glob("variant_*.json")):
        try:
            variants.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return variants


def _load_analysis(wf_dir: Path) -> dict:
    """Load analysis data from 03_analysis/."""
    for name in ("analysis_summary.json", "cross_case_analysis.json"):
        path = wf_dir / "03_analysis" / name
        if path.exists():
            return _load_json(path)
    return {}


# ---------------------------------------------------------------------------
# Section generators for composition_report.md
# ---------------------------------------------------------------------------

def _section_workflow_overview(comp: dict) -> str:
    """Section 1: Workflow Overview."""
    wf_id = comp.get("workflow_id", "")
    wf_name = comp.get("workflow_name", "")
    domain = comp.get("domain", "")
    category = comp.get("category", "")
    version = comp.get("version", "")
    date = comp.get("composition_date", "")
    schema = comp.get("schema_version", "")
    desc = comp.get("description", "")
    stats = comp.get("statistics", {})

    lines = [
        f"# {wf_id} {wf_name} -- Composition Report v{version}",
        "",
        "## Workflow Overview",
        "",
        f"**Workflow ID**: {wf_id}",
        f"**Name**: {wf_name}",
        f"**Domain**: {domain}",
        f"**Category**: {category}",
        f"**Version**: {version}",
        f"**Composition Date**: {date}",
        f"**Schema Version**: {schema}",
        "",
        desc,
        "",
        f"**Scope**: {comp.get('scope', desc[:200])}",
    ]
    return "\n".join(lines)


def _section_literature_search(comp: dict, papers: list) -> str:
    """Section 2: Literature Search Summary."""
    stats = comp.get("statistics", {})
    screening = stats.get("screening_stats", {})

    lines = [
        "## Literature Search Summary",
        "",
        f"**Databases searched**: OpenAlex, PubMed, Google Scholar",
        f"**Total screened**: {screening.get('total_screened', 'N/A')} papers",
        f"**Total selected**: {stats.get('papers_analyzed', len(papers))} papers "
        f"(selection rate: {screening.get('selection_rate', 'N/A')})",
        "",
        "| Paper | Year | Technique | Variant |",
        "|-------|------|-----------|---------|",
    ]

    for p in papers:
        pid = p.get("paper_id", p.get("id", ""))
        authors = p.get("authors", "")
        if isinstance(authors, list):
            authors = authors[0].split(",")[0] if authors else ""
        elif isinstance(authors, str):
            authors = authors.split(",")[0]
        year = p.get("year", "")
        tech = p.get("technique", "")[:60]
        variant = p.get("variant", "")
        lines.append(f"| {pid} {authors} et al. | {year} | {tech} | {variant} |")

    return "\n".join(lines)


def _section_case_summary(comp: dict, cases: list) -> str:
    """Section 3: Case Summary."""
    stats = comp.get("statistics", {})

    # Group by variant
    variant_groups: dict[str, list] = {}
    for c in cases:
        v = c.get("variant", c.get("metadata", {}).get("variant", ""))
        if isinstance(v, list):
            v = v[0] if v else "Unknown"
        variant_groups.setdefault(v, []).append(c)

    lines = [
        "## Case Summary",
        "",
        f"**Total cases**: {stats.get('cases_collected', len(cases))}",
        "",
        "| Variant | Cases | Count |",
        "|---------|-------|-------|",
    ]

    for v_id, v_cases in sorted(variant_groups.items()):
        case_ids = ", ".join(c.get("case_id", "") for c in v_cases[:5])
        if len(v_cases) > 5:
            case_ids += "..."
        lines.append(f"| {v_id} | {case_ids} | {len(v_cases)} |")

    return "\n".join(lines)


def _section_common_workflow(cases: list) -> str:
    """Section 4: Common Workflow Structure."""
    # Collect step names across all cases
    step_freq: dict[int, dict[str, int]] = {}
    for c in cases:
        for step in c.get("steps", []):
            pos = step.get("step_number", 0)
            name = step.get("step_name", "")
            if pos and name:
                step_freq.setdefault(pos, {})
                step_freq[pos][name] = step_freq[pos].get(name, 0) + 1

    lines = [
        "## Common Workflow Structure",
        "",
        "| Position | Function | Frequency | Category |",
        "|----------|----------|-----------|----------|",
    ]

    total = len(cases) if cases else 1
    for pos in sorted(step_freq.keys()):
        names = step_freq[pos]
        top_name = max(names, key=names.get) if names else ""
        freq = sum(names.values())
        pct = freq / total * 100
        cat = "Mandatory" if pct > 80 else "Optional"
        lines.append(f"| {pos} | {top_name} | {freq}/{total} ({pct:.0f}%) | {cat} |")

    return "\n".join(lines)


def _section_variants(variants: list, cases: list) -> str:
    """Section 5: Variants."""
    lines = ["## Variants", ""]

    if not variants:
        # Generate from case data
        variant_groups: dict[str, list] = {}
        for c in cases:
            v = c.get("variant", "")
            if isinstance(v, list):
                v = v[0] if v else "Unknown"
            variant_groups.setdefault(v, []).append(c)

        for v_id, v_cases in sorted(variant_groups.items()):
            v_name = v_id
            lines.append(f"### {v_name}")
            lines.append("")
            lines.append(f"**Cases**: {len(v_cases)}")
            lines.append("")
    else:
        for v in variants:
            v_id = v.get("variant_id", "")
            v_name = v.get("variant_name", v_id)
            lines.append(f"### {v_id}: {v_name}")
            lines.append("")
            if v.get("description"):
                lines.append(v["description"])
                lines.append("")
            if v.get("uo_sequence"):
                seq = [s if isinstance(s, str) else s.get("name", s.get("uo_id", str(s))) for s in v["uo_sequence"]]
                lines.append(f"**UO Sequence**: {' -> '.join(seq)}")
                lines.append("")

    return "\n".join(lines)


def _section_variant_comparison(variants: list, cases: list) -> str:
    """Section 6: Variant Comparison."""
    lines = [
        "## Variant Comparison",
        "",
        "| Feature | " + " | ".join(
            v.get("variant_id", f"V{i+1}") for i, v in enumerate(variants)
        ) + " |" if variants else "| Feature |",
        "|---------|" + "|".join("---------|" for _ in variants) if variants else "|---------|",
    ]

    if not variants:
        # Simple comparison from cases
        variant_groups: dict[str, list] = {}
        for c in cases:
            v = c.get("variant", "")
            if isinstance(v, list):
                v = v[0] if v else "?"
            variant_groups.setdefault(v, []).append(c)

        header = "| Feature | " + " | ".join(sorted(variant_groups.keys())) + " |"
        sep = "|---------|" + "|".join("---------|" for _ in variant_groups)
        count_row = "| Cases | " + " | ".join(
            str(len(cs)) for _, cs in sorted(variant_groups.items())
        ) + " |"
        lines = ["## Variant Comparison", "", header, sep, count_row]

    return "\n".join(lines)


def _section_parameter_ranges(cases: list) -> str:
    """Section 7: Parameter Ranges."""
    lines = ["## Parameter Ranges", ""]

    # Collect conditions across all steps
    all_conditions = []
    for c in cases:
        for step in c.get("steps", []):
            cond = step.get("conditions", "")
            if cond and cond != "[미기재]":
                all_conditions.append(cond)

    if all_conditions:
        lines.append("Key parameters observed across cases:")
        lines.append("")
        for cond in all_conditions[:10]:
            cond_str = cond if isinstance(cond, str) else json.dumps(cond, ensure_ascii=False)
            lines.append(f"- {cond_str[:100]}")
    else:
        lines.append("Parameter details available in individual case cards.")

    return "\n".join(lines)


def _section_equipment_inventory(cases: list) -> str:
    """Section 8: Equipment & Software Inventory."""
    equip_set: dict[str, dict] = {}
    sw_set: dict[str, dict] = {}

    for c in cases:
        for step in c.get("steps", []):
            for e in step.get("equipment", []):
                if isinstance(e, str):
                    if e and e != "[미기재]":
                        equip_set.setdefault(e, {"model": "", "manufacturer": ""})
                    continue
                name = e.get("name", "")
                if name and name != "[미기재]":
                    equip_set[name] = {
                        "model": e.get("model", ""),
                        "manufacturer": e.get("manufacturer", ""),
                    }
            for s in step.get("software", []):
                if isinstance(s, str):
                    if s and s != "[미기재]":
                        sw_set.setdefault(s, {"version": "", "developer": ""})
                    continue
                name = s.get("name", "")
                if name and name != "[미기재]":
                    sw_set[name] = {
                        "version": s.get("version", ""),
                        "developer": s.get("developer", ""),
                    }

    lines = [
        "## Equipment & Software Inventory",
        "",
        "### Equipment",
        "",
        "| Name | Model | Manufacturer |",
        "|------|-------|-------------|",
    ]
    for name, info in sorted(equip_set.items()):
        lines.append(f"| {name} | {info['model']} | {info['manufacturer']} |")

    lines.extend(["", "### Software", "", "| Name | Version | Developer |", "|------|---------|-----------|"])
    for name, info in sorted(sw_set.items()):
        lines.append(f"| {name} | {info['version']} | {info['developer']} |")

    return "\n".join(lines)


def _section_evidence_confidence(comp: dict, cases: list) -> str:
    """Section 9: Evidence and Confidence."""
    stats = comp.get("statistics", {})
    confidence = stats.get("confidence_score", 0)

    lines = [
        "## Evidence and Confidence",
        "",
        f"**Confidence Score**: {confidence}",
        f"**Papers Analyzed**: {stats.get('papers_analyzed', 0)}",
        f"**Cases Collected**: {stats.get('cases_collected', len(cases))}",
        "",
    ]

    # Completeness distribution
    scores = []
    for c in cases:
        comp_block = c.get("completeness", {})
        score = comp_block.get("score", 0)
        if isinstance(score, (int, float)):
            scores.append(score)

    if scores:
        avg = sum(scores) / len(scores)
        lines.append(f"**Average case completeness**: {avg:.2f}")
        lines.append(f"**Min/Max completeness**: {min(scores):.2f} / {max(scores):.2f}")

    return "\n".join(lines)


def _section_modularity(comp: dict) -> str:
    """Section 10: Modularity and Service Integration."""
    modularity = comp.get("modularity", {})

    lines = [
        "## Modularity and Service Integration",
        "",
        "### Boundary Inputs",
        "",
    ]

    for inp in modularity.get("boundary_inputs", []):
        if isinstance(inp, str):
            lines.append(f"- {inp}")
        else:
            name = inp.get("name", "")
            desc = inp.get("description", "")
            lines.append(f"- **{name}**: {desc}")

    lines.extend(["", "### Boundary Outputs", ""])
    for out in modularity.get("boundary_outputs", []):
        if isinstance(out, str):
            lines.append(f"- {out}")
        else:
            name = out.get("name", "")
            desc = out.get("description", "")
            lines.append(f"- **{name}**: {desc}")

    if modularity.get("service_chains"):
        lines.extend(["", "### Service Chains", ""])
        for chain in modularity.get("service_chains", []):
            if isinstance(chain, str):
                lines.append(f"- {chain}")
            else:
                lines.append(f"- {chain.get('name', str(chain))}")

    return "\n".join(lines)


def _section_limitations(comp: dict) -> str:
    """Section 11: Limitations and Notes."""
    lines = [
        "## Limitations and Notes",
        "",
        "- Case cards enriched via PubMed abstracts; full-text access may reveal additional details",
        "- Equipment model/manufacturer fields may be incomplete where papers do not specify",
        "- Conditions extracted from abstracts may not capture all experimental parameters",
    ]

    if comp.get("limitations"):
        for lim in comp["limitations"]:
            lines.append(f"- {lim}")

    return "\n".join(lines)


def _section_catalog_feedback(comp: dict) -> str:
    """Section 12: Catalog Feedback."""
    lines = [
        "## Catalog Feedback",
        "",
    ]

    if comp.get("catalog_feedback"):
        for fb in comp["catalog_feedback"]:
            lines.append(f"- {fb}")
    else:
        lines.append("No catalog feedback at this time.")

    return "\n".join(lines)


def _section_execution_metrics(comp: dict) -> str:
    """Section 13: Execution Metrics."""
    stats = comp.get("statistics", {})
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "## Execution Metrics",
        "",
        f"- **Report generated**: {now}",
        f"- **Schema version**: {comp.get('schema_version', '')}",
        f"- **Composition version**: {comp.get('version', '')}",
        f"- **Papers analyzed**: {stats.get('papers_analyzed', 0)}",
        f"- **Cases collected**: {stats.get('cases_collected', 0)}",
        f"- **Variants identified**: {stats.get('variants_identified', 0)}",
        f"- **UO types**: {stats.get('total_uos', 0)}",
        f"- **QC checkpoints**: {stats.get('qc_checkpoints', 0)}",
        f"- **Confidence score**: {stats.get('confidence_score', 0)}",
        f"- **Enrichment**: wf-migrate v2.2.0",
    ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main report generator
# ---------------------------------------------------------------------------

def generate_composition_report(wf_dir: Path) -> str:
    """Generate composition_report.md with all 13 mandatory sections.

    Reads data from:
    - composition_data.json
    - 01_papers/paper_list.json
    - 02_cases/case_C*.json
    - 04_workflow/variant_*.json
    - 03_analysis/

    Returns the markdown string.
    """
    wf_dir = Path(wf_dir)
    comp = _load_json(wf_dir / "composition_data.json")
    paper_data = _load_json(wf_dir / "01_papers" / "paper_list.json")
    if not paper_data:
        paper_data = _load_json(wf_dir / "01_literature" / "paper_list.json")

    papers = paper_data.get("papers", []) if isinstance(paper_data, dict) else paper_data
    cases = _load_cases(wf_dir)
    variants = _load_variants(wf_dir)

    sections = [
        _section_workflow_overview(comp),
        _section_literature_search(comp, papers),
        _section_case_summary(comp, cases),
        _section_common_workflow(cases),
        _section_variants(variants, cases),
        _section_variant_comparison(variants, cases),
        _section_parameter_ranges(cases),
        _section_equipment_inventory(cases),
        _section_evidence_confidence(comp, cases),
        _section_modularity(comp),
        _section_limitations(comp),
        _section_catalog_feedback(comp),
        _section_execution_metrics(comp),
    ]

    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Workflow document generator
# ---------------------------------------------------------------------------

def _wf_section_skeleton(cases: list) -> str:
    """Section 1: Common Workflow Skeleton."""
    step_freq: dict[int, dict[str, int]] = {}
    for c in cases:
        for step in c.get("steps", []):
            pos = step.get("step_number", 0)
            name = step.get("step_name", "")
            if pos and name:
                step_freq.setdefault(pos, {})
                step_freq[pos][name] = step_freq[pos].get(name, 0) + 1

    lines = [
        "## Common Workflow Skeleton",
        "",
        "| Step | Name | Frequency |",
        "|------|------|-----------|",
    ]

    total = len(cases) if cases else 1
    for pos in sorted(step_freq.keys()):
        names = step_freq[pos]
        top_name = max(names, key=names.get) if names else ""
        freq = sum(names.values())
        lines.append(f"| {pos} | {top_name} | {freq}/{total} |")

    return "\n".join(lines)


def _wf_section_variants(variants: list, cases: list) -> str:
    """Section 2: Variants (with UO sequence tables)."""
    lines = ["## Variants", ""]

    if variants:
        for v in variants:
            v_id = v.get("variant_id", "")
            v_name = v.get("variant_name", v_id)
            lines.append(f"### {v_id}: {v_name}")
            lines.append("")

            uo_seq = v.get("uo_sequence", [])
            if uo_seq:
                lines.append("| Step | UO ID | UO Name | Key Equipment |")
                lines.append("|------|-------|---------|---------------|")
                for i, uo in enumerate(uo_seq, 1):
                    if isinstance(uo, dict):
                        lines.append(
                            f"| {i} | {uo.get('uo_id', '')} | {uo.get('uo_name', '')} | "
                            f"{uo.get('key_equipment', '')} |"
                        )
                    else:
                        lines.append(f"| {i} | {uo} | | |")
                lines.append("")

            # QC checkpoints
            qc = v.get("qc_checkpoints", [])
            if qc:
                lines.append("**QC Checkpoints**:")
                for q in qc:
                    if isinstance(q, dict):
                        lines.append(f"- {q.get('name', '')}: {q.get('criteria', '')}")
                    else:
                        lines.append(f"- {q}")
                lines.append("")
    else:
        lines.append("See case cards for variant-specific details.")

    return "\n".join(lines)


def _wf_section_parameter_ref(cases: list) -> str:
    """Section 3: Parameter Quick-Reference."""
    lines = ["## Parameter Quick-Reference", ""]

    # Collect key parameters
    params: dict[str, set] = {}
    for c in cases:
        for step in c.get("steps", []):
            cond = step.get("conditions", "")
            if not cond or cond == "[미기재]":
                continue
            if not isinstance(cond, str):
                continue  # dict/list conditions cannot be key-value parsed
            for part in cond.split(","):
                part = part.strip()
                if ":" in part:
                    key, val = part.split(":", 1)
                    params.setdefault(key.strip(), set()).add(val.strip())

    if params:
        lines.append("| Parameter | Range |")
        lines.append("|-----------|-------|")
        for key, vals in sorted(params.items())[:15]:
            vals_str = ", ".join(sorted(vals)[:5])
            lines.append(f"| {key} | {vals_str} |")
    else:
        lines.append("See individual case cards for parameter details.")

    return "\n".join(lines)


def _wf_section_boundary_io(comp: dict) -> str:
    """Section 4: Boundary I/O."""
    modularity = comp.get("modularity", {})

    lines = ["## Boundary I/O", "", "### Inputs", ""]
    for inp in modularity.get("boundary_inputs", []):
        if isinstance(inp, str):
            lines.append(f"- {inp}")
        else:
            lines.append(f"- **{inp.get('name', '')}**: {inp.get('description', '')} "
                         f"[{inp.get('format', '')}]")

    lines.extend(["", "### Outputs", ""])
    for out in modularity.get("boundary_outputs", []):
        if isinstance(out, str):
            lines.append(f"- {out}")
        else:
            lines.append(f"- **{out.get('name', '')}**: {out.get('description', '')} "
                         f"[{out.get('format', '')}]")

    return "\n".join(lines)


def _wf_section_service_chains(comp: dict) -> str:
    """Section 5: Service Chains."""
    modularity = comp.get("modularity", {})
    chains = modularity.get("service_chains", [])

    lines = ["## Service Chains", ""]

    if chains:
        for chain in chains:
            if isinstance(chain, dict):
                lines.append(f"- **{chain.get('name', '')}**: {chain.get('description', '')}")
            else:
                lines.append(f"- {chain}")
    else:
        upstream = modularity.get("upstream_workflows", [])
        downstream = modularity.get("downstream_workflows", [])
        if upstream:
            lines.append(f"**Upstream**: {', '.join(upstream)}")
        if downstream:
            lines.append(f"**Downstream**: {', '.join(downstream)}")
        if not upstream and not downstream:
            lines.append("No explicit service chains defined.")

    return "\n".join(lines)


def generate_composition_workflow(wf_dir: Path) -> str:
    """Generate composition_workflow.md with all 5 mandatory sections.

    Returns the markdown string.
    """
    wf_dir = Path(wf_dir)
    comp = _load_json(wf_dir / "composition_data.json")
    cases = _load_cases(wf_dir)
    variants = _load_variants(wf_dir)

    wf_id = comp.get("workflow_id", "")
    wf_name = comp.get("workflow_name", "")

    header = f"# {wf_id} {wf_name} -- Composition Workflow\n"

    sections = [
        header,
        _wf_section_skeleton(cases),
        _wf_section_variants(variants, cases),
        _wf_section_parameter_ref(cases),
        _wf_section_boundary_io(comp),
        _wf_section_service_chains(comp),
    ]

    return "\n\n".join(sections) + "\n"


# ---------------------------------------------------------------------------
# Korean translation (simple wrapper)
# ---------------------------------------------------------------------------

_KO_SECTION_MAP = {
    "Workflow Overview": "워크플로 개요",
    "Literature Search Summary": "문헌 검색 요약",
    "Case Summary": "사례 요약",
    "Common Workflow Structure": "공통 워크플로 구조",
    "Variants": "변이형",
    "Variant Comparison": "변이형 비교",
    "Parameter Ranges": "파라미터 범위",
    "Equipment & Software Inventory": "장비 및 소프트웨어 목록",
    "Evidence and Confidence": "근거 및 신뢰도",
    "Modularity and Service Integration": "모듈성 및 서비스 통합",
    "Limitations and Notes": "제한사항 및 참고",
    "Catalog Feedback": "카탈로그 피드백",
    "Execution Metrics": "실행 지표",
    "Common Workflow Skeleton": "공통 워크플로 골격",
    "Parameter Quick-Reference": "파라미터 참조표",
    "Boundary I/O": "경계 입출력",
    "Service Chains": "서비스 체인",
    "Composition Report": "구성 보고서",
    "Composition Workflow": "구성 워크플로",
}


def translate_section_headers(md_text: str) -> str:
    """Translate English section headers to Korean.

    Only translates ## headings — leaves content unchanged.
    """
    lines = md_text.split("\n")
    translated = []

    for line in lines:
        if line.startswith("## "):
            heading = line[3:].strip()
            ko = _KO_SECTION_MAP.get(heading, heading)
            translated.append(f"## {ko}")
        elif line.startswith("# ") and "Composition Report" in line:
            translated.append(line.replace("Composition Report", "구성 보고서"))
        elif line.startswith("# ") and "Composition Workflow" in line:
            translated.append(line.replace("Composition Workflow", "구성 워크플로"))
        else:
            translated.append(line)

    return "\n".join(translated)


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------

def write_reports(wf_dir: Path) -> dict:
    """Generate and write all report files.

    Generates:
    - composition_report.md
    - composition_workflow.md
    - composition_report_ko.md
    - composition_workflow_ko.md

    Returns dict with file paths and status.
    """
    wf_dir = Path(wf_dir)
    results = {}

    # English reports
    report_md = generate_composition_report(wf_dir)
    report_path = wf_dir / "composition_report.md"
    report_path.write_text(report_md, encoding="utf-8")
    results["composition_report"] = str(report_path)

    workflow_md = generate_composition_workflow(wf_dir)
    workflow_path = wf_dir / "composition_workflow.md"
    workflow_path.write_text(workflow_md, encoding="utf-8")
    results["composition_workflow"] = str(workflow_path)

    # Korean translations
    report_ko = translate_section_headers(report_md)
    report_ko_path = wf_dir / "composition_report_ko.md"
    report_ko_path.write_text(report_ko, encoding="utf-8")
    results["composition_report_ko"] = str(report_ko_path)

    workflow_ko = translate_section_headers(workflow_md)
    workflow_ko_path = wf_dir / "composition_workflow_ko.md"
    workflow_ko_path.write_text(workflow_ko, encoding="utf-8")
    results["composition_workflow_ko"] = str(workflow_ko_path)

    return results
