---
skill: wf-audit
trigger: /wf-audit
description: >
  Audit workflow composition outputs for schema conformance,
  cross-workflow consistency, referential integrity, and drift detection.
  Uses Pydantic v2 canonical models for precise validation with
  detailed per-file, per-record, per-field violation reporting.
version: 2.0.0
author: SBLab KRIBB
tags: [biofoundry, workflow, audit, quality, schema-conformance, pydantic]
---

# wf-audit — Workflow Composition Auditor v2

Audit `/workflow-composer` outputs for schema conformance, cross-workflow consistency,
referential integrity, and drift detection across all workflow compositions.

**v2 upgrade**: Pydantic v2 canonical models as single source of truth.
Detailed violations include file path, record ID, field path, and fix hints.

## Invocation

```
/wf-audit                              # Full batch audit (all workflows)
/wf-audit WB030                        # Single workflow deep audit
/wf-audit WB030 WB140 WT050            # Specific workflows
/wf-audit --summary-only               # Batch summary only (no individual reports saved)
```

## Default Data Directory

`/home/haseong/dev/workflow_compositions/workflow-compositions/`

## Execution Steps

### Step A — Discover
1. Run `discover_workflows(base_dir)` to find all `W*/composition_data.json` dirs
2. Exclude `_versions/` backup directories
3. Gate: >= 1 workflow discovered

### Step B — Schema Conformance (Pydantic v2)
For each workflow:
1. Load `scripts/audit_workflow.py`
2. Call `audit_single_workflow(wf_dir)` which validates **13 file types**:

| # | File | Pydantic Model | Path |
|---|------|---------------|------|
| 1 | composition_data.json | `CompositionData` | root |
| 2 | case cards | `CaseCard` | `02_cases/case_C*.json` |
| 3 | paper_list.json | `PaperList` | `01_papers/` |
| 4 | variant files | `Variant` | `04_workflow/variant_V*.json` |
| 5 | composition_report.md | (section count) | root |
| 6 | uo_mapping.json | `UoMapping` | `04_workflow/` |
| 7 | case_summary.json | `CaseSummary` | `02_cases/` |
| 8 | cluster_result.json | `ClusterResult` | `03_analysis/` |
| 9 | common_pattern.json | `CommonPattern` | `03_analysis/` |
| 10 | parameter_ranges.json | `ParameterRanges` | `03_analysis/` |
| 11 | step_alignment.json | `StepAlignment` | `03_analysis/` |
| 12 | qc_checkpoints.json | `QcCheckpoints` | `04_workflow/` |
| 13 | workflow_context.json | `WorkflowContext` | `00_metadata/` |

3. Each file is validated via `Model.model_validate(data)`.
   `ValidationError` is converted to `DetailedViolation` with file, record, path, error, fix_hint.
4. Produces weighted conformance score (0.0-1.0) and migration priority.

### Step C — Cross-Workflow Analysis
1. Call `detect_cross_workflow_drift(results)` to find:
   - Statistics field name drift (e.g., `total_cases` vs `cases_collected`)
   - Schema era distribution across all workflows
2. Group workflows by schema era

### Step D — Referential Integrity
Included in Step B per-workflow. Checks:
- Case ID ↔ variant supporting_cases references
- UO IDs ↔ UO catalog existence
- Paper PMIDs ↔ paper_list.json
- Statistics counts ↔ actual file counts
- Case ID format pattern compliance
- Paper DOI validity (doi.org resolution)

### Step E — Report
1. Save individual `{wf_dir}/00_metadata/audit_report.json` (unless `--summary-only`)
2. Save batch `{base_dir}/audit_summary.json`
3. Migration priority ranking (critical → high → medium → low → none)

## Canonical Variant Format

All 8 existing variant structures should conform to this canonical format:

```json
{
  "variant_id": "V1",
  "variant_name": "...",
  "workflow_id": "WB005",
  "unit_operations": [
    {
      "uo_id": "UHW400",
      "uo_name": "...",
      "step_position": 1,
      "input": { "items": [...] },
      "output": { "items": [...] },
      "equipment": { "items": [...] },
      "consumables": { "items": [...] },
      "material_and_method": { ... },
      "result": { "measurements": [...], "qc_checkpoint": {...} },
      "discussion": { ... }
    }
  ]
}
```

Key mappings from legacy formats:
- `name` → `variant_name`, `case_refs`/`cases` → `case_ids`
- `uo_sequence` (string/object) → `unit_operations` (object array)
- `uo_order`/`position`/`step_number` → `step_position`
- `Material_Method`/`material_method` → `material_and_method`
- `Input`/`Output` (capital) → `input`/`output` (lowercase)
- `details[]` → `items[]`

## Detailed Violation Output

Each violation includes actionable location info:

```json
{
  "file": "01_papers/paper_list.json",
  "record": "P003",
  "path": "papers.2.doi",
  "error": "Field required",
  "error_type": "missing",
  "fix_hint": "'papers.2.doi' 필드를 추가하세요"
}
```

## Scoring Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| case_cards | 0.25 | Case card structure conformance |
| composition_data | 0.20 | Schema v4.0.0 compliance |
| variant_files | 0.15 | Canonical variant structure |
| report_sections | 0.15 | 13-section report compliance |
| paper_list | 0.10 | Paper list structure |
| uo_mapping | 0.10 | UO mapping structure |
| referential_integrity | 0.05 | Cross-file reference checks |

## Migration Priority

| Score | Priority |
|-------|----------|
| >= 0.9 | none |
| >= 0.7 | low |
| >= 0.5 | medium |
| >= 0.3 | high |
| < 0.3 | critical |

## File References

| File | Purpose |
|------|---------|
| `scripts/models/` | Pydantic v2 canonical models (single source of truth) |
| `scripts/scoring.py` | Pydantic-based conformance scoring engine |
| `scripts/canonical_schemas.py` | Constants derived from Pydantic models |
| `scripts/referential_integrity.py` | Cross-file reference checks |
| `scripts/audit_workflow.py` | Single workflow deep audit |
| `scripts/audit_batch.py` | Batch audit + CLI entry point |
| `requirements.txt` | pydantic>=2.0 |

## Dependencies

- Python 3.11+
- pydantic >= 2.0
- UO catalog: `~/.claude/skills/workflow-composer/assets/uo_catalog.json`
- No subprocess calls — all checks are read-only JSON analysis
