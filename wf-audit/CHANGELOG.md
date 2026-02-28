# Changelog — wf-audit

## [2.1.0] — 2026-02-28

### Added
- **Verbose progress mode** (`--verbose` / `verbose=True`) for both single and batch audits
  - Single workflow: 14-step per-file-type progress to stderr
  - Batch: per-workflow score/priority progress
- **Chunked batch API** `audit_workflows_chunked()` yielding `(chunk_index, chunk_results, total)` for agent intermediate reporting
- `_log_step()` helper for consistent progress formatting
- `_violation_count()` helper for score entry extraction
- `--verbose` / `-v` CLI flag in `audit_batch.py`
- Agent intermediate reporting protocol in SKILL.md (chunk-of-5 progress tables)

### Changed
- `audit_single_workflow()` and `audit_all_workflows()` accept `verbose` parameter
- `audit_batch.py` — extracted `_filter_dirs()` helper, removed redundant docstrings/comments
- All 14 file type checks now emit progress via `_log_step()` when verbose
- Final aggregate score/priority summary printed when verbose

## [2.0.0] — 2026-02-28

### Added
- **Pydantic v2 canonical models** (`scripts/models/`) as single source of truth for all 13 file types
  - `base.py` — shared validators and base classes
  - `case_card.py`, `case_summary.py`, `composition_data.py`, `paper_list.py`
  - `variant.py`, `uo_mapping.py`, `qc_checkpoints.py`, `workflow_context.py`
  - `analysis.py` — ClusterResult, CommonPattern, ParameterRanges, StepAlignment
- 8 new scoring functions: `score_case_summary`, `score_cluster_result`, `score_common_pattern`, `score_parameter_ranges`, `score_step_alignment`, `score_uo_mapping`, `score_qc_checkpoints`, `score_workflow_context`
- Comprehensive model test suite (`tests/test_models.py`, 327 lines)
- `requirements.txt` with `pydantic>=2.0` dependency
- Helper functions `_rel_path()` and `_build_score_entry()` in audit_workflow

### Changed
- `scoring.py` — refactored from raw-dict validation to Pydantic `model_validate()` with `DetailedViolation` output
- `canonical_schemas.py` — now derives constants from Pydantic models instead of maintaining separate dicts
- `audit_workflow.py` — streamlined with reduced docstring verbosity, added all 13 file type scoring
- `SKILL.md` — updated to v2.0.0 with Pydantic model documentation and expanded file reference table
- All tests updated to match new Pydantic-based validation API

### Removed
- Redundant inline docstrings in audit_workflow.py helper functions
- Manual schema dict definitions replaced by Pydantic models

## [1.0.0] — 2026-02-20

- Initial release: 40-workflow batch audit with DOI validation, schema conformance, referential integrity
