#!/usr/bin/env python3
"""
generate_output.py — Generate final output documents for workflow composition.

Produces:
  - composition_report.md (human-readable markdown report, English)
  - composition_data.json (machine-readable JSON)
  - composition_workflow.md (human-readable workflow reference card, English)
  - Updates index.json (global workflow index)

v2.0.0: Simplified architecture — removed Korean translation (delegated to OMC writer),
        removed expert panel references (replaced by peer-review skill),
        removed upgrade delta complexity, removed execution metrics section.
        Focus: Sections 1-13 (Overview through Execution Metrics).
"""

import json
from pathlib import Path
from datetime import datetime

__version__ = "3.0.0"

SCHEMA_VERSION = "4.0.0"

# Standard top-level key order for composition_data.json
STANDARD_KEY_ORDER = [
    "schema_version", "workflow_id", "workflow_name", "category", "domain",
    "version", "composition_date", "description",
    "statistics", "modularity", "common_skeleton", "variants",
    "uo_mapping", "qc_checkpoints", "related_workflows",
    "parameter_ranges", "equipment_software_inventory",
    "limitations", "catalog_feedback", "confidence_score",
]


def _compute_confidence(variants: dict) -> float:
    """Compute confidence score from evidence tags across all variants.

    Scores by tag:
      literature-direct: 1.0, literature-consensus: 0.95,
      literature-supplementary: 0.85, manufacturer-protocol: 0.80,
      expert-inference: 0.70, catalog-default: 0.60
    Returns weighted average, default 0.80 if no tags found.
    """
    TAG_SCORES = {
        "literature-direct": 1.0,
        "literature-consensus": 0.95,
        "literature-supplementary": 0.85,
        "manufacturer-protocol": 0.80,
        "expert-inference": 0.70,
        "catalog-default": 0.60,
    }
    scores = []
    for vid, vd in variants.items():
        for uo in vd.get("uo_sequence", []):
            tag = uo.get("evidence_tag", "")
            if tag in TAG_SCORES:
                scores.append(TAG_SCORES[tag])
            # Check component-level tags
            for comp in uo.get("components", {}).values():
                if isinstance(comp, dict):
                    ctag = comp.get("evidence_tag", "")
                    if ctag in TAG_SCORES:
                        scores.append(TAG_SCORES[ctag])
    if not scores:
        return 0.80
    return round(sum(scores) / len(scores), 2)


def _reorder_keys(data: dict) -> dict:
    """Reorder dict keys to match STANDARD_KEY_ORDER, appending extras."""
    ordered = {}
    for k in STANDARD_KEY_ORDER:
        if k in data:
            ordered[k] = data[k]
    for k, v in data.items():
        if k not in ordered:
            ordered[k] = v
    return ordered


