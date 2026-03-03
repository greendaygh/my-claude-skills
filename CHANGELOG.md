# Changelog

## [1.10.1] — 2026-03-03

### wf-literature (3.1.1)

#### Changed
- **Per-paper expert panel review** — panel now reviews each paper individually with per-paper verdict (accept/flag_recheck/reject) instead of collection-level review
- Panel moved from Phase 2.6 to Phase 2.4 (before case extraction), only accepted papers proceed to case extraction (Phase 2.5)
- Pydantic Gate 2 renumbered to Phase 2.6
- `panel_protocol.md` rewritten for per-paper 3-round protocol with Korean output format and detailed JSON schema
- Gate condition: `accepted_count` >= 3 (replaces collection-level verdict check)

### workflow-composer (2.6.1)

#### Changed
- Phase 2 gate simplified: `literature_panel.json` must exist with `accepted_count` >= 3 (replaces separate verdict and file existence checks)

## [1.10.0] — 2026-03-03

### wf-literature (3.1.0)

#### Added
- **Script-based full text acquisition** — `fetch_fulltext.py` downloads PMC/Europe PMC XML, parses into structured sections (ABSTRACT, INTRODUCTION, METHODS, RESULTS, DISCUSSION) with `=== SECTION ===` headers
- **Paper validation** — `validate_papers.py` with Pydantic v2 schema check, abstract-title cosine similarity, fulltext-title matching, optional PMID cross-validation
- **Metadata repair** — `repair_paper_metadata.py` detects abstract-title mismatches and re-resolves via DOI
- **Abstract-only cleanup** — `cleanup_abstract_fulltexts.py` removes single-line P*.txt files from `full_texts/`
- **Batch repair pipeline** — `batch_repair.py` chains metadata→cleanup→fetch→validate across all workflows
- **3-expert panel review** — `literature_panel_config.json` and `references/panel_protocol.md` for 3-round consensus protocol (한국어 출력)
- **Pydantic Gate 2** — PaperList + CaseCard + CaseSummary validation before proceeding

#### Changed
- `pubmed-database` skill dependency removed; replaced by direct PMC API scripts
- SKILL.md bumped to v3.1.0 with full text acquisition and validation steps

### wf-analysis (2.2.0)

#### Added
- **Analysis Panel** (self-performed) — 3-expert, 3-round review for variant clustering, UO mapping, and QC checkpoints (한국어 출력)
- **Pydantic Gate 3** — validates 7 analysis models (StepAlignment, ClusterResult, CommonPattern, ParameterRanges, UoMapping, Variant, QcCheckpoints)

#### Changed
- Peer review (`scientific-skills:peer-review`) removed; replaced by self-performed Analysis Panel in Phase 4.5
- Review outputs changed from `peer_review.md` to 3 JSON files in `06_review/`

### wf-audit (2.4.0)

#### Added
- **Step 15: Content validation** — `content_validator.py` checks abstract-title and fulltext-title keyword similarity, missing/short full texts, duplicate DOIs
- **Abstract-title mismatch scoring** in `scoring.py` — cosine similarity check (threshold 0.05) with `content_mismatch` error type
- `suggest_corrections()` generates actionable fix suggestions from content validation results

#### Changed
- `_TOTAL_STEPS` increased from 14 to 15
- **Lenient canonical models** — all analysis/variant/QC models now accept legacy field names alongside canonical:
  - `ClusterResult`: `total_cases` or `case_count`
  - `QcCheckpoints`: `checkpoint_id` or `qc_id`
  - `UoMapping`: `uo_assignments` or `mappings`
  - `Variant` items: `name` or `description`
  - `PaperList`: `authors` accepts `str | list[str]`, `workflow_id`/`total_papers` optional
  - `CaseCard`: `Completeness.score` and `WorkflowContextRef.workflow_id` optional
  - `CommonPattern`: `workflow_skeleton` or `common_skeleton`
  - `notes` fields accept `str | list[str]`
- Model validators added for required-one-of-two-fields pattern (`model_validator(mode="after")`)

### wf-migrate (2.6.0)

#### Added
- **PMID cross-validation** — `validate_pmid_title_match()` compares PubMed title with expected title (cosine >= 0.3) before merge
- **PMID rejection** — DOI→PMID and title-search PMID results rejected if title mismatch detected
- **Role boundary documentation** — SKILL.md clarifies wf-migrate vs wf-literature responsibilities
- **Structured section parsing** — `_parse_pmc_sections()` and `_sections_to_structured_text()` for full PMC XML → structured text

