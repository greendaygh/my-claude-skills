---
skill: wf-analysis
trigger: /wf-analysis
description: >
  Analyze collected case cards to derive common workflow patterns, variants,
  and map to standardized Unit Operations with typed 7-component structures.
version: 2.1.0
author: SBLab KRIBB
tags: [biofoundry, workflow, analysis, unit-operation, variant]
---

# WF-Analysis v2.1 — Case Analysis & UO Mapping

Analyze case cards, derive workflow patterns, map to Unit Operations, and compose typed variant structures.

## Invocation

```
/wf-analysis {wf_dir}
```

**Prerequisites**:
- `{wf_dir}/02_cases/case_C*.json` — at least 3 case cards
- `{wf_dir}/02_cases/case_summary.json` — case summary

## Reference Files

| Phase | Files |
|-------|-------|
| 3 Analyze | `references/case-analysis-guide.md`, `references/unit-operation-mapping.md` |
| 4 Compose | `references/hw-component-guide.md`, `references/sw-component-guide.md`, `references/qc-checkpoint-guide.md` |

## Phase 3 — Analyze

### 3.1 Case Comparative Analysis — per `references/case-analysis-guide.md`

- Step alignment: align cases by functional equivalence
- Common step identification: mandatory (>=60%), conditional, branch points
- Variant derivation: cluster by technique, scale, organism (min 2 cases per variant)
- Parameter ranges: aggregate per-step statistics
- Modularity analysis: boundary I/O, upstream/downstream workflows

Save to `03_analysis/`.

### 3.2 UO Mapping — per `references/unit-operation-mapping.md`

- Multi-signal scoring: equipment 0.35, function 0.30, I/O 0.20, context 0.15
- Score >= 0.7 = strong match
- Classify HW vs SW per decision tree

Save `04_workflow/uo_mapping.json`, `04_workflow/qc_checkpoints.json`.

### 3.3 Peer Review — Invoke `scientific-skills:peer-review`

Submit analysis results for structured review:
- Reviewer focus: variant classification, UO mapping accuracy, QC checkpoint placement
- Input: `03_analysis/common_pattern.json` + `04_workflow/uo_mapping.json`
- If review suggests revisions → address and re-submit (max 1 iteration)
- Save review to `06_review/peer_review.md`

## Phase 4 — Compose

### 4.1 7-Component Population

For each UO in each variant, populate typed components from case data:
- **HW UO**: Input, Output, Equipment, Consumables, Material/Method, Result, Discussion → `references/hw-component-guide.md`
- **SW UO**: Input, Output, Parameters, Environment, Method, Result, Discussion → `references/sw-component-guide.md`
- Every value must include `case_refs` and `evidence_tag`

Save `04_workflow/variant_V1_*.json`, etc.

#### Canonical Variant File Format (MANDATORY)

All variant files MUST use the canonical format:

| Field | Canonical Key | Legacy (do NOT use) |
|-------|---------------|---------------------|
| UO sequence | `unit_operations` | ~~`uo_sequence`~~ |
| Variant name | `variant_name` | ~~`name`~~ |
| Case references | `case_ids` | ~~`case_refs`~~, ~~`cases`~~, ~~`supporting_cases`~~ |
| Step position | `step_position` (integer) | ~~string position~~ |
| Components | Flat on UO object (`input`, `output`, `equipment`, ...) | ~~nested under `components` wrapper~~ |
| Material/Method | `material_and_method` | ~~`Material_Method`~~ |

### 4.2 QC Checkpoint Design — per `references/qc-checkpoint-guide.md`

### 4.3 Gap-Fill Search

For components with many `[미기재]` items:
- Targeted WebSearch for manufacturer protocols, application notes
- Generate expert-inference items list

## External Skill Dependencies

| Skill | Purpose | Step |
|-------|---------|------|
| `scientific-skills:peer-review` | Structured analysis review | 3.3 |

## Output Contract

```
{wf_dir}/
├── 03_analysis/
│   ├── step_alignment.json
│   ├── cluster_result.json
│   ├── common_pattern.json
│   └── parameter_ranges.json
├── 04_workflow/
│   ├── uo_mapping.json
│   ├── variant_V1_*.json ... variant_VN_*.json
│   └── qc_checkpoints.json
└── 06_review/
    └── peer_review.md
```

## Evidence Tagging

| Priority | Tag | Description |
|---|---|---|
| 1 | `literature-direct` | Paper Methods/Results direct extraction |
| 2 | `literature-supplementary` | From supplementary materials |
| 3 | `literature-consensus` | Multiple cases agree |
| 4 | `manufacturer-protocol` | Equipment/kit manufacturer docs |
| 5 | `expert-inference` | Inferred — reasoning required |
| 6 | `catalog-default` | UO catalog default (last resort) |
