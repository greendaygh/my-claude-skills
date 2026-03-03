---
skill: wf-output
trigger: /wf-output
description: >
  Generate final output documents, visualizations, and translations for composed workflows.
  Produces reports, JSON data, Mermaid diagrams, and Korean translations.
version: 2.3.0
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

### 5.2 Visualization — Invoke `scientific-skills:scientific-visualization`

Per `references/visualization-guide.md`:
- UO workflow graphs (Mermaid): HW=blue, SW=green, QC=amber
- Variant comparison graph
- Workflow context graph (upstream/downstream connections)

Save to `05_visualization/`.

### 5.3 Full Validation Gate 4 — MANDATORY (3 Steps)

**CRITICAL: ALL 3 steps must pass before Korean translation proceeds.**

**Step A: Existing Validation Scripts**

Run `wf-output/scripts/validate.py`:
- All 13 report sections present in `composition_report.md`
- All case cards have required fields
- All UO mappings have case_refs
- All variants have at least 2 supporting cases
- `composition_data.json` schema valid

Also run `workflow-composer/scripts/validate_workflow.py` for cross-skill validation.

**Step B: Full Pydantic Audit**

```python
# Run wf-audit full audit on all 13 file types
from wf_audit.scripts.audit_workflow import audit_single_workflow
result = audit_single_workflow(wf_dir, verbose=True)
# Includes: Pydantic model validation + referential integrity + content quality
```

**Pass**: conformance >= 0.7.

**Step C: Visualization Structure Validation (per `references/visualization-guide.md` Detailed mode)**

Validate `05_visualization/` files against 8 criteria (text parsing, not Pydantic):

1. **File completeness**:
   - variant count == `workflow_graph_V*.mmd` count
   - `variant_comparison.mmd` exists
   - `workflow_context.mmd` exists

2. **classDef color scheme** (6 required classes):
   - `comp_input`: fill:#A8D8EA,stroke:#5B9BD5
   - `comp_output`: fill:#FFD3B6,stroke:#E88D4F
   - `comp_equipment`: fill:#D5A6E6,stroke:#8E44AD
   - `comp_consumables`: fill:#B5EAD7,stroke:#3D9970
   - `comp_material_and_method`: fill:#FFEAA7,stroke:#FDCB6E (compact mode)
   - `qc`: fill:#F0AD4E,stroke:#D48A1A,color:white

3. **UO subgraph structure**:
   - `graph TD` declaration (top-to-bottom overall flow)
   - Each UO = subgraph (node ID: `{uo_id}_{index}_sub`)
   - Component nodes: `{uo_id}_{index}_{3letter}` (inp, out, equ, con)
   - Component labels: "IN:", "OUT:", "EQUIP:", "CONS:" prefixes
   - HW subgraph: `fill:#EBF2FA,stroke:#2C5F8A`; SW subgraph: `fill:#EBF8EB,stroke:#3D7A3D`

4. **Output-to-Input edges** (data flow):
   - Previous UO `_out` node → next UO `_inp` node
   - HW→HW: solid arrow (`-->`); SW involved: dashed (`-.->`)
   - Edge label: first output item name

5. **QC diamond nodes**:
   - `{{ }}` shape (outside UO subgraphs, placed between UO steps)
   - `:::qc` class applied
   - Each `qc_checkpoints` entry has a corresponding QC node
   - Pass: solid arrow → next UO; Fail: dashed + `"Fail: {action}"` label → previous UO

6. **Color Legend** (Detailed mode required):
   - Legend subgraph at bottom with Input, Output, Equipment/Parameters, Consumables/Environment, QC (5 items)
   - Legend style: `fill:#F9F9F9,stroke:#CCCCCC`

7. **UO ID consistency**:
   - Subgraph title UO IDs match `variant_V*.json` uo_id values
   - Also match `uo_mapping.json` primary_uo values

8. **Mermaid syntax integrity**:
   - `subgraph`/`end` pairs balanced
   - Node IDs are valid Mermaid identifiers (alphanumeric + underscore)
   - Edge labels in quotes

Save results to:
- `00_metadata/validation_report.json` (Step A)
- `00_metadata/audit_report.json` (Step B)
- `00_metadata/visualization_validation.json` (Step C)

If missing sections or validation failures detected, fix and re-validate (max 2 retries).

### 5.4 Korean Translation — Delegate to OMC `writer` agent

Launch Task agent (subagent_type: `oh-my-claudecode:writer`) to translate:
- `composition_report.md` → `composition_report_ko.md`
- `composition_workflow.md` → `composition_workflow_ko.md`

### 5.5 Update Index — Update `index.json` global workflow index

## External Skill Dependencies

| Skill | Purpose | Step |
|-------|---------|------|
| `scientific-skills:scientific-visualization` | Publication-quality graphs | 5.2 |
| `scientific-skills:scientific-writing` | Report generation support | 5.1 |
| `oh-my-claudecode:writer` | Korean translation | 5.4 |

## Output Contract

```
{wf_dir}/
├── 00_metadata/
│   ├── validation_report.json
│   ├── audit_report.json
│   └── visualization_validation.json
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
