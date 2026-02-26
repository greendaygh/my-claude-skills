# Audit Guide — wf-audit v1.0.0

## Methodology

The wf-audit skill performs a **read-only** analysis of workflow composition outputs,
comparing each file against canonical schemas defined in `assets/canonical_schemas.json`.

### Principles
1. **Non-destructive**: No files are modified, no subprocess calls, no validation reports overwritten
2. **Schema-first**: All conformance checks derive from canonical_schemas.json (Single Source of Truth)
3. **Partial credit**: Alias matches and wrong-type fields receive partial scores instead of binary pass/fail
4. **Cross-workflow**: Drift detection identifies inconsistencies across the full corpus

## Schema Eras

Workflow compositions evolved through several schema generations:

### v2_canonical (current standard)
- Case cards: `{case_id, metadata, steps, completeness, flow_diagram, workflow_context}`
- Metadata block: 14 required fields (pmid, doi, authors, year, journal, title, purpose, organism, scale, automation_level, core_technique, fulltext_access, access_method, access_tier)
- Steps: `{step_number, step_name, description, equipment, software, reagents, conditions, result_qc, notes}`
- Equipment: list of `{name, model, manufacturer}`
- Software: list of `{name, version, developer}`

### v1_legacy_flat
- Case cards: `{case_id, paper_id, title, technique, organism, scale, steps}`
- No metadata block
- Steps use `position` instead of `step_number`, `name` instead of `step_name`
- Equipment as flat string arrays: `["Autoclave", "Centrifuge"]`
- Parameters as dict instead of conditions string

### v1_wt_extended
- Like v1_legacy_flat but with `variant_hint` or `variant_cluster` field
- Steps use `position` + `action` (instead of description)
- Common in WT-prefixed (Test category) workflows

### v1_wt_findings
- Has `workflow_steps` + `key_findings` at top level
- Step structure varies widely

### v1_unknown
- Does not match any known pattern

## Scoring Details

### Case Card Scoring (weight: 0.25)
- Top-level keys: 40% of score (6 required fields)
- Metadata fields: 30% of score (14 required fields)
- Step fields: 30% of score (9 required fields per step, averaged across all steps)

Equipment/software type scoring per step:
- `[{name, model, manufacturer}]` → 1.0
- `["string", "string"]` → 0.5 (wrong_type)
- Missing → 0.0

### Paper List Scoring (weight: 0.10)
- Required top-level (`papers` key): 40%
- Recommended top-level (`search_date`, `workflow_id`, `total_papers`): 20%
- Per-paper required fields (6 fields): 40%

Known paper_list.json variations (5+):
1. `{"papers": [{paper_id, doi, pmid, title, authors, year, journal, ...}]}` — canonical
2. `{"papers": [{...}], "search_date": "...", "workflow_id": "...", "total_papers": N}` — canonical with recommended
3. `[{paper_id, doi, ...}]` — flat array (no wrapper)
4. `{"papers": [{...}]}` with extra fields (cited_by_count, oa_status, openalex_id, search_source, relevance_score)
5. `{"papers": [{...}]}` with minimal fields (missing pmid or doi)

### Variant Scoring (weight: 0.15)
- Required top-level keys: `variant_id`, `variant_name`, `uo_sequence`
- `variant_id` pattern: `^V\d+$` (canonical) vs `WB\d+-V\d+` (non-canonical → 0.0)
- `uo_sequence` must be a list

### Composition Data Scoring (weight: 0.20)
- Schema version must start with "4."
- 8 required top-level fields
- Statistics must use standard names (not deprecated)

Statistics field name mapping:
| Deprecated | Standard |
|-----------|----------|
| total_papers | papers_analyzed |
| total_cases | cases_collected |
| total_variants | variants_identified |
| total_uo_types | total_uos |

Additional non-standard statistics fields observed:
- `techniques_covered`, `year_range`, `journal_count` — informational, not penalized

### Report Section Scoring (weight: 0.15)
- Checks for 13 numbered sections via regex `^#{1,3}\s*\d+\.`
- Score = sections_found / 13

### UO Mapping Scoring (weight: 0.10)
- Binary: 1.0 if `04_workflow/uo_mapping.json` exists and is non-empty, 0.0 otherwise

### Referential Integrity Scoring (weight: 0.05)
- Score = max(0.0, 1.0 - violation_count * 0.1)
- Each violation deducts 0.1 from score

## Cross-Workflow Drift Detection

Drift is detected when the same field has 2+ name variations across workflows:
- **Statistics field drift**: e.g., `cases_collected` in WB005 but `total_cases` in WT050
- Output includes canonical_name, found_names, and affected_workflows

## Step Key Aliases

The following aliases are recognized with partial credit (0.3):

| Canonical | Aliases |
|-----------|---------|
| step_number | position, order |
| step_name | name |
| conditions | parameters |
| result_qc | qc_checkpoints, qc_criteria, qc_measures |
| description | action |

## Output Files

### Per-workflow: `{wf_dir}/00_metadata/audit_report.json`
Contains: audit_version, workflow_id, conformance_score, migration_priority,
schema_era, step_field_style, per-component scores with violations,
existing validation reference, migration recommendations.

### Batch summary: `{base_dir}/audit_summary.json`
Contains: total_workflows, mean_conformance, schema_era_distribution,
conformance_histogram, cross_workflow_drift, migration_candidates,
top_common_violations.
