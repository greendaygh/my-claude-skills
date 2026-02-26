"""Single case card migration from legacy to canonical format."""

import re
from field_transforms import migrate_step
from metadata_builder import (build_metadata, build_completeness_stub,
                               build_flow_diagram, build_workflow_context,
                               build_completeness, build_flow_diagram_with_qc,
                               build_workflow_context_from_composition)
from case_enricher import (enrich_case_card as _enrich_case_card_impl,
                            is_enriched as _is_enriched_impl)


# Fields that get absorbed into metadata (removed from top level)
_METADATA_SOURCE_FIELDS = {"paper_id", "technique", "organism", "scale", "title"}

# Fields that indicate canonical format
_CANONICAL_MARKERS = {"metadata", "completeness", "flow_diagram", "workflow_context"}

# Pattern for a well-formed canonical case_id: e.g. WB140-C001, WT050-C002
_CANONICAL_CASE_ID_RE = re.compile(r"^W[BTDL]\d{3}-C\d{3,}$")


def is_canonical(case_data: dict) -> bool:
    """Check if a case card is already in canonical format."""
    return all(k in case_data for k in _CANONICAL_MARKERS)


def _fix_case_id(case_id: str, workflow_id: str) -> tuple[str, str | None]:
    """Return (fixed_case_id, change_msg_or_None).

    If case_id already matches canonical pattern, return as-is.
    If workflow_id is provided and case_id looks like a bare "C001", prepend prefix.
    """
    if _CANONICAL_CASE_ID_RE.match(case_id):
        return case_id, None

    if workflow_id and re.match(r"^C\d{3,}$", case_id):
        new_id = f"{workflow_id}-{case_id}"
        return new_id, f"Fixed case_id: {case_id} → {new_id}"

    return case_id, None


def migrate_case_card(case_data: dict, paper_index: dict,
                      workflow_id: str = "", dry_run: bool = False) -> dict:
    """Migrate a legacy case card to canonical format.

    If already canonical, returns as-is (with minimal fixes).

    Steps:
    1. Detect if already canonical → skip if so
    2. Fix case_id prefix if missing
    3. Build metadata from paper_id lookup + existing fields
    4. Handle workflow_steps → steps rename (wt_findings)
    5. Migrate each step via field_transforms.migrate_step()
    6. Add completeness stub, flow_diagram, workflow_context
    7. Remove absorbed top-level fields
    8. Preserve extra fields (variant_hint, evidence_tag, etc.)

    Returns:
        If dry_run=False: the migrated dict
        If dry_run=True: {"migrated": dict, "changes": list[str]}
    """
    changes: list[str] = []

    # 1. Already canonical — return as-is (no double-migration)
    if is_canonical(case_data):
        result = dict(case_data)
        if dry_run:
            return {"migrated": result, "changes": ["Already canonical — no changes made"]}
        return result

    # Work on a shallow copy; we'll build the output explicitly
    src = dict(case_data)

    out: dict = {}

    # 2. Fix case_id
    raw_case_id = src.pop("case_id", "")
    fixed_case_id, case_id_change = _fix_case_id(raw_case_id, workflow_id)
    out["case_id"] = fixed_case_id
    if case_id_change:
        changes.append(case_id_change)

    # 3. Build metadata (uses paper_id, organism, scale, technique, title from src)
    metadata = build_metadata(src, paper_index)
    out["metadata"] = metadata
    changes.append("Added metadata block")

    # 4. Handle workflow_steps → steps rename (WT120 wt_findings style)
    if "workflow_steps" in src and "steps" not in src:
        src["steps"] = src.pop("workflow_steps")
        changes.append("Renamed workflow_steps → steps")

    # 5. Migrate steps
    raw_steps = src.pop("steps", [])
    migrated_steps = []
    for i, step in enumerate(raw_steps, start=1):
        migrated = migrate_step(step)
        migrated_steps.append(migrated)
        # Record notable renames
        if "position" in step:
            changes.append(f"position → step_number in step {i}")
        if "action" in step and "name" not in step:
            changes.append(f"action → step_name in step {i}")
        if "parameters" in step:
            changes.append(f"parameters → conditions in step {i}")
    out["steps"] = migrated_steps

    # 6. Add completeness stub, flow_diagram, workflow_context
    out["completeness"] = build_completeness_stub()
    out["flow_diagram"] = build_flow_diagram(migrated_steps)
    out["workflow_context"] = build_workflow_context(workflow_id)
    changes.append("Added completeness stub")
    changes.append("Added flow_diagram")
    changes.append("Added workflow_context")

    # 7. Remove absorbed top-level fields from src (they moved to metadata)
    for field in _METADATA_SOURCE_FIELDS:
        src.pop(field, None)

    # 8. Preserve all remaining src fields (variant_hint, evidence_tag, etc.)
    out.update(src)

    if dry_run:
        return {"migrated": out, "changes": changes}
    return out


# ---------------------------------------------------------------------------
# Enrichment (Phase B) — delegates to case_enricher module
# ---------------------------------------------------------------------------

def enrich_case_card(case_data: dict, paper_info: dict,
                     composition_data: dict = None) -> dict:
    """Enrich a case card using paper information (6-principle extraction).

    Wrapper around case_enricher.enrich_case_card for unified API.

    Args:
        case_data: existing (already migrated) case card
        paper_info: enriched paper dict with abstract, mesh_terms, etc.
        composition_data: workflow composition_data.json (for workflow_context)

    Returns:
        Enriched case card dict.
    """
    return _enrich_case_card_impl(case_data, paper_info, composition_data)


def is_enriched(case_data: dict) -> bool:
    """Check if a case card has already been enriched (idempotency guard).

    Enriched = completeness.score > 0 AND metadata.pmid is non-empty.
    """
    return _is_enriched_impl(case_data)
