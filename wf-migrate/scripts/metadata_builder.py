"""Build canonical metadata blocks for legacy case cards."""

import json
from pathlib import Path


def build_paper_index(paper_data) -> dict:
    """Build lookup dict from paper_list data.

    Handles both {"papers": [...]} and flat [...] formats.
    Returns {paper_id: {pmid, doi, title, authors, year, journal}}.
    """
    if isinstance(paper_data, list):
        papers = paper_data
    elif isinstance(paper_data, dict):
        papers = paper_data.get("papers", [])
    else:
        return {}

    index = {}
    for p in papers:
        pid = p.get("paper_id")
        if pid:
            index[pid] = {
                "pmid": p.get("pmid", ""),
                "doi": p.get("doi", ""),
                "title": p.get("title", ""),
                "authors": p.get("authors", ""),
                "year": p.get("year", ""),
                "journal": p.get("journal", ""),
            }
    return index


def load_paper_list(wf_dir: Path) -> dict:
    """Load paper_list.json from wf_dir (try 01_papers/ then 01_literature/).
    Returns parsed data or empty dict.
    """
    for subdir in ("01_papers", "01_literature"):
        candidate = wf_dir / subdir / "paper_list.json"
        if candidate.exists():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
    return {}


def build_metadata(case_data: dict, paper_index: dict) -> dict:
    """Build canonical metadata block from legacy case data + paper lookup.

    Maps:
    - paper_id -> lookup pmid, doi, authors, year, journal, title from paper_index
    - organism -> organism
    - scale -> scale
    - technique -> core_technique
    - title (from case) -> purpose
    - title (from paper) -> title

    Defaults:
    - automation_level: "manual"
    - fulltext_access: False
    - access_method: "unknown"
    - access_tier: 3

    Returns dict with all 14 canonical metadata fields.
    """
    paper_id = case_data.get("paper_id", "")
    paper_info = paper_index.get(paper_id, {}) if paper_id else {}

    return {
        "pmid": paper_info.get("pmid", ""),
        "doi": paper_info.get("doi", ""),
        "authors": paper_info.get("authors", ""),
        "year": paper_info.get("year", ""),
        "journal": paper_info.get("journal", ""),
        "title": paper_info.get("title", ""),
        "purpose": case_data.get("title", ""),
        "organism": case_data.get("organism", ""),
        "scale": case_data.get("scale", ""),
        "core_technique": case_data.get("technique", ""),
        "automation_level": "manual",
        "fulltext_access": False,
        "access_method": "unknown",
        "access_tier": 3,
    }


def build_completeness_stub() -> dict:
    """Create a stub completeness block for migrated cards."""
    return {"score": 0.0, "notes": "Auto-generated during migration - requires manual review"}


def build_completeness(case_data: dict) -> dict:
    """Compute real completeness score based on actual data presence.

    Scoring weights:
    - metadata block (14 fields): 30%
    - steps detail (conditions, equipment, result_qc, reagents): 40%
    - structural blocks (flow_diagram, workflow_context): 15%
    - documentation (description quality): 15%

    Returns {"score": float, "details": dict, "notes": str}.
    """
    scores = {}

    # 1. Metadata completeness (30%)
    metadata = case_data.get("metadata", {})
    meta_fields = [
        "pmid", "doi", "authors", "year", "journal", "title",
        "purpose", "organism", "scale", "core_technique",
        "automation_level", "fulltext_access", "access_method", "access_tier",
    ]
    meta_filled = sum(
        1 for f in meta_fields
        if metadata.get(f) and str(metadata.get(f, "")).strip()
        and str(metadata.get(f, "")) not in ("[미기재]", "unknown", "")
    )
    scores["metadata"] = meta_filled / len(meta_fields) if meta_fields else 0

    # 2. Steps detail completeness (40%)
    steps = case_data.get("steps", [])
    if steps:
        step_scores = []
        for step in steps:
            filled = sum(1 for field in ("step_name", "description", "conditions",
                                          "equipment", "result_qc", "reagents")
                         if step.get(field) and str(step.get(field, "")) not in ("", "[미기재]"))
            step_scores.append(filled / 6)
        scores["steps"] = sum(step_scores) / len(step_scores)
    else:
        scores["steps"] = 0.0

    # 3. Structural blocks (15%)
    struct_present = sum(1 for k in ("flow_diagram", "workflow_context", "completeness")
                         if case_data.get(k))
    scores["structure"] = struct_present / 3

    # 4. Documentation quality (15%)
    doc_score = 0
    total_steps = len(steps) if steps else 1
    for step in steps:
        desc = str(step.get("description", ""))
        if len(desc) > 50:
            doc_score += 1.0
        elif len(desc) > 20:
            doc_score += 0.5
    scores["documentation"] = doc_score / total_steps if steps else 0

    total = (scores["metadata"] * 0.30 + scores["steps"] * 0.40
             + scores["structure"] * 0.15 + scores["documentation"] * 0.15)

    notes_parts = []
    if scores["metadata"] < 0.5:
        notes_parts.append("metadata incomplete")
    if scores["steps"] < 0.5:
        notes_parts.append("step details sparse")
    if not notes_parts:
        notes_parts.append("well-populated")

    return {
        "score": round(total, 3),
        "details": {k: round(v, 3) for k, v in scores.items()},
        "notes": f"Computed by wf-migrate v2.0: {', '.join(notes_parts)}",
    }


def build_flow_diagram(steps: list) -> str:
    """Generate simple flow diagram string from step names.

    Returns "Step A -> Step B -> Step C" format.
    """
    if not steps:
        return ""
    names = [s.get("step_name", "") for s in steps]
    return " -> ".join(names)


def build_flow_diagram_with_qc(steps: list) -> str:
    """Generate flow diagram with QC checkpoint markers.

    Steps with non-empty result_qc get a [QC] marker.
    Returns "Step A -> [QC] -> Step B -> Step C -> [QC]" format.
    """
    if not steps:
        return ""
    parts = []
    for step in steps:
        name = step.get("step_name", "")
        parts.append(name)
        qc = step.get("result_qc", "")
        if qc and str(qc) not in ("", "[미기재]"):
            parts.append("[QC]")
    return " -> ".join(parts)


def build_workflow_context(workflow_id: str) -> dict:
    """Create workflow_context block."""
    return {"workflow_id": workflow_id, "migration_source": "wf-migrate v1.0.0"}


def build_workflow_context_from_composition(workflow_id: str,
                                             composition_data: dict = None) -> dict:
    """Create workflow_context from composition_data.modularity.

    Args:
        workflow_id: e.g. "WT120"
        composition_data: parsed composition_data.json (optional)

    Returns:
        workflow_context dict with boundary info from modularity.
    """
    ctx = {
        "workflow_id": workflow_id,
        "migration_source": "wf-migrate v2.0.0",
    }

    if composition_data:
        modularity = composition_data.get("modularity", {})
        ctx["boundary_inputs"] = [
            inp.get("name", "") for inp in modularity.get("boundary_inputs", [])
        ]
        ctx["boundary_outputs"] = [
            out.get("name", "") for out in modularity.get("boundary_outputs", [])
        ]
        if modularity.get("upstream_workflows"):
            ctx["upstream_workflows"] = modularity["upstream_workflows"]
        if modularity.get("downstream_workflows"):
            ctx["downstream_workflows"] = modularity["downstream_workflows"]

    return ctx
