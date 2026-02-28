# Changelog — wf-audit

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
