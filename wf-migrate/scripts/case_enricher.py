"""Case card enrichment based on paper data (6-principle extraction).

Implements the workflow-composer case-collection-guide's 6 extraction principles
to enrich case cards with metadata, step details, equipment, and QC criteria
from paper abstracts/full texts.
"""

import re


# ---------------------------------------------------------------------------
# 6-Principle extraction helpers
# ---------------------------------------------------------------------------

# Principle 1: Extract metadata from paper info
def extract_metadata_from_paper(paper_info: dict, case_data: dict) -> dict:
    """Build/enrich metadata block from paper information.

    Combines paper-level data (PMID, DOI, authors, year, journal, title)
    with case-level data (organism, scale, technique, purpose).

    Args:
        paper_info: enriched paper dict with pmid, doi, authors, abstract, etc.
        case_data: existing case card data

    Returns:
        Complete metadata dict with all 14 canonical fields.
    """
    existing_meta = case_data.get("metadata", {})

    # Authors: prefer structured list, fall back to string
    authors = paper_info.get("authors", "")
    if isinstance(authors, list):
        authors = ", ".join(authors)

    metadata = {
        "pmid": _best(existing_meta.get("pmid"), str(paper_info.get("pmid", ""))),
        "doi": _best(existing_meta.get("doi"), str(paper_info.get("doi", ""))),
        "authors": _best(existing_meta.get("authors"), authors),
        "year": _best(existing_meta.get("year"), paper_info.get("year", "")),
        "journal": _best(existing_meta.get("journal"), paper_info.get("journal", "")),
        "title": _best(existing_meta.get("title"), paper_info.get("title", "")),
        "purpose": _best(
            existing_meta.get("purpose"),
            case_data.get("title", ""),
            case_data.get("application", ""),
        ),
        "organism": _best(
            existing_meta.get("organism"),
            case_data.get("organism", ""),
        ),
        "scale": _best(
            existing_meta.get("scale"),
            case_data.get("scale", ""),
        ),
        "core_technique": _best(
            existing_meta.get("core_technique"),
            case_data.get("technique", ""),
            paper_info.get("technique", ""),
        ),
        "automation_level": _best(
            existing_meta.get("automation_level"),
            _infer_automation_level(case_data, paper_info),
        ),
        "fulltext_access": existing_meta.get(
            "fulltext_access",
            bool(paper_info.get("full_text") or paper_info.get("abstract")),
        ),
        "access_method": _best(
            existing_meta.get("access_method"),
            paper_info.get("text_source", ""),
            "pubmed_abstract" if paper_info.get("abstract") else "unknown",
        ),
        "access_tier": existing_meta.get(
            "access_tier",
            1 if paper_info.get("full_text") else (2 if paper_info.get("abstract") else 3),
        ),
    }

    return metadata


def _best(*values) -> str:
    """Return first non-empty, non-placeholder value."""
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v and v not in ("[미기재]", "unknown", ""):
                return v
        elif isinstance(v, (int, float)):
            if v:
                return v
        elif v:
            return v
    return values[-1] if values else ""


def _infer_automation_level(case_data: dict, paper_info: dict) -> str:
    """Infer automation level from case/paper text."""
    text = " ".join([
        str(case_data.get("title", "")),
        str(case_data.get("application", "")),
        str(paper_info.get("abstract", "")),
        str(paper_info.get("title", "")),
    ]).lower()

    if any(kw in text for kw in ["automated", "robotic", "self-driving", "autonomous"]):
        return "automated"
    if any(kw in text for kw in ["semi-automated", "semi-automatic", "assisted"]):
        return "semi-automated"
    return "manual"


# ---------------------------------------------------------------------------
# Principle 2: Enrich step details from paper text
# ---------------------------------------------------------------------------

def enrich_step_details(step: dict, paper_text: str) -> dict:
    """Enrich a single step with details extracted from paper text.

    Extracts:
    - Specific conditions (temperature, time, concentration) from paper
    - Enriches description if sparse
    - Fills [미기재] placeholders where possible

    Args:
        step: existing step dict
        paper_text: abstract or full text from paper

    Returns:
        Enriched step dict (mutated copy).
    """
    enriched = dict(step)

    if not paper_text:
        return enriched

    step_name = str(enriched.get("step_name", "")).lower()

    # Enrich conditions from paper text
    conditions = enriched.get("conditions", "")
    if not conditions or conditions == "[미기재]":
        extracted = _extract_conditions_for_step(step_name, paper_text)
        if extracted:
            enriched["conditions"] = extracted

    # Enrich result_qc
    result_qc = enriched.get("result_qc", "")
    if not result_qc or result_qc == "[미기재]":
        qc = extract_qc_criteria(paper_text, step_name)
        if qc:
            enriched["result_qc"] = qc

    # Enrich reagents
    reagents = enriched.get("reagents", "")
    if not reagents or reagents == "[미기재]":
        extracted_reagents = _extract_reagents(paper_text, step_name)
        if extracted_reagents:
            enriched["reagents"] = extracted_reagents

    return enriched


