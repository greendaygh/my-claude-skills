---
skill: wf-audit
trigger: /wf-audit
description: >
  Audit workflow composition outputs for schema conformance,
  cross-workflow consistency, referential integrity, and drift detection.
version: 1.0.0
author: SBLab KRIBB
tags: [biofoundry, workflow, audit, quality, schema-conformance]
---

# wf-audit — Workflow Composition Auditor

Audit `/workflow-composer` outputs for schema conformance, cross-workflow consistency,
referential integrity, and drift detection across all workflow compositions.

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

### Step B — Schema Conformance
For each workflow:
1. Load `scripts/audit_workflow.py`
2. Call `audit_single_workflow(wf_dir)` which:
   - Scores case cards (top-level + metadata + step structure + equipment/software types)
   - Scores paper_list.json (required + recommended + per-paper fields)
   - Scores variant files (required keys + variant_id pattern + uo_sequence)
   - Scores composition_data.json (schema v4.0.0 + statistics standard names)
   - Scores composition_report.md (13 numbered sections)
   - Checks uo_mapping.json existence
   - Runs referential integrity checks (read-only)
3. Produces weighted conformance score (0.0-1.0) and migration priority

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

### Step E — Report
1. Save individual `{wf_dir}/00_metadata/audit_report.json` (unless `--summary-only`)
2. Save batch `{base_dir}/audit_summary.json`
3. Migration priority ranking (critical → high → medium → low → none)

## Scoring Weights

| Component | Weight | Description |
|-----------|--------|-------------|
| case_cards | 0.25 | Case card structure conformance |
| composition_data | 0.20 | Schema v4.0.0 compliance |
| variant_files | 0.15 | Variant structure + ID pattern |
| report_sections | 0.15 | 13-section report compliance |
| paper_list | 0.10 | Paper list structure |
| uo_mapping | 0.10 | UO mapping existence |
| referential_integrity | 0.05 | Cross-file reference checks |

## Partial Scoring

| State | Score | Detail |
|-------|-------|--------|
| Present + correct type | 1.0 | `"present"` |
| Present + wrong type | 0.5 | `"wrong_type"` (e.g., flat string array) |
| Alias match | 0.3 | `"alias_match"` (e.g., `position` for `step_number`) |
| Missing | 0.0 | `"missing"` |

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
| `scripts/canonical_schemas.py` | Loads canonical_schemas.json (SSOT) |
| `scripts/scoring.py` | Conformance scoring engine |
| `scripts/referential_integrity.py` | Cross-file reference checks |
| `scripts/audit_workflow.py` | Single workflow deep audit |
| `scripts/audit_batch.py` | Batch audit + CLI entry point |
| `assets/canonical_schemas.json` | Single Source of Truth for all schemas |
| `references/audit-guide.md` | Methodology, schema eras, scoring details |

## External Dependencies

- UO catalog: `~/.claude/skills/workflow-composer/assets/uo_catalog.json`
- No subprocess calls — all checks are read-only JSON analysis

## Agent Integration

| Agent | Use | Step |
|-------|-----|------|
| `oh-my-claudecode:writer` | Polish batch summary markdown | E |
| `scientific-skills:exploratory-data-analysis` | Score distribution visualization (optional) | E |
