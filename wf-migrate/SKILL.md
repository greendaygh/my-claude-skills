---
skill: wf-migrate
trigger: /wf-migrate
description: >
  Migrate and enrich legacy workflow compositions to canonical format.
  Phase A performs mechanical field renaming; Phase A.5 applies audit-driven
  targeted fixes; Phase B enriches case cards with PubMed paper metadata
  and regenerates reports. All phases run automatically on every invocation.
  Fix results are recorded in audit_report.json to avoid redundant re-processing.
version: 2.2.0
author: SBLab KRIBB
tags: [biofoundry, workflow, migration, schema-upgrade, enrichment, audit-fix]
---

# wf-migrate — Workflow Composition Migrator & Enricher

Migrate legacy workflow compositions to canonical (v2) format using wf-audit
results as input. Runs three phases automatically:
- **Phase A**: Transforms case cards, renames step fields, builds metadata blocks,
  normalizes equipment/software, migrates composition_data and variant files.
- **Phase A.5**: Reads `audit_report.json` detailed violations and applies targeted
  fixes based on error_type (wrong_type, missing, pattern_mismatch). Records
  fix_status back into audit_report.json to prevent redundant re-processing.
- **Phase B**: Enriches case cards with PubMed paper metadata, computes real
  completeness scores, and regenerates 13-section reports.

## Prerequisites

Run `/wf-audit` first to generate `audit_summary.json` with migration candidates
and per-workflow `audit_report.json` with detailed violations.

## Invocation

```
/wf-migrate WB140                        # Single workflow
/wf-migrate WB140 WT050                  # Multiple specific workflows
/wf-migrate --priority high              # All high+critical priority candidates
/wf-migrate --priority medium            # All medium+ priority candidates
/wf-migrate --dry-run WB140              # Preview changes without writing
```

## Default Data Directory

`/home/haseong/dev/workflow_compositions/workflow-compositions/`

## Phase A — Mechanical Migration

### Step 1 — Discover Candidates
- Read `audit_summary.json` from base directory (or use --targets)
- Filter by priority: critical > high > medium > low

### Step 2 — Backup
- Copy `02_cases/` to `_versions/pre_migration/02_cases/`
- Copy `composition_data.json` to `_versions/pre_migration/`
- Idempotent: skip if backup already exists

### Step 3 — Migrate Case Cards
For each `02_cases/case_C*.json`:
1. Skip if already canonical (has metadata+completeness.score+flow_diagram+workflow_context.workflow_id)
2. Fix case_id prefix if bare (e.g., `C001` → `WB140-C001`)
3. Build metadata block from paper_list.json lookup
4. Rename step fields (position→step_number, name→step_name, etc.)
5. Normalize equipment and software to structured objects
6. Add completeness stub, flow_diagram, workflow_context
7. Preserve extra fields (variant_hint, evidence_tag, etc.)

### Step 4 — Migrate composition_data.json
- Convert `modularity.boundary_inputs/outputs` from object arrays to string arrays
- Rename deprecated statistics fields + fill missing canonical fields with defaults

### Step 5 — Migrate Variant Files
For each `04_workflow/variant_V*.json`:
- Flatten `components` dict to UO top-level keys
- Key mapping: `Input`→`input`, `Material_Method`→`material_and_method`, etc.
- Rename `details`→`items`, `item`→`name`
- Convert `step_position` from string to integer
- Rename `uo_sequence`→`unit_operations`, `case_refs`→`case_ids`, `name`→`variant_name`

### Step 6 — Report
Write migration reports to `00_metadata/`.

## Phase A.5 — Audit-Driven Targeted Fixes

After Phase A mechanical migration, reads `audit_report.json` and applies
targeted fixes based on each violation's `error_type`:

- `wrong_type` + boundary_inputs/outputs → extract `.name` from objects
- `wrong_type` + step_position → cast string to integer
- `wrong_type` + checkpoint_summary → cast string to integer
- `missing` + completeness.score → add default 0.0
- `missing` + workflow_context.workflow_id → extract from composition_data
- `missing` + statistics fields → compute defaults from file counts

Each fix is recorded in `audit_report.json`:
```json
{
  "fix_status": "resolved",
  "fix_action": "object-to-string: name field extracted",
  "fix_timestamp": "2026-02-28T12:00:00Z"
}
```

