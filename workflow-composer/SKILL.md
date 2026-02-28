---
skill: workflow-composer
trigger: /workflow-composer
description: >
  Orchestrate biofoundry workflow composition through sub-skill delegation.
  Phase 1 (Resolve) runs locally; Phases 2-5 are delegated to wf-literature,
  wf-analysis, and wf-output skills for context isolation and independent re-runs.
version: 2.5.0
author: SBLab KRIBB
tags: [biofoundry, workflow, orchestrator, unit-operation, literature-mining]
---

# Workflow Composer v2.5 — Orchestrator

Compose biofoundry workflows (~37 standard workflows, ~80 unit operations) through **case-first literature mining**. Supports two delegation modes: sub-skill chaining (default) and deep-executor (for batch processing).

## Invocation

```
/workflow-composer WB030                  # New or Update (auto-detect)
/workflow-composer WB030 DNA Assembly     # ID + name
/workflow-composer WB030 --fresh          # Delete existing, start fresh
/workflow-composer WB030 --deep           # Use deep-executor mode (single agent)
/workflow-composer WB* --fresh --deep     # Batch: all WB* workflows, deep-executor
```

**Modes**: **New** (no existing data) | **Update** (existing found, add new papers + re-analyze). `--fresh` flag = backup existing + run as New.

**Delegation Modes**:
- **Default (sub-skill chaining)**: Phases 2-5 delegated to `/wf-literature`, `/wf-analysis`, `/wf-output` sequentially. Best for single workflows with precise quality control.
- **`--deep` (deep-executor)**: Phases 2-5 delegated to a single `oh-my-claudecode:deep-executor` agent. Best for batch processing multiple workflows. Requires `references/deep-executor-guide.md` as context.

## Core Approach

```
Papers -> Individual Cases -> Comparative Analysis -> Common Patterns -> UO Mapping -> Visualization
```

1. Collect individual cases faithfully (1 paper = 1 case card)
2. Compare and analyze cases to find commonalities and differences
3. Derive common workflow and variants inductively from the data
4. Map to UO catalog and populate typed 7-component structures
5. Visualize as UO directed graphs with QC checkpoints

## Reference Files

| Phase | Files |
|-------|-------|
| 1 Resolve | `assets/workflow_catalog.json`, `assets/uo_catalog.json`, `assets/domain_classification.json` |
| Deep-executor | `references/deep-executor-guide.md` (consolidated guide for all phases) |

## Source Data

| Role | Path |
|------|------|
| Workflow definitions | `/home/haseong/cl/workflow_list.md` |
| UO definitions | `/home/haseong/cl/unitoperation_list.md` |
| Concept framework | `/home/haseong/cl/workflow_unitoperation.md` |

---

## Execution Logging

Use `scripts/simple_logger.py` to track phase timing and errors throughout execution.

**Initialization** (Phase 1, after creating output directory):
```python
from scripts.simple_logger import create_logger
logger = create_logger(wf_dir)
```

**Per-Phase** — wrap each phase:
```python
logger.phase_start("1_resolve", "Parsing workflow input")
# ... phase work ...
logger.phase_end("1_resolve", "Created output directory")
```

**On Errors** — log before continuing or aborting:
```python
logger.error("OpenAlex search failed", phase="2_collect", details="timeout after 30s")
```

**Always Save** — at end of execution AND after any fatal error:
```python
logger.save()  # writes 00_metadata/execution_log.json
```

Phase names: `1_resolve`, `2_collect`, `3_analyze`, `4_compose`, `5_output`

**Rules**:
- Initialize logger immediately after `wf_dir` is created/resolved in Phase 1
- Call `logger.save()` even on partial completion — the log must capture where things failed
- Log all external skill invocation failures (openalex, pubmed, peer-review, etc.)
- Log validation failures from `scripts/validate.py`

---

## Phase 1 — Resolve (~30s)

1. Parse input: extract workflow ID, name, flags
2. **Auto-detect mode**: Use `Glob(pattern="composition_data.json", path="./workflow-compositions/{WF_ID}_*/")`.
   - Found + no `--fresh` → **Update**: load existing `composition_data.json`, `paper_list.json`, `case_summary.json`. Backup to `_versions/`
   - Found + `--fresh` → **Fresh**: backup to `_versions/`, proceed as New
   - Not found → **New**
3. Load workflow from `assets/workflow_catalog.json`
4. Load UO catalog from `assets/uo_catalog.json`
5. Classify domain via `assets/domain_classification.json`
6. Create output directory: `./workflow-compositions/{WF_ID}_{WF_NAME}/` with subdirs
7. Save `00_metadata/workflow_context.json`

## Orchestration — Sub-Skill Delegation

After Phase 1 completes, invoke sub-skills sequentially with verification gates:

### Phase 2 — Literature Collection
```
/wf-literature {wf_dir}
```
**Gate**: Verify `02_cases/case_summary.json` exists and contains >= 3 cases.

### Phase 3+4 — Analysis & Composition
```
/wf-analysis {wf_dir}
```
**Gate**: Verify `04_workflow/uo_mapping.json` and at least one `04_workflow/variant_V*.json` exist.