#### Changed
- `workflow_migrator.py` — full text saved ONLY when `_full_text_pending` has actual PMC content (no abstract fallback)
- `paper_enricher.py` — `_extract_sections_from_pmc_xml()` removed; replaced by `_parse_pmc_sections()` with all-section extraction
- `case_migrator.py` — `enrich_case_card()` accepts `**kwargs` for forward compatibility
- `fetch_pmc_fulltext()` and `fetch_europepmc_fulltext()` return structured text with section headers

### wf-output (2.4.0)

#### Changed
- Phase reordering: Visualization (5.2) → Validation Gate (5.3) → Korean Translation (5.4)
- **Full Validation Gate 4** — 3-step mandatory gate: Step A (validate.py + validate_workflow.py), Step B (wf-audit full Pydantic audit, conformance >= 0.7), Step C (8-criteria visualization structure validation)
- Visualization validation criteria: file completeness, classDef color scheme, UO subgraph structure, output-to-input edges, QC diamond nodes, color legend, UO ID consistency, Mermaid syntax integrity
- Output contract includes `audit_report.json` and `visualization_validation.json` in `00_metadata/`

### workflow-composer (2.6.0)

#### Added
- **Gate 1** — WorkflowContext Pydantic validation after Phase 1
- **Enhanced Phase 2 gate** — 4 conditions: case count + Gate 2 Pydantic + Literature Panel verdict + review file
- **Enhanced Phase 3+4 gate** — 3 conditions: files + Gate 3 Pydantic + Analysis Panel review files
- **Enhanced Phase 5 gate** — 3 conditions: files + Gate 4 Full Audit (conformance >= 0.7) + audit report

#### Changed
- Fresh mode (`--fresh`) now moves entire workflow directory to `_versions/{timestamp}/` instead of just backing up
- `validate_phase2_gate()` expanded: full_texts/ directory check, average file size >= 500 chars, `validate_papers.py` integration
- `deep-executor-guide.md` — Step 2.0 added for script-based full text acquisition and validation before case extraction
- Review output structure changed from `peer_review.md` to 4 JSON files in `06_review/`

## [1.9.0] — 2026-03-02

### prophage-miner (1.0.0)

#### Added
- **New skill**: Automated prophage literature mining — PubMed search, PMC full text extraction, 3-expert panel consensus, knowledge graph construction
- Scripts: `search_papers.py`, `fetch_fulltext.py`, `build_graph.py`, `generate_report.py`
- Assets: `prophage_schema.json`, `panel_config.json`
- References: `extraction_prompts.md`, `prophage_biology.md`, `panel_protocol.md`

## [1.8.0] — 2026-03-01

### workflow-composer (2.5.0)

#### Added
- **Batch tracker** (`batch_tracker.py`) — state-file based resume capability for batch runs with `batch_state.json`
- **Enhanced gate checks** — `validate_phase2_gate()`, `validate_phase34_gate()`, `validate_phase5_gate()` in `validate_workflow.py`
- **Canonical variant format validation** — `validate_variant_canonical_format()` enforces `unit_operations`, `variant_name`, flat components
- **Canonical format table** in SKILL.md documenting required vs legacy field names

#### Changed
- Batch processing flow updated to use `BatchTracker` with error recovery and `--resume` support
- `deep-executor-guide.md` updated to canonical field names (`variant_name`, `unit_operations`)

### wf-analysis (2.1.0)

#### Added
- **Canonical variant format table** in SKILL.md — mandatory field mapping (canonical vs legacy)
- **Canonical structure examples** in hw-component-guide.md and sw-component-guide.md

### wf-audit (2.3.0)

#### Changed
- `check_uo_catalog_refs()` now reads `unit_operations` with `uo_sequence` fallback
- `check_paper_case_refs()` searches both `01_papers/` and `01_literature/` directories
- Tests updated: canonical format test cases added, paper paths changed to `01_papers/`

### wf-output (2.3.0)

#### Changed
- `visualize_workflow.py` uses `_extract_uo_list()` and `_get_component()` helpers for canonical/legacy compatibility

### wf-migrate (2.5.0)

#### Added
- **Separate full-text storage** — full texts saved to `full_texts/{paper_id}.txt` instead of inline in paper objects
- `_load_full_text()` in `case_enricher.py` loads text from separate files
- `has_full_text` boolean flag replaces inline `full_text` field in paper_list.json

#### Changed
- `case_enricher.py` checks `has_full_text` field for access tier determination
- `report_generator.py` reads `unit_operations` with `uo_sequence` fallback, uses `uo_name`
- `workflow_migrator.py` strips `_full_text_pending` and `full_text` from paper objects before saving
- `enrich_case_card()` accepts `wf_dir` parameter for full-text file loading