`fix_status` values:
- `"resolved"` — auto-fixed successfully
- `"unresolved"` — requires manual review
- `"skipped"` — dry-run mode (not written)
- absent — migration not yet applied

A `migration_applied` summary is added to the top level:
```json
{
  "migration_applied": {
    "migrated_at": "...",
    "migration_version": "2.2.0",
    "total_violations_at_audit": 150,
    "resolved": 120,
    "unresolved": 25,
    "skipped": 5,
    "pre_migration_score": 0.643,
    "post_migration_score": 0.89
  }
}
```

On subsequent runs, violations with `fix_status: "resolved"` are skipped.

## Phase B — Enrichment

### B.0 — Paper Re-collection (fake paper repair)

Before B.1, check `audit_summary.json` for `fake_paper_suspects`:

1. Read `{base_dir}/audit_summary.json`
2. If `fake_paper_suspects` contains workflows in the current migration targets:
   - For each flagged workflow, invoke `/wf-literature {wf_dir}`
   - This replaces fake papers with real ones from OpenAlex/PubMed
   - After re-collection, proceed to B.1 (enrichment) as normal
3. If no fake paper suspects, skip this phase

This phase is ONLY triggered when `audit_summary.json` contains `fake_paper_suspects`.
The agent running wf-migrate must check this before starting Python enrichment.

### B.1 — Paper Metadata & Full Text Enrichment (PubMed + PMC API)
- For each paper in `paper_list.json`:
  1. Resolve PMID **and PMCID** from DOI via NCBI ID Converter API
  2. If no PMID, search PubMed by title
  3. Fetch PubMed details: abstract, MeSH terms, full author list
  4. **Fetch PMC full text** (if PMCID available):
     - Priority: PMC Open Access efetch API → Europe PMC REST API → abstract only
     - Methods/Materials and Methods section prioritized over full body
     - Full text capped at 200k chars for memory protection
  5. Merge fetched data (preserving existing non-empty values)
- Each paper receives `text_source` field: `"pmc_oa"` | `"europepmc"` | `"abstract_only"`
- Save enriched `paper_list.json` and full texts (or abstracts) to `01_papers/full_texts/`
- Rate limited: 0.4s/request for all APIs (PubMed, PMC, Europe PMC)

### B.2 — Case Card Enrichment (6-Principle Extraction)
For each case card:
1. **Metadata enrichment**: Build complete 14-field metadata from paper data
2. **Step detail enrichment**: Extract conditions, reagents from paper full text (Methods section preferred) or abstract
3. **Equipment enrichment**: Fill model/manufacturer from paper text
4. **QC criteria extraction**: "verified by...", "confirmed using..." patterns
5. **Real completeness scoring**: Weighted score based on actual data presence
6. **Unverifiable marking**: Empty fields marked as [미기재]

### B.3 — Structural Block Generation
- `completeness`: Real score with weighted sub-scores (metadata 30%, steps 40%, structure 15%, docs 15%)
- `flow_diagram`: Step names with [QC] checkpoint markers
- `workflow_context`: Boundary I/O from composition_data.modularity

### B.4 — Report Regeneration
- `composition_report.md`: 13 mandatory sections
- `composition_workflow.md`: 5 mandatory sections
- Korean translations: `*_ko.md`

## Transforms Reference

### Case Card Transforms
| Legacy Field | Canonical Field | Transform |
|---|---|---|
| `position` | `step_number` | Rename |
| `name` (in step) | `step_name` | Rename |
| `action` | `step_name` + `description` | Rename + duplicate |
| `parameters` (dict) | `conditions` (string) | Flatten: `"key: val, ..."` |
| `equipment` (strings) | `equipment` (objects) | `{name, model, manufacturer}` |
| `software` (strings) | `software` (objects) | `{name, version, developer}` |
| `paper_id` | `metadata.pmid/doi/...` | Paper list lookup |
| `technique` | `metadata.core_technique` | Move to metadata |
| `organism` | `metadata.organism` | Move to metadata |
| `scale` | `metadata.scale` | Move to metadata |
| `workflow_steps` | `steps` | Rename (wt_findings) |

