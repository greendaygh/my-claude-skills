# Changelog — wf-migrate

## [2.2.0] — 2026-02-28

### Added
- **Phase A.5 — Audit-driven targeted fixes** (`audit_fixer.py`)
  - Reads `audit_report.json` detailed violations, applies fixes by error_type
  - Supports `wrong_type`, `missing`, `pattern_mismatch` error types
  - Records `fix_status`/`fix_action`/`fix_timestamp` per violation
  - `migration_applied` summary block in audit_report.json
  - Idempotent: skips violations with `fix_status: "resolved"` on re-run
- **Variant file migration** (`variant_migrator.py`)
  - Handles 3 legacy patterns (WB005/WB040/WB010 styles)
  - Flattens `components` dict to canonical UO top-level keys
  - Renames `details`→`items`, `item`→`name`, `uo_sequence`→`unit_operations`
  - Casts `step_position` from string to integer
- `migrate_composition_data()` in workflow_migrator — boundary_inputs/outputs object-to-string, statistics defaults
- `_compute_stat_defaults()` — auto-computes missing statistics from file counts
- `has_violations` parameter on `is_enriched()` to bypass idempotency for cards with pending violations
- Comprehensive test suites for audit_fixer and variant_migrator

### Changed
- `is_canonical()` now verifies sub-fields (`completeness.score`, `workflow_context.workflow_id`), not just key existence
- `enrich_workflow()` accepts `case_violation_map` to bypass enrichment idempotency for violated cases
- `migrate_batch.py` integrates Phase A.5 after Phase A+B, updates audit_report.json
- Migration version bumped to `2.2.0` in all reports
- SKILL.md expanded with Phase A.5 docs, variant/composition_data transform tables, fix_status lifecycle

## [2.1.0] — 2026-02-25

- Phase A + B automatic migration with PubMed enrichment
- Batch CLI with priority filtering and dry-run mode

## [2.0.0] — 2026-02-22

- Initial release with case card migration, field transforms, paper enrichment
