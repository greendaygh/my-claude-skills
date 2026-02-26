---
skill: wf-output
trigger: /wf-output
description: >
  Generate final output documents, visualizations, and translations for composed workflows.
  Produces reports, JSON data, Mermaid diagrams, and Korean translations.
version: 2.1.0
author: SBLab KRIBB
tags: [biofoundry, workflow, output, visualization, report]
---

# WF-Output v2.0 — Report Generation & Visualization

Generate final output documents, visualizations, and Korean translations for a composed workflow.

## Invocation

```
/wf-output {wf_dir}
```

**Prerequisites**:
- `{wf_dir}/04_workflow/variant_V*.json` — at least 1 variant file
- `{wf_dir}/04_workflow/uo_mapping.json` — UO mapping

## Reference Files

| File | Purpose |
|------|---------|
| `references/visualization-guide.md` | Mermaid graph specifications |
| `references/output-templates.md` | Report/JSON templates |

## Phase 5 — Output

### 5.1 Generate Reports

- `composition_data.json` — machine-readable JSON (see `references/output-templates.md` for schema)
- `composition_report.md` — human-readable report (English)
- `composition_workflow.md` — workflow reference card (English)

Invoke `scientific-skills:scientific-writing` for report generation support.

#### composition_report.md — MANDATORY 13 Sections (exact names and order)

Do NOT rename, reorder, merge, or omit any section. Every report MUST contain exactly these 13 `## ` headings:

| # | Section Heading (exact) |
|---|------------------------|
| 1 | Workflow Overview |
| 2 | Literature Search Summary |
| 3 | Case Summary |
| 4 | Common Workflow Structure |
| 5 | Variants |
| 6 | Variant Comparison |
| 7 | Parameter Ranges |
| 8 | Equipment & Software Inventory |
| 9 | Evidence and Confidence |
| 10 | Modularity and Service Integration |
| 11 | Limitations and Notes |
| 12 | Catalog Feedback |
| 13 | Execution Metrics |

Do NOT use alternative names like "Executive Summary", "Scope and Objectives", "Literature Basis", "Decision Guide", "Composition Metadata", etc. Use the exact names above.

#### composition_workflow.md — MANDATORY 5 Sections (exact names and order)

| # | Section Heading (exact) |
|---|------------------------|
| 1 | Common Workflow Skeleton |
| 2 | Variants |
| 3 | Parameter Quick-Reference |
| 4 | Boundary I/O |
| 5 | Service Chains |

Within "Variants", each variant is a `### V{n}: {name}` subsection containing a UO Sequence table with columns: Step, UO ID, UO Name, Instance Label, Type, Key Equipment/Software, Key Parameters. Each variant subsection ends with QC Checkpoints.

### 5.2 Validation (GATE) — Report Section Verification

**CRITICAL: `validate_report_sections()` must pass before Korean translation proceeds.**
If missing sections are detected, supplement the report and re-validate.

Run `wf-output/scripts/validate.py`:
- All 13 report sections present in `composition_report.md`
- All case cards have required fields
- All UO mappings have case_refs
- All variants have at least 2 supporting cases
- `composition_data.json` schema valid

Also run `workflow-composer/scripts/validate_workflow.py` for cross-skill validation.

Save validation report to `00_metadata/validation_report.json`.

### 5.3 Korean Translation — Delegate to OMC `writer` agent

Launch Task agent (subagent_type: `oh-my-claudecode:writer`) to translate:
- `composition_report.md` → `composition_report_ko.md`
- `composition_workflow.md` → `composition_workflow_ko.md`

### 5.4 Visualization — Invoke `scientific-skills:scientific-visualization`

Per `references/visualization-guide.md`:
- UO workflow graphs (Mermaid): HW=blue, SW=green, QC=amber
- Variant comparison graph
- Workflow context graph (upstream/downstream connections)

Save to `05_visualization/`.

### 5.5 Update Index — Update `index.json` global workflow index

## External Skill Dependencies

| Skill | Purpose | Step |
|-------|---------|------|
| `scientific-skills:scientific-visualization` | Publication-quality graphs | 5.3 |
| `scientific-skills:scientific-writing` | Report generation support | 5.1 |
| `oh-my-claudecode:writer` | Korean translation | 5.2 |

## Output Contract

```
{wf_dir}/
├── 00_metadata/
│   └── validation_report.json
├── 05_visualization/
│   ├── workflow_graph_V*.mmd
│   ├── variant_comparison.mmd
│   └── workflow_context.mmd
├── composition_report.md
├── composition_report_ko.md
├── composition_data.json
├── composition_workflow.md
└── composition_workflow_ko.md
```
