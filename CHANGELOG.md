# Changelog

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