def _extract_conditions_for_step(step_name: str, text: str) -> str:
    """Extract relevant conditions from paper text based on step name."""
    conditions = []

    # Temperature patterns
    temp_matches = re.findall(
        r'(\d+)\s*[°]?\s*C(?:\s|,|\.|;)', text
    )
    if temp_matches:
        temps = sorted(set(temp_matches))
        if len(temps) <= 3:
            conditions.append(f"Temperature: {', '.join(t + '°C' for t in temps)}")

    # Time/duration patterns
    time_matches = re.findall(
        r'(\d+(?:\.\d+)?)\s*(min(?:utes?)?|h(?:ours?)?|s(?:econds?)?|days?)',
        text, re.IGNORECASE
    )
    if time_matches:
        times = [f"{val} {unit}" for val, unit in time_matches[:3]]
        conditions.append(f"Duration: {', '.join(times)}")

    # RPM/speed patterns
    rpm_matches = re.findall(r'(\d+)\s*rpm', text, re.IGNORECASE)
    if rpm_matches:
        conditions.append(f"Speed: {', '.join(set(rpm_matches))} rpm")

    # Concentration patterns
    conc_matches = re.findall(
        r'(\d+(?:\.\d+)?)\s*(mM|µM|uM|nM|mg/mL|µg/mL|%\s*(?:v/v|w/v)?)',
        text, re.IGNORECASE
    )
    if conc_matches:
        concs = [f"{val} {unit}" for val, unit in conc_matches[:3]]
        conditions.append(f"Concentrations: {', '.join(concs)}")

    return "; ".join(conditions) if conditions else ""


def _extract_reagents(text: str, step_name: str) -> str:
    """Extract reagent mentions from text."""
    # Common reagent patterns
    reagent_patterns = [
        r'(?:using|with|containing)\s+([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+)*(?:\s+\d+)?)',
        r'(\d+(?:\.\d+)?\s*(?:mM|µM|mg/mL|µg/mL)\s+\w+(?:\s+\w+)?)',
    ]

    reagents = []
    for pattern in reagent_patterns:
        matches = re.findall(pattern, text)
        reagents.extend(matches[:3])

    return ", ".join(reagents) if reagents else ""


# ---------------------------------------------------------------------------
# Principle 3: Extract equipment details
# ---------------------------------------------------------------------------

def extract_equipment_details(text: str) -> list[dict]:
    """Extract equipment model and manufacturer from paper text.

    Looks for patterns like:
    - "ModelName (Manufacturer)"
    - "Manufacturer ModelName"
    - Known equipment brand patterns

    Returns list of {name, model, manufacturer} dicts.
    """
    equipment = []

    # Pattern: "Name (Manufacturer)" or "Name (Model; Manufacturer)"
    paren_pattern = re.findall(
        r'([A-Z][\w\s-]{2,30}?)\s*\(([^)]+)\)',
        text
    )
    for name, paren_content in paren_pattern:
        name = name.strip()
        # Skip common false positives
        if name.lower() in ("fig", "figure", "table", "et al", "i.e", "e.g"):
            continue
        parts = [p.strip() for p in paren_content.split(";")]
        if len(parts) >= 2:
            equipment.append({
                "name": name,
                "model": parts[0],
                "manufacturer": parts[1],
            })
        elif len(parts) == 1:
            equipment.append({
                "name": name,
                "model": "",
                "manufacturer": parts[0],
            })

    return equipment


def enrich_step_equipment(step: dict, paper_text: str) -> list[dict]:
    """Enrich equipment entries in a step with details from paper text.

    For each equipment item that has empty model/manufacturer,
    try to find details in the paper text.

    Returns updated equipment list.
    """
    if not paper_text:
        return step.get("equipment", [])

    equipment = step.get("equipment", [])
    paper_equipment = extract_equipment_details(paper_text)

    # Build lookup by name similarity
    paper_equip_by_name = {}
    for pe in paper_equipment:
        key = pe["name"].lower().split()[0] if pe["name"] else ""
        if key:
            paper_equip_by_name[key] = pe

    enriched = []
    for item in equipment:
        item = dict(item)
        name_key = item.get("name", "").lower().split()[0] if item.get("name") else ""

        # If model/manufacturer empty, try to fill from paper
        if name_key and (not item.get("model") or not item.get("manufacturer")):
            match = paper_equip_by_name.get(name_key)
            if match:
                if not item.get("model") and match.get("model"):
                    item["model"] = match["model"]
                if not item.get("manufacturer") and match.get("manufacturer"):
                    item["manufacturer"] = match["manufacturer"]

        enriched.append(item)

    return enriched