### Phase 5 — Output
```
/wf-output {wf_dir}
```
**Gate**: Verify `composition_data.json` and `composition_report.md` exist in `{wf_dir}/`.

### Error Recovery

Each sub-skill can be re-invoked independently:
- If Phase 2 fails: fix issues, re-run `/wf-literature {wf_dir}`
- If Phase 3+4 fails: re-run `/wf-analysis {wf_dir}` (Phase 2 outputs preserved)
- If Phase 5 fails: re-run `/wf-output {wf_dir}` (Phase 3+4 outputs preserved)

---

## Orchestration — Deep-Executor Delegation (`--deep` mode)

When `--deep` flag is set or batch processing multiple workflows, delegate Phases 2-5 to a single `oh-my-claudecode:deep-executor` agent.

### How to Delegate

After Phase 1 completes:

1. **Read the consolidated guide**: `references/deep-executor-guide.md`
2. **Spawn deep-executor** with the guide content included in the prompt:

```
Task(
  subagent_type="oh-my-claudecode:deep-executor",
  mode="bypassPermissions",
  prompt="""
  Complete Phases 2-5 for workflow composition.

  Workflow: {WF_ID} - {WF_NAME}
  Directory: {wf_dir}
  Context: {workflow_context.json content}

  CRITICAL: Read and follow the consolidated guide at:
  /home/haseong/.claude/skills/workflow-composer/references/deep-executor-guide.md

  This guide defines MANDATORY structural requirements for:
  - Case cards (structured metadata, equipment as name/model/manufacturer arrays)
  - Analysis files (step_alignment, cluster_result, common_pattern with modularity)
  - Variant files (7-component structure with items[] arrays, NOT flat text)
  - Visualization (subgraph-per-UO, 6-color scheme, color legend)
  - Reports (13 sections, equipment inventory, catalog feedback)

  Phase 2: Search OpenAlex, extract 8-15 cases following case_template.json structure
  Phase 3: Analyze cases → step_alignment, cluster_result, common_pattern, parameter_ranges
  Phase 4: Map UOs, compose variant files with full 7-component structure
  Phase 5: Generate visualization (.mmd), reports (.md), data (.json), Korean translations

  OpenAlex API pattern:
  Use WebSearch to find papers via OpenAlex (https://api.openalex.org/works).
  Example: WebSearch("site:openalex.org {workflow_name} protocol automated")
  Then use WebFetch sequentially (one at a time) on PMC full texts.
  See generate_search_queries.py for query templates and ranking logic.

  Gate checks after each phase:
  - Phase 2: case_summary.json exists with >= 3 cases
  - Phase 3+4: uo_mapping.json + at least one variant_V*.json exist
  - Phase 5: composition_data.json + composition_report.md exist
  """
)
```

### Key Differences from Sub-Skill Mode

| Aspect | Sub-Skill Mode | Deep-Executor Mode |
|--------|---------------|-------------------|
| Context isolation | Each phase in separate context | All phases in single context |
| Guide reference | Each sub-skill loads own guides | Must read `deep-executor-guide.md` |
| Error recovery | Per-phase re-run | Full re-run required |
| Best for | Single workflow, precision | Batch processing, efficiency |
| Gate verification | Orchestrator checks between phases | Agent self-checks |

### Batch Processing Pattern

For multiple workflows (e.g., `WB* --fresh --deep`):

```
from scripts.batch_tracker import BatchTracker

tracker = BatchTracker(output_dir, workflow_ids)

for WF_ID in tracker.get_pending():   # or get_resumable() with --resume
  tracker.start(WF_ID)
  try:
    1. Run Phase 1 locally (backup, clean, create workflow_context.json)
    2. Spawn deep-executor for Phases 2-5 (with guide reference)
    3. Verify gate checks on completion (validate_phase2_gate, validate_phase34_gate, validate_phase5_gate)
    4. Verify canonical format (validate_variant_canonical_format)
    tracker.complete(WF_ID)
  except Exception as e:
    tracker.fail(WF_ID, str(e))
    continue  # skip to next workflow

tracker.finish()
```

**State Tracking**: `batch_state.json` records completed/failed/pending workflows.

**Resume Mode**: Use `--resume` flag. `tracker.get_resumable()` returns failed + pending workflows, skipping already completed ones.

**Error Recovery**:
- Individual failure: re-run the specific workflow with `/workflow-composer {WF_ID}`
- Batch resume: re-run batch with `--resume` flag to continue from where it stopped
- Full restart: delete `batch_state.json` and run batch again

---

## Canonical Variant File Format

All `variant_V*.json` files MUST use the canonical format. This applies to both sub-skill and deep-executor modes.

| Field | Canonical Key | Legacy (do NOT use) |
|-------|---------------|---------------------|
| UO sequence | `unit_operations` | ~~`uo_sequence`~~ |
| Variant name | `variant_name` | ~~`name`~~ |
| Case references | `case_ids` | ~~`case_refs`~~, ~~`cases`~~, ~~`supporting_cases`~~ |
| Step position | `step_position` (integer) | ~~string position~~ |
| Components | Flat on UO object (`input`, `output`, `equipment`, ...) | ~~nested under `components` wrapper~~ |
| Material/Method | `material_and_method` | ~~`Material_Method`~~ |

