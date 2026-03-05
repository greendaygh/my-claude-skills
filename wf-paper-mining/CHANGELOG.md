# Changelog — wf-paper-mining

## [1.0.1] — 2026-03-05

### Fixed
- **추출 파일 명명 표준화**: 저장 파일명을 `{paper_id}_extraction.json` → `{paper_id}_{workflow_id}.json`으로 통일 (SKILL.md Phase 4와 일치). `extract_resources save` 및 `aggregate_summary`가 새 형식 사용.
- **하위 호환**: `extract_resources summary`와 `aggregate_summary`는 `*_{workflow_id}.json`과 기존 `*_extraction.json` 이중 패턴을 모두 로드.
- **plan_run extraction_guide**: `file_paths.extraction_guide`를 `extraction_template.json`(스키마)에서 `uo_catalog.json`(UO 카탈로그)으로 변경. Panel A/B 프롬프트의 "UO 카탈로그" 참조가 올바른 파일을 가리키도록 수정.

### Documentation
- `references/extraction_guide.md`: 저장 경로 설명을 `{paper_id}_{workflow_id}.json`으로 갱신.

---

## [1.0.0] — 2026-03-04

### Added
- **New skill**: Biofoundry workflow paper mining — PubMed primary + OpenAlex fallback search, PMC full text extraction, 4-expert panel system (A/B/C/D), resource extraction with 7-component UO structure
- **Thin Controller architecture** — orchestrator LLM acts as minimal controller; all decisions made by Python scripts via RunManifest
- **RunManifest** — `plan_run.py` generates deterministic execution plans; no LLM memory dependency
- **Per-run paper lists** — `paper_list_{run_id}.json` prevents unbounded file growth across runs
- **4-panel expert review system**:
  - Panel A: UO candidate validation (stable cache)
  - Panel B: Paper relevance with lenient acceptance principle (accept/reject only)
  - Panel C: Extraction accuracy verification (accept/flag_reextract/reject)
  - Panel D: Workflow variant validation (accept/merge/reject)
- **Full/Quick panel modes** — automatic Quick mode after 5+ runs with high confidence; Full revert on critical flags
- **Pydantic v2 validation** — StrictModel for state/paper_list, FlexModel for LLM-generated extractions
- **Saturation detection** — 4-level overlap ratio tracking to skip exhausted workflows
- **Domain-grouped batch execution** — 64 workflows across 7 domains with session budgeting
- Scripts: `search_papers.py`, `fetch_fulltext.py`, `run_tracker.py`, `plan_run.py`, `resolve_target.py`, `extract_resources.py`, `aggregate_summary.py`, `validate_outputs.py`, `migrate_dirs.py`
- Models: `paper_list.py`, `state.py`, `extraction.py`, `summary.py`, `variant.py`, `manifest.py`, `panel_review.py`, `base.py`
- Assets: `extraction_config.json`, `extraction_template.json`, `panel_configs.json`, `workflow_catalog.json`, `uo_catalog.json`
- References: `extraction_guide.md`, `panel_protocol.md`

### Data compatibility
- `MiningPaper.authors`: `list[str]` for individual author access
- `MiningPaper.pmcid`/`doi`: nullable (`str | None`) for semantic correctness
- `MiningPaper.added_in_run`: run tracking metadata
- `ExtractionResult`: FlexModel tolerating extra fields from LLM-generated content
- `RunRegistry.schema_version`: forward compatibility field
- `FrequencyItem.type`: optional categorization for summary items
- Directory convention: `01_papers/`, `02_extractions/`, `03_summaries/` with ordered prefixes
- Summary file naming: `{WF_ID}_resource_summary.json`, `{WF_ID}_variants.json`
- Validated against 64 existing workflows (0 violations)
