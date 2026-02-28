# Changelog

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
