# Migration Guide — wf-migrate v1.0.0

## Overview

This guide documents the migration methodology for converting legacy workflow
compositions to canonical (v2) format.

## Legacy Schema Eras

### v1_legacy_flat (e.g., WB140)
- Top-level: `{case_id, paper_id, title, technique, organism, scale, steps, notes}`
- Steps: `{position, name, description, parameters, equipment (strings)}`
- 1 workflow identified

### v1_wt_extended (e.g., WT050, WT060, WT070, WT080, WT085)
- Top-level: `{case_id, paper_id, technique, variant_hint, steps}`
- Steps: `{position, action, parameters, equipment (mixed)}`
- ~7 workflows identified

### v1_wt_findings (e.g., WT120, WT130, WT150, WT160)
- Top-level: `{case_id, paper_id, variant/variant_cluster, workflow_steps, key_findings}`
- Uses `workflow_steps` instead of `steps`
- Steps: `{position, action, parameters}`
- ~4 workflows identified

### v2_canonical (target format)
- Top-level: `{case_id, metadata, steps, completeness, flow_diagram, workflow_context}`
- Metadata: 14 required fields
- Steps: `{step_number, step_name, description, equipment, software, reagents, conditions, result_qc, notes}`
- Equipment: `[{name, model, manufacturer}]`
- Software: `[{name, version, developer}]`

## Transform Details

### Parameters → Conditions

Legacy `parameters` is a dict; canonical `conditions` is a string.

Transform rule: flatten nested dicts with dot notation, join as comma-separated `key: value` pairs.

```
Input:  {"temperature": "37C", "rpm": "200", "reaction": {"time": "5min"}}
Output: "temperature: 37C, rpm: 200, reaction.time: 5min"
```

### Equipment Normalization

| Input Format | Output |
|---|---|
| `"Autoclave"` | `{"name": "Autoclave", "model": "", "manufacturer": ""}` |
| `{"name": "QuBit", "manufacturer": "TF"}` | `{"name": "QuBit", "model": "", "manufacturer": "TF"}` |
| `{"name": "X", "model": "Y", "manufacturer": "Z"}` | Passthrough |

Note: `model` and `manufacturer` fields are left empty for flat string inputs.
These should be manually curated post-migration for important equipment.

### Metadata Construction

Built from two sources:
1. **Paper list lookup**: `paper_id` → match in `paper_list.json` → extract pmid, doi, authors, year, journal, title
2. **Case fields**: organism, scale, technique → core_technique, case title → purpose

Default values for fields that cannot be derived:
- `automation_level`: "manual"
- `fulltext_access`: False
- `access_method`: "unknown"
- `access_tier`: 3

### Case ID Fix

Bare case IDs like `C001` get the workflow prefix: `WB140-C001`.
Already-prefixed IDs (matching `^W[BTDL]\d{3}-C\d{3,}$`) are unchanged.

### Statistics Field Renaming

| Deprecated | Standard |
|---|---|
| `total_papers` | `papers_analyzed` |
| `total_cases` | `cases_collected` |
| `total_variants` | `variants_identified` |
| `total_uo_types` | `total_uos` |

## Post-Migration Manual Review

After automated migration, these fields need manual curation:

1. **Equipment model/manufacturer**: Flat strings converted with empty model/manufacturer
2. **Metadata automation_level**: Defaulted to "manual" — verify per case
3. **Metadata fulltext_access/access_method/access_tier**: Defaulted — update based on actual access
4. **Completeness score**: Set to 0.0 — re-evaluate based on actual data quality
5. **Flow diagram**: Auto-generated from step names — may need refinement

## Backup Strategy

All migrations create backups at `{wf_dir}/_versions/pre_migration/`:
- `02_cases/` — original case card JSON files
- `composition_data.json` — original composition data

To restore: copy files from `_versions/pre_migration/` back to their original locations.
