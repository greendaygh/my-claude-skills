# Changelog

## [2.2.0] - 2026-02-11

### Report Section Validation Gate

Added code-level validation to prevent incomplete reports from reaching Korean translation.

#### Added
- `generate_output.py`: Sections 9-13 auto-generation (Evidence/Confidence, Modularity/Service Integration, Limitations/Notes, Catalog Feedback, Execution Metrics)
- `validate.py`: `validate_report_sections()` — checks all 13 sections present, detects renamed/missing/out-of-order sections, EN/KO support
- `validate_workflow.py`: Inline report section check in `validate_output_structure()` (13 section numbers, no cross-skill import)
- `--test` self-test flags for both `generate_output.py` and `validate.py`
- Backward-compatible alternate names for sections 6 ("QC Checkpoints") and 7 ("UO Mapping Summary")

#### Changed
- `wf-output/SKILL.md`: Validation gate moved from step 5.4 to **5.2 (GATE)** — must pass before Korean translation (5.3)
- Non-standard reports (>50% renamed sections) now blocked as invalid
- `validate_workflow.py` test fixture updated with 13-section report

#### Root Cause Addressed
- WB030 composition_report_ko.md had missing sections because LLM wrote English report directly (bypassing generate_output.py), producing non-standard structure that propagated to Korean translation

## [2.1.0] - 2026-02-09

### Architecture: 4-Skill Split

Split single monolithic skill into 4 independent skills for context isolation and independent phase re-runs.

#### Added
- `wf-literature` skill (Phase 2: Literature Collection, 98-line SKILL.md)
- `wf-analysis` skill (Phase 3+4: Analysis & Composition, 112-line SKILL.md)
- `wf-output` skill (Phase 5: Output & Visualization, 93-line SKILL.md)
- Orchestration flow with verification gates between phase delegations
- Independent re-run capability via `/wf-literature`, `/wf-analysis`, `/wf-output`

#### Changed
- `workflow-composer` SKILL.md rewritten as orchestrator (293 -> 183 lines)
- `map_unit_operations.py` inlined `load_uo_catalog()` for self-contained execution
- `generate_output.py` inlined `__version__` constant
- ~60% context reduction per phase through sub-skill delegation

#### Removed from orchestrator
- 6 scripts moved to sub-skills: `collect_case.py`, `analyze_cases.py`, `map_unit_operations.py`, `generate_output.py`, `visualize_workflow.py`, `validate.py`
- 8 reference files moved to sub-skills
- `assets/case_template.json` moved to `wf-literature`

## [2.0.0] - 2026-02-09

### Full Redesign

Complete rewrite from v1.x: 11 phases -> 5 phases, 4 modes -> 2 modes, external skill delegation.

#### Added
- External skill delegation: openalex-database, pubmed-database, scholar-evaluation, peer-review, scientific-visualization, scientific-writing, oh-my-claudecode:writer
- `validate.py`: Deterministic validation checks
- `simple_logger.py`: Phase timing + error logging
- Per-phase reference loading architecture

#### Changed
- SKILL.md reduced from 587 -> 255 lines
- `generate_output.py` simplified (1336 -> 820 lines)
- `analyze_cases.py` simplified (597 -> 300 lines)
- `visualize_workflow.py` simplified (529 -> 440 lines, Mermaid only)
- `resolve_workflow.py` simplified (239 -> 195 lines)

#### Removed
- 6-expert panel simulation (replaced by `peer-review` skill)
- Checkpoint/multi-session architecture
- 12 files: expert-panel.md, paper-access-guide.md, search-queries.md, upgrade-mode-guide.md, validation-checklist.md, variant-identification.md, paper_cache.py, upgrade_manager.py, execution_logger.py, checkpoint_manager.py, panel_config.json, old CHANGELOG.md

## [1.9.1c] - 2026-02-07
- Enforce sequential WebFetch + correct PMC URL + prompt mandate

## [1.9.1b] - 2026-02-07
- Fix WebFetch subagent context overflow in Phase 3 Pass 2

## [1.9.1] - 2026-02-07
- Fix full_texts/ file save + global cache save not triggered in Phase 3

## [1.8.0] - 2026-02-06
- Phase 3 paper fetching resilience: two-pass strategy, incremental save, resume

## [1.7.1] - 2026-02-06
- Add status messages & phase timing for improved UX

## [1.7.0] - 2026-02-05
- Apply 18 improvements from 20-expert skill-evolve panel review

## [1.6.0] - 2026-02-04
- Context optimization: reduce panel, add file references, batch analysis

## [1.5.0] - 2026-02-03
- Add PQA paper quality assessment, --reeval mode, pool management

## [1.4.0] - 2026-02-02
- Centralize version management, deduplicate code, fix report sections

## [1.3.1] - 2026-02-01
- Add CHANGELOG, update README with upgrade full-regeneration docs