# ---------------------------------------------------------------------------
# Principle 4: Extract QC criteria
# ---------------------------------------------------------------------------

def extract_qc_criteria(text: str, step_name: str = "") -> str:
    """Extract quality control criteria from paper text.

    Looks for patterns:
    - "verified by..." / "confirmed by..." / "validated using..."
    - "quality control..." / "QC..."
    - Acceptance criteria patterns

    Returns QC criteria string or ''.
    """
    if not text:
        return ""

    qc_patterns = [
        r'(?:verified|confirmed|validated|checked|assessed|monitored)\s+(?:by|using|with|via)\s+([^.;]{10,80})',
        r'(?:quality\s+control|QC)[:\s]+([^.;]{10,80})',
        r'(?:acceptance\s+criteri(?:a|on))[:\s]+([^.;]{10,80})',
        r'(?:purity|yield|recovery)\s+(?:was|were|of)\s+([^.;]{10,60})',
    ]

    results = []
    for pattern in qc_patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        results.extend(m.strip() for m in matches[:2])

    return "; ".join(results[:3]) if results else ""


# ---------------------------------------------------------------------------
# Principle 5: Compute real completeness score
# ---------------------------------------------------------------------------

def compute_completeness(case_data: dict) -> dict:
    """Compute real completeness score based on actual data presence.

    Scoring weights:
    - metadata block (14 fields): 30%
    - steps detail (per step: conditions, equipment, result_qc, reagents): 40%
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
            step_fields = {
                "step_name": bool(step.get("step_name")),
                "description": bool(step.get("description") and
                                   str(step.get("description")) != "[미기재]"),
                "conditions": bool(step.get("conditions") and
                                  str(step.get("conditions")) != "[미기재]"),
                "equipment": bool(step.get("equipment")),
                "result_qc": bool(step.get("result_qc") and
                                 str(step.get("result_qc")) != "[미기재]"),
                "reagents": bool(step.get("reagents") and
                                str(step.get("reagents")) != "[미기재]"),
            }
            step_scores.append(sum(step_fields.values()) / len(step_fields))
        scores["steps"] = sum(step_scores) / len(step_scores)
    else:
        scores["steps"] = 0.0

    # 3. Structural blocks (15%)
    struct_present = 0
    struct_total = 3
    if case_data.get("flow_diagram"):
        struct_present += 1
    if case_data.get("workflow_context"):
        struct_present += 1
    if case_data.get("completeness"):
        struct_present += 1
    scores["structure"] = struct_present / struct_total

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

    # Weighted total
    total = (
        scores["metadata"] * 0.30
        + scores["steps"] * 0.40
        + scores["structure"] * 0.15
        + scores["documentation"] * 0.15
    )

    # Generate notes
    notes_parts = []
    if scores["metadata"] < 0.5:
        notes_parts.append("metadata incomplete")
    if scores["steps"] < 0.5:
        notes_parts.append("step details sparse")
    if scores["structure"] < 1.0:
        notes_parts.append("structural blocks missing")
    if not notes_parts:
        notes_parts.append("well-populated")

    return {
        "score": round(total, 3),
        "details": {k: round(v, 3) for k, v in scores.items()},
        "notes": f"Computed by wf-migrate v2.0: {', '.join(notes_parts)}",
    }


# ---------------------------------------------------------------------------
# Principle 6: Mark unverifiable data
# ---------------------------------------------------------------------------

def mark_unverifiable(case_data: dict) -> dict:
    """Mark fields that couldn't be verified from paper as [미기재].

    Only marks fields that are completely empty (not partial data).
    Preserves existing non-empty values.

    Returns modified case_data (mutated).
    """
    metadata = case_data.get("metadata", {})
    for field in ("organism", "scale", "core_technique", "purpose"):
        if not metadata.get(field) or not str(metadata.get(field, "")).strip():
            metadata[field] = "[미기재]"

    steps = case_data.get("steps", [])
    for step in steps:
        for field in ("conditions", "reagents", "result_qc"):
            if not step.get(field) or not str(step.get(field, "")).strip():
                step[field] = "[미기재]"

    return case_data


# ---------------------------------------------------------------------------
# Methods section extraction from full text
# ---------------------------------------------------------------------------

_METHODS_HEADINGS = re.compile(
    r'(?:^|\n)\s*(?:\d+\.?\s*)?'
    r'(Materials?\s+and\s+Methods|Methods|Experimental(?:\s+Procedures)?'
    r'|Experimental\s+Section|Supplementary\s+Methods)'
    r'\s*\n',
    re.IGNORECASE,
)

_NEXT_HEADING = re.compile(
    r'\n\s*(?:\d+\.?\s*)?'
    r'(?:Results|Discussion|Conclusions?|Acknowledgments?|References|Funding'
    r'|Author\s+Contributions?|Competing\s+Interests?|Data\s+Availability)'
    r'\s*\n',
    re.IGNORECASE,
)


def _extract_methods_section(full_text: str) -> str:
    """Extract Methods/Materials and Methods section from full text.

    Falls back to full text if no Methods section heading found.
    """
    if not full_text:
        return ""

    match = _METHODS_HEADINGS.search(full_text)
    if not match:
        # No methods heading found — return full text (capped)
        return full_text[:50_000]

    start = match.start()
    # Find next major heading after Methods
    end_match = _NEXT_HEADING.search(full_text, match.end())
    if end_match:
        methods = full_text[start:end_match.start()]
    else:
        methods = full_text[start:]

    # If methods section is too short, append the rest as supplement
    if len(methods) < 500 and len(full_text) > len(methods):
        return full_text[:50_000]

    return methods[:50_000]


# ---------------------------------------------------------------------------
# Main enrichment entry point
# ---------------------------------------------------------------------------

def enrich_case_card(case_data: dict, paper_info: dict,
                     composition_data: dict = None) -> dict:
    """Full enrichment of a single case card using paper information.

    Applies all 6 principles:
    1. Extract metadata from paper
    2. Enrich step details
    3. Extract equipment details
    4. Extract QC criteria
    5. Compute real completeness
    6. Mark unverifiable data

    Args:
        case_data: existing case card dict
        paper_info: enriched paper dict (with abstract, etc.)
        composition_data: workflow composition_data.json (for workflow_context)

    Returns:
        Enriched case card dict.
    """
    enriched = dict(case_data)
    full_text = paper_info.get("full_text", "")
    abstract = paper_info.get("abstract", "")
    paper_text = _extract_methods_section(full_text) if full_text else str(abstract)

    # 1. Build/enrich metadata
    enriched["metadata"] = extract_metadata_from_paper(paper_info, enriched)

    # 2 & 3 & 4. Enrich each step
    steps = enriched.get("steps", [])
    enriched_steps = []
    for step in steps:
        step = enrich_step_details(step, paper_text)
        step["equipment"] = enrich_step_equipment(step, paper_text)
        enriched_steps.append(step)
    enriched["steps"] = enriched_steps

    # 5. Compute real completeness
    enriched["completeness"] = compute_completeness(enriched)

    # Build flow_diagram with QC markers
    step_names = [s.get("step_name", "") for s in enriched_steps]
    qc_steps = [
        i + 1 for i, s in enumerate(enriched_steps)
        if s.get("result_qc") and str(s.get("result_qc")) not in ("[미기재]", "")
    ]
    if step_names:
        parts = []
        for i, name in enumerate(step_names):
            parts.append(name)
            if (i + 1) in qc_steps:
                parts.append("[QC]")
        enriched["flow_diagram"] = " -> ".join(parts)

    # Build workflow_context from composition_data
    if composition_data:
        modularity = composition_data.get("modularity", {})
        enriched["workflow_context"] = {
            "workflow_id": composition_data.get("workflow_id", ""),
            "migration_source": "wf-migrate v2.1.0",
            "boundary_inputs": [
                (inp if isinstance(inp, str) else inp.get("name", ""))
                for inp in modularity.get("boundary_inputs", [])
            ],
            "boundary_outputs": [
                (out if isinstance(out, str) else out.get("name", ""))
                for out in modularity.get("boundary_outputs", [])
            ],
        }

    # 6. Mark unverifiable
    enriched = mark_unverifiable(enriched)

    return enriched


def is_enriched(case_data: dict) -> bool:
    """Check if a case card has already been enriched.

    Enriched = has completeness with score > 0 AND metadata.pmid is non-empty.
    """
    completeness = case_data.get("completeness", {})
    score = completeness.get("score", 0)
    if isinstance(score, (int, float)) and score > 0:
        metadata = case_data.get("metadata", {})
        pmid = str(metadata.get("pmid", "")).strip()
        if pmid and pmid != "[미기재]":
            return True
    return False