def load_json(filepath: str | Path) -> dict:
    """Load a JSON file, returning empty dict on error."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def generate_limitations(wf_dir: str | Path) -> tuple[list, dict]:
    """
    Analyze completed composition for limitations and catalog feedback.

    Reads composition_report.md Section 11, uo_mapping.json, case_summary.json,
    and variant files to identify:
    - Data/methodology/coverage limitations
    - Catalog feedback (UO issues, component gaps)

    Returns:
        (limitations_list, catalog_feedback_dict)
    """
    wf_dir = Path(wf_dir)

    uo_mapping = load_json(wf_dir / "04_workflow" / "uo_mapping.json")
    case_summary = load_json(wf_dir / "02_cases" / "case_summary.json")

    # --- Limitations ---
    limitations = []

    # Data limitation: case count
    total_cases = case_summary.get("total_cases", 0)
    if total_cases < 15:
        limitations.append({
            "category": "data",
            "description": f"Limited case coverage ({total_cases} cases). Results may not capture full variation.",
            "case_refs": [],
        })

    # Data limitation: organism bias
    by_organism = case_summary.get("by_organism", {})
    if by_organism:
        total = sum(by_organism.values())
        for org, count in by_organism.items():
            if total > 0 and count / total > 0.5:
                limitations.append({
                    "category": "data",
                    "description": f"Organism bias: {org} represents {count}/{total} ({count/total:.0%}) of cases.",
                    "case_refs": [],
                })

    # Methodology limitation: expert-inference items
    variant_files = sorted((wf_dir / "04_workflow").glob("variant_V*.json"))
    expert_inference_count = 0
    for vf in variant_files:
        vd = load_json(vf)
        for uo in vd.get("uo_sequence", []):
            components = uo.get("components", {})
            for comp_name, comp_val in components.items():
                if isinstance(comp_val, dict):
                    if comp_val.get("evidence_tag") == "expert-inference":
                        expert_inference_count += 1
                elif isinstance(comp_val, list):
                    for item in comp_val:
                        if isinstance(item, dict) and item.get("evidence_tag") == "expert-inference":
                            expert_inference_count += 1

    if expert_inference_count > 0:
        limitations.append({
            "category": "methodology",
            "description": f"{expert_inference_count} component values rely on expert-inference rather than direct literature evidence.",
            "case_refs": [],
        })

    # --- Catalog Feedback ---
    uo_issues = []
    component_gaps = []

    # Check UO mapping scores for weak matches
    mappings = uo_mapping.get("mappings", uo_mapping.get("uo_mappings", []))
    if isinstance(mappings, list):
        for m in mappings:
            score = m.get("score", m.get("multi_signal_score", 1.0))
            if score < 0.7:
                uo_issues.append({
                    "category": "mapping",
                    "uo_id": m.get("uo_id", ""),
                    "description": f"Weak mapping (score={score:.2f}). Step may need a new or different UO.",
                    "evidence": m.get("case_refs", []),
                    "suggested_action": "Review mapping; consider creating new UO if no good match exists.",
                })

    # Check for systematically [미기재] components across all variants
    component_missing = {}  # {(uo_id, component): [variant_ids]}
    for vf in variant_files:
        vd = load_json(vf)
        vid = vd.get("variant_id", vf.stem)
        for uo in vd.get("uo_sequence", []):
            uo_id = uo.get("uo_id", "")
            components = uo.get("components", {})
            for comp_name, comp_val in components.items():
                is_missing = False
                if isinstance(comp_val, str) and "[미기재]" in comp_val:
                    is_missing = True
                elif isinstance(comp_val, dict) and "[미기재]" in str(comp_val.get("value", "")):
                    is_missing = True
                if is_missing:
                    key = (uo_id, comp_name)
                    component_missing.setdefault(key, []).append(vid)

    # If a component is missing in ALL variants, it's a systematic gap
    num_variants = len(variant_files)
    for (uo_id, comp_name), variants in component_missing.items():
        if len(variants) >= num_variants and num_variants > 0:
            component_gaps.append({
                "uo_id": uo_id,
                "component": comp_name,
                "gap_description": f"Systematically [미기재] across all {num_variants} variants.",
                "affected_variants": variants,
            })

    summary = {
        "total_findings": len(uo_issues) + len(component_gaps),
        "critical": len([i for i in uo_issues if i.get("category") == "mapping"]),
        "improvements": len(uo_issues),
    }

    catalog_feedback = {
        "uo_issues": uo_issues,
        "component_gaps": component_gaps,
        "summary": summary,
    }

    return limitations, catalog_feedback


def generate_composition_report(wf_dir: str | Path) -> str:
    """
    Generate composition_report.md from all workflow artifacts.

    Sections 1-13:
    1. Workflow Overview
    2. Literature Search Summary
    3. Case Summary
    4. Common Workflow Structure
    5. Variants
    6. QC Checkpoints
    7. UO Mapping Summary
    8. Equipment & Software Inventory
    9. Evidence and Confidence
    10. Modularity and Service Integration
    11. Limitations and Notes
    12. Catalog Feedback
    13. Execution Metrics
    """
    wf_dir = Path(wf_dir)

    # Load all data
    context = load_json(wf_dir / "00_metadata" / "workflow_context.json")
    paper_list = load_json(wf_dir / "01_papers" / "paper_list.json")
    case_summary = load_json(wf_dir / "02_cases" / "case_summary.json")
    common_pattern = load_json(wf_dir / "03_analysis" / "common_pattern.json")
    uo_mapping = load_json(wf_dir / "04_workflow" / "uo_mapping.json")
    qc_checkpoints = load_json(wf_dir / "04_workflow" / "qc_checkpoints.json")

    wf_id = context.get("workflow_id", "UNKNOWN")
    wf_name = context.get("workflow_name", "UNKNOWN")
    domain = context.get("domain", "UNKNOWN")

    # Count variants
    variant_files = sorted((wf_dir / "04_workflow").glob("variant_V*.json"))
    num_variants = len(variant_files)
    total_uos = 0
    variants_data = []
    for vf in variant_files:
        vd = load_json(vf)
        variants_data.append(vd)
        total_uos += len(vd.get("uo_sequence", []))

    num_qc = len(qc_checkpoints.get("checkpoints", []))
    num_papers = len(paper_list.get("papers", []))
    num_cases = case_summary.get("total_cases", 0)

    # Build report
    report_lines = [
        f"# {wf_id}: {wf_name} — Workflow Composition Report",
        "",
        f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Domain**: {domain}",
        f"**Papers analyzed**: {num_papers}",
        f"**Cases collected**: {num_cases}",
        f"**Variants identified**: {num_variants}",
        f"**Total UOs**: {total_uos}",
        f"**QC Checkpoints**: {num_qc}",
        "",
        "---",
        "",
        "## 1. Workflow Overview",
        "",
        context.get("description", ""),
        "",
        "## 2. Literature Search Summary",
        "",
        f"- Cases extracted: {num_cases}",
        f"- Papers analyzed: {num_papers}",
        "",
        "## 3. Case Summary",
        "",
    ]

    # Technique distribution
    by_technique = case_summary.get("by_technique", {})
    if by_technique:
        report_lines.append("### Distribution by Technique")
        report_lines.append("")
        report_lines.append("| Technique | Cases |")
        report_lines.append("|-----------|-------|")
        for tech, count in sorted(by_technique.items(), key=lambda x: -x[1]):
            report_lines.append(f"| {tech} | {count} |")
        report_lines.append("")

    # Organism distribution
    by_organism = case_summary.get("by_organism", {})
    if by_organism:
        report_lines.append("### Distribution by Organism")
        report_lines.append("")
        report_lines.append("| Organism | Cases |")
        report_lines.append("|----------|-------|")
        for org, count in sorted(by_organism.items(), key=lambda x: -x[1]):
            report_lines.append(f"| {org} | {count} |")
        report_lines.append("")

    # Common workflow
    report_lines.extend([
        "## 4. Common Workflow Structure",
        "",
    ])

    mandatory = common_pattern.get("mandatory_steps", [])
    if mandatory:
        report_lines.append("### Mandatory Steps")
        report_lines.append("")
        report_lines.append("| Position | Function | Presence |")
        report_lines.append("|----------|----------|----------|")
        for step in mandatory:
            pos = step.get("position", "?")
            func = step.get("function", "") or ", ".join(step.get("step_name_variants", {}).keys())
            ratio = step.get("presence_ratio", 0)
            report_lines.append(f"| {pos} | {func} | {ratio:.0%} |")
        report_lines.append("")

    branch_points = common_pattern.get("branch_points", [])
    if branch_points:
        report_lines.append("### Branch Points")
        report_lines.append("")
        for bp in branch_points:
            branches = bp.get("branches", [])
            report_lines.append(f"- Position {bp.get('position', '?')}: {' / '.join(branches)}")
        report_lines.append("")

    # Variants
    report_lines.extend([
        "## 5. Variants",
        "",
    ])

    for vd in variants_data:
        vid = vd.get("variant_id", "?")
        vname = vd.get("name", "?")
        case_ids = vd.get("case_ids", [])
        report_lines.extend([
            f"### {vid}: {vname}",
            "",
            f"**Cases**: {', '.join(case_ids)}",
            "",
        ])

        uo_seq = vd.get("uo_sequence", [])
        if uo_seq:
            report_lines.append("#### UO Sequence")
            report_lines.append("")
            report_lines.append("| # | UO ID | Name | Type |")
            report_lines.append("|---|-------|------|------|")
            for i, uo in enumerate(uo_seq, 1):
                report_lines.append(
                    f"| {i} | {uo.get('uo_id', '')} | {uo.get('instance_label', uo.get('uo_name', ''))} | {uo.get('type', '')} |"
                )
            report_lines.append("")

        # Reference visualization
        png_path = f"05_visualization/workflow_graph_{vid}.png"
        if (wf_dir / png_path).exists():
            report_lines.append(f"![{vid} Workflow Graph]({png_path})")
            report_lines.append("")

    # QC Checkpoints
    report_lines.extend([
        "## 6. QC Checkpoints",
        "",
    ])

    checkpoints = qc_checkpoints.get("checkpoints", [])
    if checkpoints:
        report_lines.append("| QC ID | Position | Metric | Pass Criteria |")
        report_lines.append("|-------|----------|--------|---------------|")
        for cp in checkpoints:
            items = cp.get("measurement_items", [])
            for item in items:
                report_lines.append(
                    f"| {cp.get('qc_id', '')} | {cp.get('position', '')} | {item.get('metric', '')} | {item.get('pass_criteria', '')} |"
                )
        report_lines.append("")
    else:
        report_lines.append("No QC checkpoints defined.")
        report_lines.append("")

    # UO Mapping Summary
    report_lines.extend([
        "## 7. UO Mapping Summary",
        "",
    ])

    mappings = uo_mapping.get("mappings", uo_mapping.get("uo_mappings", []))
    if isinstance(mappings, list) and mappings:
        report_lines.append("| Step Function | UO ID | Mapping Score | Cases |")
        report_lines.append("|---------------|-------|---------------|-------|")
        for m in mappings:
            func = m.get("step_function", "")
            uo_id = m.get("uo_id", "")
            score = m.get("score", m.get("multi_signal_score", 0))
            cases = ", ".join(m.get("case_refs", [])[:3])
            if len(m.get("case_refs", [])) > 3:
                cases += "..."
            report_lines.append(f"| {func} | {uo_id} | {score:.2f} | {cases} |")
        report_lines.append("")
    else:
        report_lines.append("UO mappings will be populated during workflow composition.")
        report_lines.append("")

    # Equipment & Software Inventory
    report_lines.extend([
        "## 8. Equipment & Software Inventory",
        "",
    ])

    eq_inv = []
    sw_inv = []
    for vf in variant_files:
        vd = load_json(vf)
        for uo in vd.get("uo_sequence", []):
            components = uo.get("components", {})
            # Equipment items
            eq_comp = components.get("equipment", {})
            eq_items = eq_comp.get("items", []) if isinstance(eq_comp, dict) else []
            for item in eq_items:
                name = item.get("name", "")
                if name and name != "[미기재]":
                    eq_inv.append({
                        "name": name,
                        "model": item.get("model", "[미기재]"),
                        "manufacturer": item.get("manufacturer", "[미기재]"),
                        "uo_id": uo.get("uo_id", ""),
                    })
            # Software items
            sw_comp = components.get("parameters", components.get("environment", {}))
            sw_items = sw_comp.get("items", []) if isinstance(sw_comp, dict) else []
            for item in sw_items:
                name = item.get("name", "")
                if name and name != "[미기재]":
                    sw_inv.append({
                        "name": name,
                        "version": item.get("version", "[미기재]"),
                        "developer": item.get("developer", "[미기재]"),
                        "uo_id": uo.get("uo_id", ""),
                    })

    if eq_inv:
        report_lines.append("### 8.1 Equipment")
        report_lines.append("")
        report_lines.append("| Equipment | Model | Manufacturer | UO |")
        report_lines.append("|-----------|-------|--------------|-----|")
        seen_eq = set()
        for eq in eq_inv:
            key = (eq["name"], eq["model"])
            if key not in seen_eq:
                seen_eq.add(key)
                report_lines.append(f"| {eq['name']} | {eq['model']} | {eq['manufacturer']} | {eq['uo_id']} |")
        report_lines.append("")

    if sw_inv:
        report_lines.append("### 8.2 Software")
        report_lines.append("")
        report_lines.append("| Software | Version | Developer | UO |")
        report_lines.append("|----------|---------|-----------|-----|")
        seen_sw = set()
        for sw in sw_inv:
            key = (sw["name"], sw["version"])
            if key not in seen_sw:
                seen_sw.add(key)
                report_lines.append(f"| {sw['name']} | {sw['version']} | {sw['developer']} | {sw['uo_id']} |")
        report_lines.append("")

    if not eq_inv and not sw_inv:
        report_lines.append("No equipment or software inventory data available.")
        report_lines.append("")

    # Section 9: Evidence and Confidence
    report_lines.extend([
        "## 9. Evidence and Confidence",
        "",
    ])

    evidence_counts = {}
    for vd in variants_data:
        for uo in vd.get("uo_sequence", []):
            uo_tag = uo.get("evidence_tag", "")
            if uo_tag:
                evidence_counts[uo_tag] = evidence_counts.get(uo_tag, 0) + 1
            components = uo.get("components", {})
            for comp_name, comp_val in components.items():
                if isinstance(comp_val, dict):
                    tag = comp_val.get("evidence_tag", "")
                    if tag:
                        evidence_counts[tag] = evidence_counts.get(tag, 0) + 1
                elif isinstance(comp_val, list):
                    for item in comp_val:
                        if isinstance(item, dict):
                            tag = item.get("evidence_tag", "")
                            if tag:
                                evidence_counts[tag] = evidence_counts.get(tag, 0) + 1

    if evidence_counts:
        total_ev = sum(evidence_counts.values())
        report_lines.append("| Evidence Tag | Count | Proportion |")
        report_lines.append("|-------------|-------|------------|")
        for tag, count in sorted(evidence_counts.items(), key=lambda x: -x[1]):
            report_lines.append(f"| {tag} | {count} | {count/total_ev:.0%} |")
        report_lines.append("")
    else:
        report_lines.append("No evidence tags found in variant data.")
        report_lines.append("")

    # Section 10: Modularity and Service Integration
    report_lines.extend([
        "## 10. Modularity and Service Integration",
        "",
    ])

    boundaries = context.get("boundaries", context.get("boundary_io", {}))
    if boundaries:
        upstream = boundaries.get("upstream", boundaries.get("input", {}))
        downstream = boundaries.get("downstream", boundaries.get("output", {}))
        if upstream:
            report_lines.append("### Input Boundaries")
            report_lines.append("")
            if isinstance(upstream, dict):
                for key, val in upstream.items():
                    report_lines.append(f"- **{key}**: {val}")
            elif isinstance(upstream, list):
                for item in upstream:
                    report_lines.append(f"- {item}")
            report_lines.append("")
        if downstream:
            report_lines.append("### Output Boundaries")
            report_lines.append("")
            if isinstance(downstream, dict):
                for key, val in downstream.items():
                    report_lines.append(f"- **{key}**: {val}")
            elif isinstance(downstream, list):
                for item in downstream:
                    report_lines.append(f"- {item}")
            report_lines.append("")
        if not upstream and not downstream:
            report_lines.append("<!-- TODO: Populate boundary I/O data in workflow_context.json -->")
            report_lines.append("")
    else:
        report_lines.append("<!-- TODO: Populate boundary I/O data in workflow_context.json -->")
        report_lines.append("")

    # Section 11: Limitations and Notes
    report_lines.extend([
        "## 11. Limitations and Notes",
        "",
    ])

    limitations, catalog_feedback = generate_limitations(wf_dir)

    if limitations:
        for lim in limitations:
            cat = lim.get("category", "general")
            desc = lim.get("description", "")
            report_lines.append(f"- **[{cat.upper()}]** {desc}")
        report_lines.append("")
    else:
        report_lines.append("No significant limitations identified.")
        report_lines.append("")

    # Section 12: Catalog Feedback
    report_lines.extend([
        "## 12. Catalog Feedback",
        "",
    ])

    cf_uo_issues = catalog_feedback.get("uo_issues", [])
    cf_component_gaps = catalog_feedback.get("component_gaps", [])

    if cf_uo_issues:
        report_lines.append("### UO Mapping Issues")
        report_lines.append("")
        report_lines.append("| UO ID | Category | Description | Suggested Action |")
        report_lines.append("|-------|----------|-------------|-----------------|")
        for issue in cf_uo_issues:
            report_lines.append(
                f"| {issue.get('uo_id', '')} | {issue.get('category', '')} | "
                f"{issue.get('description', '')} | {issue.get('suggested_action', '')} |"
            )
        report_lines.append("")

    if cf_component_gaps:
        report_lines.append("### Component Gaps")
        report_lines.append("")
        report_lines.append("| UO ID | Component | Gap Description |")
        report_lines.append("|-------|-----------|-----------------|")
        for gap in cf_component_gaps:
            report_lines.append(
                f"| {gap.get('uo_id', '')} | {gap.get('component', '')} | "
                f"{gap.get('gap_description', '')} |"
            )
        report_lines.append("")

    if not cf_uo_issues and not cf_component_gaps:
        cf_summary = catalog_feedback.get("summary", {})
        report_lines.append(
            f"No catalog feedback issues found "
            f"(total findings: {cf_summary.get('total_findings', 0)})."
        )
        report_lines.append("")

    # Section 13: Execution Metrics
    report_lines.extend([
        "## 13. Execution Metrics",
        "",
    ])

    exec_log = load_json(wf_dir / "00_metadata" / "execution_log.json")
    exec_events = exec_log.get("events", [])
    exec_summary = exec_log.get("summary", {})

    if exec_summary:
        for key, val in exec_summary.items():
            report_lines.append(f"- **{key}**: {val}")
        report_lines.append("")
    elif exec_events:
        phase_events = [e for e in exec_events if e.get("type") == "phase"]
        if phase_events:
            report_lines.append("| Phase | Start | Duration |")
            report_lines.append("|-------|-------|----------|")
            for pe in phase_events:
                phase = pe.get("phase", "?")
                start = pe.get("timestamp", pe.get("start", ""))
                duration = pe.get("duration", pe.get("elapsed", ""))
                report_lines.append(f"| {phase} | {start} | {duration} |")
            report_lines.append("")
        else:
            report_lines.append(f"Execution log contains {len(exec_events)} events.")
            report_lines.append("")
    else:
        report_lines.append("No execution metrics available.")
        report_lines.append("")

    report_lines.extend([
        "---",
        "",
        f"*Generated by workflow-composer skill v{__version__}*",
    ])

    report_content = "\n".join(report_lines)

    # Save report
    report_path = wf_dir / "composition_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)

    return report_content


def generate_composition_data(wf_dir: str | Path) -> dict:
    """Generate composition_data.json from all workflow artifacts."""
    wf_dir = Path(wf_dir)

    context = load_json(wf_dir / "00_metadata" / "workflow_context.json")
    case_summary = load_json(wf_dir / "02_cases" / "case_summary.json")
    common_pattern = load_json(wf_dir / "03_analysis" / "common_pattern.json")
    cluster_result = load_json(wf_dir / "03_analysis" / "cluster_result.json")
    parameter_ranges = load_json(wf_dir / "03_analysis" / "parameter_ranges.json")
    qc_checkpoints = load_json(wf_dir / "04_workflow" / "qc_checkpoints.json")

    # Load variants
    variant_files = sorted((wf_dir / "04_workflow").glob("variant_V*.json"))
    variants = {}
    total_uos = 0
    for vf in variant_files:
        vd = load_json(vf)
        vid = vd.get("variant_id", vf.stem.split("_")[1])
        variants[vid] = vd
        total_uos += len(vd.get("uo_sequence", []))

    # Generate limitations and catalog feedback
    limitations, catalog_feedback = generate_limitations(wf_dir)

    # Determine version info
    version_history_path = wf_dir / "00_metadata" / "version_history.json"
    version = 1.0
    version_history = []
    if version_history_path.exists():
        vh = load_json(version_history_path)
        version_history = vh.get("versions", [])
        version = float(vh.get("current_version", 1.0))

    wf_id = context.get("workflow_id", "")

    # Compute confidence score from evidence tags across variants
    confidence_score = _compute_confidence(variants)

    # Build modularity section from common_pattern
    modularity = {}
    for mkey in ["boundary_inputs", "boundary_outputs", "common_upstream_workflows",
                 "common_downstream_workflows", "service_chains_observed"]:
        if mkey in common_pattern:
            modularity[mkey] = common_pattern[mkey]

    # Load UO mapping
    uo_mapping_data = load_json(wf_dir / "04_workflow" / "uo_mapping.json")

    # Build related_workflows from modularity data
    related_workflows = {}
    if common_pattern.get("common_upstream_workflows"):
        related_workflows["upstream"] = common_pattern["common_upstream_workflows"]
    if common_pattern.get("common_downstream_workflows"):
        related_workflows["downstream"] = common_pattern["common_downstream_workflows"]

    # Paper count from paper_list.json
    paper_list = load_json(wf_dir / "01_papers" / "paper_list.json")
    papers_analyzed = len(paper_list.get("papers", []))
    if papers_analyzed == 0:
        # Fallback: count P* entries via keys
        papers_analyzed = sum(1 for k in paper_list if k.startswith("P"))

    data = {
        "schema_version": SCHEMA_VERSION,
        "workflow_id": wf_id,
        "workflow_name": context.get("workflow_name", ""),
        "category": context.get("category", {"WB": "Build", "WT": "Test", "WD": "Design", "WL": "Learn"}.get(wf_id[:2], "Build")),
        "domain": context.get("domain", ""),
        "version": version,
        "composition_date": datetime.now().strftime("%Y-%m-%d"),
        "description": context.get("description", ""),
        "statistics": {
            "papers_analyzed": papers_analyzed,
            "cases_collected": case_summary.get("total_cases", 0),
            "variants_identified": len(variants),
            "total_uos": total_uos,
            "qc_checkpoints": len(qc_checkpoints.get("checkpoints", [])),
            "confidence_score": confidence_score,
        },
        "modularity": modularity,
        "common_skeleton": common_pattern.get("mandatory_steps", []),
        "variants": variants,
        "uo_mapping": uo_mapping_data if uo_mapping_data else None,
        "qc_checkpoints": qc_checkpoints.get("checkpoints", []),
        "related_workflows": related_workflows if related_workflows else None,
        "parameter_ranges": parameter_ranges,
        "limitations": limitations,
        "catalog_feedback": catalog_feedback,
        "confidence_score": confidence_score,
    }

    # Remove None-valued optional sections
    data = {k: v for k, v in data.items() if v is not None}

    # Populate equipment_software_inventory
    eq_inventory = []
    sw_inventory = []
    eq_seen = set()
    sw_seen = set()
    for vf in variant_files:
        vd = load_json(vf)
        vid = vd.get("variant_id", vf.stem.split("_")[1] if "_" in vf.stem else vf.stem)
        for uo in vd.get("uo_sequence", []):
            uo_id = uo.get("uo_id", "")
            components = uo.get("components", {})
            # Equipment items
            eq_comp = components.get("equipment", {})
            eq_items = eq_comp.get("items", []) if isinstance(eq_comp, dict) else []
            for item in eq_items:
                name = item.get("name", "")
                if name and name != "[미기재]":
                    key = (name, item.get("model", ""))
                    if key not in eq_seen:
                        eq_seen.add(key)
                        eq_inventory.append({
                            "name": name,
                            "model": item.get("model", "[미기재]"),
                            "manufacturer": item.get("manufacturer", "[미기재]"),
                            "used_in_uos": [uo_id],
                            "variants": [vid],
                            "case_refs": uo.get("case_refs", []),
                            "evidence_tag": item.get("evidence_tag", uo.get("evidence_tag", "")),
                        })
                    else:
                        # Merge into existing
                        for eq in eq_inventory:
                            if (eq["name"], eq["model"]) == key:
                                if uo_id not in eq["used_in_uos"]:
                                    eq["used_in_uos"].append(uo_id)
                                if vid not in eq["variants"]:
                                    eq["variants"].append(vid)
                                for cr in uo.get("case_refs", []):
                                    if cr not in eq["case_refs"]:
                                        eq["case_refs"].append(cr)
                                break
            # Software items
            sw_comp = components.get("parameters", components.get("environment", {}))
            sw_items = sw_comp.get("items", []) if isinstance(sw_comp, dict) else []
            for item in sw_items:
                name = item.get("name", "")
                if name and name != "[미기재]":
                    key = (name, item.get("version", ""))
                    if key not in sw_seen:
                        sw_seen.add(key)
                        sw_inventory.append({
                            "name": name,
                            "version": item.get("version", "[미기재]"),
                            "developer": item.get("developer", "[미기재]"),
                            "license": item.get("license", "[미기재]"),
                            "used_in_uos": [uo_id],
                            "variants": [vid],
                            "case_refs": uo.get("case_refs", []),
                            "evidence_tag": item.get("evidence_tag", uo.get("evidence_tag", "")),
                        })
                    else:
                        for sw in sw_inventory:
                            if (sw["name"], sw["version"]) == key:
                                if uo_id not in sw["used_in_uos"]:
                                    sw["used_in_uos"].append(uo_id)
                                if vid not in sw["variants"]:
                                    sw["variants"].append(vid)
                                for cr in uo.get("case_refs", []):
                                    if cr not in sw["case_refs"]:
                                        sw["case_refs"].append(cr)
                                break

    eq_with_model = sum(1 for e in eq_inventory if e["model"] != "[미기재]")
    eq_with_mfr = sum(1 for e in eq_inventory if e["manufacturer"] != "[미기재]")
    sw_with_ver = sum(1 for s in sw_inventory if s["version"] != "[미기재]")
    sw_with_dev = sum(1 for s in sw_inventory if s["developer"] != "[미기재]")

    data["equipment_software_inventory"] = {
        "equipment": eq_inventory,
        "software": sw_inventory,
        "coverage": {
            "equipment_with_model": eq_with_model,
            "equipment_with_manufacturer": eq_with_mfr,
            "total_equipment": len(eq_inventory),
            "software_with_version": sw_with_ver,
            "software_with_developer": sw_with_dev,
            "total_software": len(sw_inventory),
        },
    }

    if version_history:
        data["version_history"] = version_history

    # Reorder keys to standard and save
    data = _reorder_keys(data)
    data_path = wf_dir / "composition_data.json"
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return data


def generate_composition_workflow(wf_dir: str | Path) -> str:
    """
    Generate composition_workflow.md — a human-readable workflow reference card.

    Reads composition_data.json and produces compact tables:
    skeleton, variant sequences, parameter ranges.
    """
    wf_dir = Path(wf_dir)
    data = load_json(wf_dir / "composition_data.json")

    wf_id = data.get("workflow_id", "UNKNOWN")
    wf_name = data.get("workflow_name", "UNKNOWN")
    stats = data.get("statistics", {})
    num_variants = stats.get("variants_identified", 0)

    lines = [
        f"# {wf_id}: {wf_name} — Workflow Reference Card",
        "",
        f"**Version**: {datetime.now().strftime('%Y-%m-%d')} | **Variants**: {num_variants}",
        "",
    ]

    # Common Workflow Skeleton
    skeleton = data.get("common_skeleton", [])
    if skeleton:
        lines.extend([
            "## Common Workflow Skeleton",
            "",
            "| Pos | Function | Mandatory | UO | Type |",
            "|-----|----------|-----------|----|------|",
        ])
        for step in skeleton:
            pos = step.get("position", "?")
            func = step.get("function", "") or ", ".join(step.get("step_name_variants", {}).keys())
            ratio = step.get("presence_ratio", 0)
            mandatory = "Y" if ratio >= 0.8 else "N"
            uo_id = step.get("uo_id", step.get("mapped_uo", ""))
            uo_type = step.get("type", step.get("uo_type", ""))
            lines.append(f"| {pos} | {func} | {mandatory} | {uo_id} | {uo_type} |")
        lines.append("")

    # Variants
    variants = data.get("variants", {})
    if variants:
        lines.extend(["## Variants", ""])
        for vid, vd in sorted(variants.items()):
            vname = vd.get("name", "?")
            case_ids = vd.get("case_ids", [])
            uo_seq = vd.get("uo_sequence", [])

            # UO sequence arrow string
            uo_ids = [uo.get("uo_id", "?") for uo in uo_seq]
            arrow_str = " → ".join(uo_ids)

            lines.extend([
                f"### {vid}: {vname} ({len(case_ids)} cases)",
                f"**UO Sequence**: {arrow_str}",
                "",
                "| Step | UO ID | UO Name | Instance Label | Type |",
                "|------|-------|---------|----------------|------|",
            ])
            for i, uo in enumerate(uo_seq, 1):
                uo_id = uo.get("uo_id", "")
                uo_name = uo.get("uo_name", "")
                label = uo.get("instance_label", "")
                uo_type = uo.get("type", "")
                lines.append(f"| {i} | {uo_id} | {uo_name} | {label} | {uo_type} |")
            lines.append("")

            # QC Checkpoints for this variant
            qc = vd.get("qc_checkpoints", [])
            if qc:
                lines.append("**QC Checkpoints**:")
                for cp in qc:
                    qc_id = cp.get("qc_id", "")
                    items = cp.get("measurement_items", [])
                    for item in items:
                        metric = item.get("metric", "")
                        pass_c = item.get("pass_criteria", "")
                        fail_a = item.get("fail_action", "")
                        lines.append(f"- {qc_id}: {metric} — Pass: {pass_c} | Fail: {fail_a}")
                lines.append("")

    # Parameter Quick-Reference
    param_ranges = data.get("parameter_ranges", {})
    if param_ranges:
        lines.extend([
            "## Parameter Quick-Reference",
            "",
            "| Parameter | Range | Unit | Variants | Cases |",
            "|-----------|-------|------|----------|-------|",
        ])
        params = param_ranges.get("parameters", param_ranges)
        if isinstance(params, list):
            for p in params:
                name = p.get("name", p.get("parameter", ""))
                rng = p.get("range", "")
                unit = p.get("unit", "")
                pvariants = ", ".join(p.get("variants", []))
                cases = ", ".join(p.get("case_refs", []))
                lines.append(f"| {name} | {rng} | {unit} | {pvariants} | {cases} |")
        elif isinstance(params, dict):
            for pname, pval in params.items():
                if isinstance(pval, dict):
                    rng = pval.get("range", "")
                    unit = pval.get("unit", "")
                    pvariants = ", ".join(pval.get("variants", []))
                    cases = ", ".join(pval.get("case_refs", []))
                    lines.append(f"| {pname} | {rng} | {unit} | {pvariants} | {cases} |")
        lines.append("")

    content = "\n".join(lines)

    # Save
    out_path = wf_dir / "composition_workflow.md"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content


def update_index(base_dir: str | Path, wf_dir: str | Path):
    """Update the global index.json with this workflow's information."""
    base_dir = Path(base_dir)
    wf_dir = Path(wf_dir)
    index_path = base_dir / "workflow-compositions" / "index.json"

    # Load existing index or create new
    if index_path.exists():
        with open(index_path, "r", encoding="utf-8") as f:
            index = json.load(f)
    else:
        index = {
            "generated": datetime.now().isoformat(),
            "total_workflows": 0,
            "completed": [],
            "in_progress": [],
            "workflows": {},
        }

    # Load this workflow's data
    context = load_json(wf_dir / "00_metadata" / "workflow_context.json")
    data = load_json(wf_dir / "composition_data.json")

    wf_id = context.get("workflow_id", "")
    wf_name = context.get("workflow_name", "")

    version = data.get("version", 1.0)
    existing_entry = index.get("workflows", {}).get(wf_id, {})
    version_count = existing_entry.get("version_count", 0) + 1

    stats = data.get("statistics", {})
    index["workflows"][wf_id] = {
        "name": wf_name,
        "category": context.get("category", {"WB": "Build", "WT": "Test", "WD": "Design", "WL": "Learn"}.get(wf_id[:2], "Build")),
        "domain": context.get("domain", ""),
        "status": "completed",
        "version": version,
        "version_count": version_count,
        "papers": stats.get("papers_analyzed", 0),
        "cases": stats.get("cases_collected", 0),
        "variants": stats.get("variants_identified", 0),
        "uos": stats.get("total_uos", 0),
        "path": f"./{wf_dir.relative_to(base_dir / 'workflow-compositions')}/",
        "last_updated": datetime.now().isoformat(),
        "confidence": stats.get("confidence_score"),
        "last_upgraded": data.get("composition_date", datetime.now().strftime("%Y-%m-%d")),
    }

    # Update counts
    index["total_workflows"] = len(index["workflows"])
    index["completed"] = [k for k, v in index["workflows"].items() if v.get("status") == "completed"]
    index["in_progress"] = [k for k, v in index["workflows"].items() if v.get("status") == "in_progress"]
    index["generated"] = datetime.now().isoformat()

    # Save
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)

    return index