## [1.7.0] — 2026-03-01

### Housekeeping

- Remove all `.pyc` files from git tracking (already in `.gitignore`)

### wf-output (3.1.0)

#### Added
- **Canonical/legacy compatibility helpers** — `_extract_uo_list()`, `_get_component()`, `_get_variant_name()` for dual-format support
- Item-level evidence tag scoring in `_compute_confidence()`

#### Changed
- All functions now use 7-component direct access (`input`, `output`, `equipment`, `consumables`, `material_and_method`, `result`, `discussion`) instead of generic `components` dict iteration
- `generate_limitations()` reads component items via `_get_component()` helper
- Equipment/software inventory extraction updated for canonical schema
- Evidence tag counting uses explicit component keys

### wf-migrate (2.5.0)

#### Added
- **Circuit breaker** in `paper_enricher.py` — stops enrichment after 3 adaptive pause cycles to prevent infinite retry loops

## [1.6.0] — 2026-03-01

### wf-audit (2.2.0)

#### Added
- **Content quality checks** in `score_paper_list()` — detects `full_text` fields that should be stored separately and duplicate DOIs
- `_check_paper_content_quality()` helper with `content_quality` and `duplicate` error types
- Paper model enrichment fields: `abstract`, `enrichment_status`, `text_source`, `openalex_id`, `oa_status`, `cited_by_count`, `mesh_terms`
- Tests for enrichment field validation and content quality scoring (5 new test cases)

#### Changed
- `DetailedViolation.error_type` expanded with `content_quality` and `duplicate` types
- `score_paper_list()` refactored to combine schema validation with content quality checks
- Content violations now contribute to overall score penalty

### wf-migrate (2.4.0)

#### Added
- **Adaptive rate limiting** in `paper_enricher.py` — tracks consecutive API failures, auto-increases delay, pauses 60s after 3+ failures
- **NCBI connectivity check** after consecutive failures and in batch cooldown periods
- **Idempotent enrichment** — skips papers already enriched (PMID + abstract > 50 chars)
- Socket-level timeout (`socket.setdefaulttimeout`) to prevent TCP SYN-SENT hangs
- HTTP 403/503 handling as server block signals
- Network error backoff retry in `_http_get()`
- API key warning at module load if `NCBI_API_KEY` not set

#### Changed
- Batch cooldown increased: 10s between workflows, 60s every 5 workflows (was 5s/30s per 10)
- NCBI connectivity probe after cooldown with 120s additional wait on failure
- User-Agent bumped to `wf-migrate/2.3`

## [1.5.0] — 2026-02-28

### wf-output (2.2.0)

#### Added
- **Compact visualization mode** (default) — each UO rendered as horizontal subgraph with all component items shown
- **Detailed mode** (legacy) — activated via `--detailed` CLI flag
- **Data compatibility layer** for canonical and legacy variant formats
  - `_extract_uo_list()` — reads `unit_operations` first, falls back to `uo_sequence`
  - `_get_component()` — reads `uo[key]` first, falls back to `uo["components"][key]`
  - `_extract_component_lines()` — extracts all display lines from component items or text fields
- **Method component** (`material_and_method`) with yellow color scheme (`#FFEAA7`)
- `argparse` CLI with `--detailed` flag replacing positional-only usage
- `generate_compact_graph()` function with QC Pass/Fail branching between subgraphs
- Compact/detailed mode comparison table and full template examples in visualization-guide.md

#### Changed
- `generate_mermaid_graph()` now dispatches to compact (default) or detailed mode
- `generate_variant_comparison()` uses `_extract_uo_list()` for format compatibility
- `generate_workflow_context_graph()` uses `_get_component()` for format compatibility
- `generate_all_visualizations()` accepts `detailed` parameter
- visualization-guide.md restructured with compact mode as primary, detailed as legacy
- Removed Case-Variant Heatmap and Parameter Distribution Charts sections (handled by scientific-visualization skill)

### wf-migrate

#### Changed
- Minor variable rename in `paper_enricher.py` (`normalized` -> `normalized_doi`) for clarity

## [1.4.0] — 2026-02-28

- Add wf-migrate verbose progress logging and bump to v1.4.0

## [1.3.0] — 2026-02-28

- Add audit verbose/chunked mode and migrate Phase A.5 with audit-driven fixes

## [1.2.0] — 2026-02-28

- Upgrade wf-audit to v2.0.0 with Pydantic v2 canonical models

## [1.1.0] — 2026-02-28

- Add README.md with full skills overview and pipeline architecture

## [1.0.0] — 2026-02-20

- Initial release