The canonical schema is defined by Pydantic models in `wf-audit/scripts/models/variant.py`. Use `validate_variant_canonical_format()` from `scripts/validate_workflow.py` to verify.

---

## Schema v4.0.0 — composition_data.json Standard

All `composition_data.json` files MUST conform to Schema v4.0.0. The standard defines required fields, key ordering, and statistics field naming conventions.

### Required Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schema_version` | string | YES | Must start with `"4."` (e.g., `"4.0.0"`) |
| `workflow_id` | string | YES | e.g., `"WB030"` |
| `workflow_name` | string | YES | e.g., `"DNA Assembly"` |
| `category` | string | YES | `"Build"` (WB*) or `"Test"` (WT*) |
| `domain` | string | YES | Domain classification |
| `version` | number | YES | Numeric version (e.g., `3.0`) |
| `composition_date` | string | YES | `YYYY-MM-DD` format |
| `description` | string | YES | Brief description (may be empty) |
| `statistics` | object | YES | See Statistics Fields below |
| `modularity` | object | no | Boundary I/O, upstream/downstream |
| `common_skeleton` | array | no | Common workflow steps |
| `variants` | array | no | Variant definitions |
| `uo_mapping` | object | no | UO mapping data |
| `qc_checkpoints` | array | no | QC checkpoint definitions |
| `related_workflows` | object | no | Upstream/downstream references |
| `parameter_ranges` | array | no | Parameter ranges |
| `equipment_software_inventory` | object | no | Equipment and software |
| `limitations` | array | no | Data/methodological limitations |
| `catalog_feedback` | object | no | UO/WF catalog improvement suggestions |
| `confidence_score` | number | no | Top-level confidence (0.0–1.0) |

### Standard Key Order

Keys in composition_data.json MUST follow this order:
```
schema_version → workflow_id → workflow_name → category → domain →
version → composition_date → description → statistics → modularity →
common_skeleton → variants → uo_mapping → qc_checkpoints →
related_workflows → parameter_ranges → equipment_software_inventory →
limitations → catalog_feedback → confidence_score
```

### Statistics Field Names (Standard)

| Standard Name | Type | Deprecated Alternatives (do NOT use) |
|---------------|------|--------------------------------------|
| `papers_analyzed` | int | `total_papers`, `papers_screened`, `papers_selected`, `papers_retained` |
| `cases_collected` | int | `total_cases`, `cases_extracted` |
| `variants_identified` | int | `total_variants`, `variants_composed` |
| `total_uos` | int | `total_uo_types`, `uo_types_used` |
| `qc_checkpoints` | int | — |
| `confidence_score` | float | — |

### Deprecated Fields (do NOT use)

| Deprecated | Replacement |
|------------|-------------|
| `generated` | `composition_date` (YYYY-MM-DD) |
| `created_at` | `composition_date` |
| `created_date` | `composition_date` |
| `cluster_result` | removed (use `modularity` instead) |

### Index Entry Fields

Each workflow entry in `index.json` MUST include:

| Field | Source |
|-------|--------|
| `category` | `composition_data.category` |
| `papers` | `statistics.papers_analyzed` |
| `cases` | `statistics.cases_collected` |
| `confidence` | `statistics.confidence_score` |
| `last_upgraded` | `composition_data.composition_date` |

## Evidence Tagging

| Priority | Tag | Description |
|---|---|---|
| 1 | `literature-direct` | Paper Methods/Results direct extraction |
| 2 | `literature-supplementary` | From supplementary materials |
| 3 | `literature-consensus` | Multiple cases agree |
| 4 | `manufacturer-protocol` | Equipment/kit manufacturer docs |
| 5 | `expert-inference` | Inferred — reasoning required |
| 6 | `catalog-default` | UO catalog default (last resort) |

## Output Structure

```
./workflow-compositions/{WF_ID}_{WF_NAME}/
├── _versions/                     # Version backups (Update/Fresh mode)
├── 00_metadata/
│   ├── workflow_context.json
│   ├── execution_log.json
│   └── validation_report.json
├── 01_papers/
│   ├── paper_list.json
│   ├── paper_ranking.json
│   └── full_texts/
├── 02_cases/
│   ├── case_C001.json ... case_C0XX.json
│   └── case_summary.json
├── 03_analysis/
│   ├── step_alignment.json
│   ├── cluster_result.json
│   ├── common_pattern.json
│   └── parameter_ranges.json
├── 04_workflow/
│   ├── uo_mapping.json
│   ├── variant_V1_*.json ... variant_VN_*.json
│   └── qc_checkpoints.json
├── 05_visualization/
│   ├── workflow_graph_V*.mmd
│   ├── variant_comparison.mmd
│   └── workflow_context.mmd
├── 06_review/
│   └── peer_review.md
├── composition_report.md
├── composition_report_ko.md
├── composition_data.json
├── composition_workflow.md
└── composition_workflow_ko.md
```