def generate_all_outputs(wf_dir: str | Path, base_dir: str | Path = ".") -> dict:
    """
    Generate all final output documents.

    Args:
        wf_dir: workflow output directory
        base_dir: project base directory (parent of workflow-compositions/)

    Returns:
        Summary of generated outputs.
    """
    wf_dir = Path(wf_dir)
    base_dir = Path(base_dir)

    report = generate_composition_report(wf_dir)
    data = generate_composition_data(wf_dir)
    workflow_md = generate_composition_workflow(wf_dir)
    index = update_index(base_dir, wf_dir)

    result = {
        "report_path": str(wf_dir / "composition_report.md"),
        "data_path": str(wf_dir / "composition_data.json"),
        "workflow_md_path": str(wf_dir / "composition_workflow.md"),
        "index_path": str(base_dir / "workflow-compositions" / "index.json"),
        "workflow_id": data.get("workflow_id", ""),
        "statistics": data.get("statistics", {}),
    }

    return result


if __name__ == "__main__":
    import sys

    if "--test" in sys.argv:
        import re
        import tempfile

        print("=== generate_output.py self-test ===\n")

        with tempfile.TemporaryDirectory() as tmpdir:
            wf_dir = Path(tmpdir) / "WB_TEST"
            for d in ["00_metadata", "01_papers", "02_cases", "03_analysis",
                       "04_workflow", "05_visualization"]:
                (wf_dir / d).mkdir(parents=True, exist_ok=True)

            # Create minimal data files
            with open(wf_dir / "00_metadata" / "workflow_context.json", "w") as f:
                json.dump({
                    "workflow_id": "WB_TEST", "workflow_name": "Test Workflow",
                    "domain": "test", "description": "A test workflow.",
                }, f)
            with open(wf_dir / "01_papers" / "paper_list.json", "w") as f:
                json.dump({"papers": [{"id": "P1", "title": "Test Paper"}]}, f)
            with open(wf_dir / "02_cases" / "case_summary.json", "w") as f:
                json.dump({
                    "total_cases": 3,
                    "by_technique": {"PCR": 2, "RT-qPCR": 1},
                    "by_organism": {"E. coli": 3},
                }, f)
            with open(wf_dir / "03_analysis" / "common_pattern.json", "w") as f:
                json.dump({"mandatory_steps": [
                    {"position": 1, "function": "DNA Extraction", "presence_ratio": 1.0},
                ]}, f)
            with open(wf_dir / "04_workflow" / "uo_mapping.json", "w") as f:
                json.dump({"mappings": [
                    {"step_function": "DNA Extraction", "uo_id": "UO-001",
                     "score": 0.95, "case_refs": ["C001"]},
                ]}, f)
            with open(wf_dir / "04_workflow" / "qc_checkpoints.json", "w") as f:
                json.dump({"checkpoints": [
                    {"qc_id": "QC1", "position": "after UO-001",
                     "measurement_items": [{"metric": "concentration", "pass_criteria": ">10 ng/uL"}]},
                ]}, f)

            # Create a variant file with evidence tags
            variant = {
                "variant_id": "V1", "name": "Standard",
                "case_ids": ["C001", "C002"],
                "uo_sequence": [{
                    "uo_id": "UO-001", "instance_label": "DNA Extraction",
                    "type": "HW", "evidence_tag": "literature",
                    "components": {
                        "equipment": {"items": [
                            {"name": "Centrifuge", "model": "5424R",
                             "manufacturer": "Eppendorf", "evidence_tag": "literature"},
                        ]},
                    },
                }],
            }
            with open(wf_dir / "04_workflow" / "variant_V1.json", "w") as f:
                json.dump(variant, f)

            # Generate report
            report = generate_composition_report(wf_dir)

            # Verify 13 sections
            found_sections = set()
            for line in report.split("\n"):
                m = re.match(r'^## (\d+)\.', line)
                if m:
                    found_sections.add(int(m.group(1)))

            expected = set(range(1, 14))
            missing = expected - found_sections

            if missing:
                print(f"FAIL: Missing sections: {sorted(missing)}")
                print(f"Found sections: {sorted(found_sections)}")
                sys.exit(1)
            else:
                print(f"PASS: All 13 sections found: {sorted(found_sections)}")
                for line in report.split("\n"):
                    if line.startswith("## "):
                        print(f"  {line}")
                print(f"\nReport length: {len(report)} characters")
                print("\n=== All tests passed! ===")

    elif len(sys.argv) < 2:
        print("Usage: python generate_output.py <workflow_output_dir> [base_dir]")
        print("       python generate_output.py --test")
        sys.exit(1)

    else:
        wf_dir = sys.argv[1]
        base_dir = sys.argv[2] if len(sys.argv) > 2 else "."

        result = generate_all_outputs(wf_dir, base_dir)
        print(json.dumps(result, indent=2, ensure_ascii=False))
