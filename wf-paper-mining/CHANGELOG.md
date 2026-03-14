# Changelog — wf-paper-mining

## [2.3.0] — 2026-03-14

### Changed
- **Phase 4 추출 프롬프트 강화** — uo_connections, workflows, doi 규칙 명시
  - `from_uo`/`to_uo`: catalog_id 사용 필수 (is_new UO는 name 허용)
  - `workflows`: 논문의 실제 워크플로 기록, 대상 워크플로 포함 보장
  - `doi`: 필수 필드로 명시
- **Phase 3 Panel B 도메인 특이성 검사** — 관대한 수용 유지하되 대상 워크플로와 무관한 논문 reject
- **Phase 5a Panel C 점수 형식** — 0.0~1.0 float 필수 (소수점 포함, 정수 불가)
- **extraction_template.json** — `from_uo`/`to_uo` 설명을 catalog_id 기준으로 변경, doi/uo_connections 가이드라인 추가
- **aggregate_summary.py** — variant 감지를 순서 독립 비교(`sorted tuple`)로 변경, 첫 등장 step 순서 보존

### Added
- **run_tracker.py `sync_after_cleanup()`** — Phase 4 JSON cleanup 후 누락 파일을 "lost" 상태로 동기화
- **run_tracker.py `sync-after-cleanup` CLI** — 새 서브커맨드
- **run_tracker.py `_update_index()` 개선** — `extracted_count`를 실제 파일 수 기준으로 계산
- **validate_outputs.py `_cross_validate_uo_connections()`** — uo_connections의 from_uo/to_uo가 유효한 catalog_id 또는 is_new UO name인지 교차 검증
- **SKILL.md Phase 4 post-cleanup** — JSON cleanup 후 `sync-after-cleanup` 자동 호출 추가

### Fixed
- Phase 4 post-cleanup에서 손상 파일 삭제 시 wf_state/registry_index 미갱신 문제 해결 (재실행 시 영구 데이터 손실 위험 제거)

---

## [2.2.0] — 2026-03-12

### Fixed
- **Verdict 대소문자 정규화** — `apply_panel_b_verdicts.py`와 `run_tracker.py`에서 verdict 값을 `.lower()`로 통일. 대소문자 불일치로 인한 verdict 매칭 실패 방지
- **Top-level list 포맷 호환** — `apply_panel_b_verdicts.py`의 `apply_verdicts()`와 `run_tracker.py`의 `apply_verdicts_from_file()`에서 서브에이전트가 wrapper dict 없이 list만 반환하는 경우 `{"papers": data}`로 자동 래핑

### Added
- **Panel C Fallback 전략** — SKILL.md에 API 정책 위반(Usage Policy violation) 시 재시도 프로토콜 추가: (1) 프롬프트 단순화 후 1회 재시도, (2) 오케스트레이터 직접 수행

---

## [2.0.0] — 2026-03-07

### Changed
- **Per-workflow state files** — 단일 `run_registry.json` → 워크플로별 `{WF_ID}/wf_state.json` + 경량 `registry_index.json`으로 분리. 워크플로 수 증가에도 I/O 부담 없음
- **RunTracker v2 API** — `RunTracker(registry_path)` → `RunTracker(root_dir, wf_id)`. 모든 메서드에서 `wf_id` 파라미터 제거 (인스턴스에 바인딩)
- **Atomic file writes** — `tempfile + os.replace` 패턴으로 상태 파일 손상 방지
- **Batched verdict save** — `apply_verdicts_from_file()`에서 verdict당 개별 저장 대신 단일 `_save()` 호출
- **CLI args** — 모든 스크립트에서 `--registry` → `--root-dir` (v2). `--registry`는 legacy 폴백으로 유지
- **aggregate_summary** — `RunRegistry` 대신 `WorkflowState` 직접 로드
- **validate_outputs** — `run_registry.json` 대신 `wf_state.json` + `registry_index.json` 검증
- **SKILL.md** — 모든 CLI 예시에서 `$REGISTRY` 제거, `--root-dir $ROOT_DIR` 사용. 디렉토리 구조에 `wf_state.json` 반영

### Added
- `WorkflowState` — 워크플로별 상태 Pydantic 모델 (DOI 커버리지 + run_id 참조 검증)
- `WorkflowIndexEntry` / `RegistryIndex` — 경량 글로벌 인덱스 모델 (extracted_count ≤ paper_count 검증)
- `migrate_registry.py` — legacy `run_registry.json` → per-workflow 파일 변환 스크립트 (백업 자동 생성)
- Legacy fallback — `RunTracker(root_dir, wf_id, legacy_registry=Path)`로 기존 데이터 자동 감지/로드

---

## [1.0.2] — 2026-03-06

### Changed
- **Per-workflow keyword cache** — `wf_search_keywords.json`에서 워크플로별 LLM 생성 검색 키워드 로드. `extraction_config.json`의 공유 `domain_groups` 제거
- **Workflow-prefixed paper IDs** — `P0001` → `{WF_ID}_P{NNN}` 형식 (예: `WB030_P001`). 워크플로 간 ID 충돌 방지
- **Sequential-only execution** — 멀티 워크플로 실행 시 순차 전용 규칙 SKILL.md에 명시 (병렬 실행 절대 금지)
- **Extraction file naming** — `{paper_id}_{WF_ID}.json` → `{paper_id}.json`으로 단순화 (paper_id에 이미 WF_ID 포함)
- **Fuzzy title matching** — Panel B title 비교를 prefix 방식에서 `SequenceMatcher` (threshold 0.85)로 변경. LLM 자동 오타 교정 대응
- **Robust Panel B verdict parsing** — `results`, `round_2.final_verdict`, `summary.accepted_ids/rejected_ids` 등 추가 포맷 지원
- **Soft warning for title mismatch** — title mismatch는 경고만, paper_id 불일치만 hard failure로 처리
- **Domain → Category** — `plan_run.py`가 `extraction_config.json`의 domain_groups 대신 `workflow_catalog.json`의 category (Design/Build/Test/Learn) 사용
- **validate_outputs paper_id regex** — `^P\d{4,}$` → `^[A-Z]{2}\d{3}_P\d{3,}$`로 새 형식 반영

### Added
- `wf_search_keywords.json` — 워크플로별 검색 키워드/MeSH 캐시 파일

---

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
