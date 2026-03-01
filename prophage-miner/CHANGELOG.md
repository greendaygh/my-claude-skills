# prophage-miner Changelog

## v1.0.0 (2026-03-01)

### Added
- 6-Phase pipeline: PubMed Search → Full Text Download → Subagent Extraction → Expert Panel → Knowledge Graph → Report
- PubMed E-utilities integration with NCBI API key support
- PMC/Europe PMC full text download with section-based parsing
- Parallel subagent extraction (4 papers per agent, 4 concurrent)
- 3-expert panel review with consensus voting (Full Panel + Quick Panel modes)
- NetworkX-based knowledge graph with entity merging and confidence averaging
- GraphML and CSV export formats
- Pydantic v2 data validation (papers, extractions, graph referential integrity)
- Run tracking with `run_registry.json` for incremental execution
- Prophage catalog, host range matrix, gene inventory, and markdown report generation

### Fixed (post-initial implementation)
- **search_papers.py**: Fix PMCID parsing — ArticleIdList is under PubmedData, not Article
- **search_papers.py**: Add `tracker.add_papers()` call to register papers in run_registry
- **search_papers.py**: Add `--run-id` argument for orchestrator compatibility
- **build_graph.py**: Fix entity key generation to handle both `type`/`label` and `name`/`properties.name` formats
- **build_graph.py**: Rewrite `build_edges()` to resolve paper-local IDs (E001) through entity key lookup
- **generate_report.py**: Fix Host entity name lookup — use `species` with `name` fallback via `_get_host_name()` helper
- **generate_report.py**: Add entity type validation in host range matrix (Prophage/Host direction check)