### Composition Data Transforms
| Legacy Field | Canonical Field | Transform |
|---|---|---|
| `modularity.boundary_inputs` (objects) | `modularity.boundary_inputs` (strings) | Extract `.name` |
| `modularity.boundary_outputs` (objects) | `modularity.boundary_outputs` (strings) | Extract `.name` |
| `total_papers` | `papers_analyzed` | Rename |
| `total_cases` | `cases_collected` | Rename |
| `total_variants` | `variants_identified` | Rename |
| `total_uo_types` | `total_uos` | Rename |

### Variant File Transforms
| Legacy Field | Canonical Field | Transform |
|---|---|---|
| `components.Input` | `input` | Flatten + lowercase |
| `components.Output` | `output` | Flatten + lowercase |
| `components.Equipment` | `equipment` | Flatten + lowercase |
| `components.Consumables` | `consumables` | Flatten + lowercase |
| `components.Material_Method` | `material_and_method` | Flatten + rename |
| `components.Result` | `result` | Flatten + lowercase |
| `components.Discussion` | `discussion` | Flatten + lowercase |
| `details` (in component) | `items` | Rename |
| `item` (in detail) | `name` | Rename |
| `step_position` (string) | `step_position` (int) | Cast |
| `uo_sequence` | `unit_operations` | Rename |
| `case_refs` / `cases` | `case_ids` | Rename |
| `name` (top-level) | `variant_name` | Rename |

## File References

| File | Purpose |
|------|---------|
| `scripts/field_transforms.py` | Step field renaming + equipment/software parsing |
| `scripts/metadata_builder.py` | Metadata block construction + completeness scoring |
| `scripts/case_migrator.py` | Single case card migration + enrichment |
| `scripts/variant_migrator.py` | Variant file structure migration (components flattening) |
| `scripts/audit_fixer.py` | Audit-driven targeted fix + fix_status recording |
| `scripts/workflow_migrator.py` | Full workflow migration + enrichment orchestration |
| `scripts/migrate_batch.py` | CLI entry point + batch orchestration |
| `scripts/paper_enricher.py` | PubMed API integration for paper metadata |
| `scripts/case_enricher.py` | 6-principle case card enrichment |
| `scripts/report_generator.py` | 13-section report + 5-section workflow generation |

## Safety

- **Double backup**: `_versions/pre_migration/` (Phase A) + `_versions/pre_enrichment/` (Phase B)
- **Canonical passthrough**: Already-canonical cards are never modified (Phase A); checks both key existence AND required sub-fields (completeness.score, workflow_context.workflow_id)
- **Enrichment idempotency**: `is_enriched()` checks completeness.score > 0 + metadata.pmid present; bypassed for cases with pending audit violations
- **Audit fix idempotency**: Violations with `fix_status: "resolved"` are skipped on re-run
- **API failure isolation**: One paper's PubMed failure doesn't affect other case cards
- **Rate limiting**: PubMed/PMC/Europe PMC 0.4s/request (3 req/sec)
- **Full text fallback**: PMC OA → Europe PMC → abstract only (graceful degradation)
- **Memory protection**: Full text capped at 200k chars; Methods section preferred over full body
- **Data preservation**: Enrichment only adds/updates, never deletes existing values
- **Dry-run mode**: `--dry-run` previews all changes without writing; fix_status set to "skipped"

## Report Sections

### composition_report.md (13 sections)
1. Workflow Overview
2. Literature Search Summary
3. Case Summary
4. Common Workflow Structure
5. Variants
6. Variant Comparison
7. Parameter Ranges
8. Equipment & Software Inventory
9. Evidence and Confidence
10. Modularity and Service Integration
11. Limitations and Notes
12. Catalog Feedback
13. Execution Metrics

### composition_workflow.md (5 sections)
1. Common Workflow Skeleton
2. Variants
3. Parameter Quick-Reference
4. Boundary I/O
5. Service Chains

## Workflow with wf-audit

```
/wf-audit                                    # 1. Audit all workflows
/wf-migrate --dry-run --priority medium      # 2. Preview changes
/wf-migrate --priority medium                # 3. Execute (Phase A + A.5 + B)
# No need to re-audit: audit_report.json is updated with fix_status
/wf-migrate --priority medium                # 4. Re-run: skips already-resolved violations
```

After migration, check `audit_report.json` for:
- `migration_applied.resolved` — number of violations fixed
- `migration_applied.unresolved` — violations requiring manual review
- Each violation's `fix_status` for per-field resolution detail
