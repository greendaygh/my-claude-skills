# Changelog — wf-migrate

## [2.3.0] — 2026-02-28

### Added
- **Verbose progress logging** for `migrate_batch.py` and `workflow_migrator.py`
  - Per-phase progress to stderr: `[A.1]` backup, `[A.2]` case cards, `[A.3]` composition_data, `[A.4]` variants, `[B.1]` papers, `[B.2]` cases, `[B.4]` reports
  - Batch-level progress: `[1/N] workflow_id starting...`, `[OK]`, `[ERR]`, `[COOLDOWN]`
  - `[A.5]` audit-fix summary with resolved/total counts
- `--quiet` / `-q` CLI flag to suppress progress messages
- `_blog()` and `_log()` helper functions for consistent stderr output
- **Progress Monitoring** section in SKILL.md with output examples and agent protocol

### Changed
- `migrate_batch()` accepts `verbose` parameter (default: `True`)
- `migrate_workflow()` and `enrich_workflow()` accept `verbose` parameter
- All print statements redirected to stderr (separating progress from JSON stdout)
- Migration version bumped to `2.3.0`

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
