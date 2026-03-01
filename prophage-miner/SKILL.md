---
name: prophage-miner
description: >
  This skill should be used when the user asks to "prophage 논문 분석",
  "prophage literature mining", "prophage gene extraction",
  "박테리오파지 프로파지 연구", "prophage knowledge graph",
  "프로파지 유전자 추출", "prophage 10회 반복", "prophage 연속 실행",
  or needs automated prophage-related literature collection and analysis.
user_invocable: true
---

# Prophage Miner

PubMed에서 prophage 관련 논문을 자동 검색/선정하고, PMC full text에서 유전자/단백질/숙주 감염 정보를 추출하여 knowledge graph를 구축한다. Pydantic v2 검증 + 3인 전문가 패널 합의로 데이터 품질을 보장한다. 반복 실행 시 기존 데이터에 증분 업데이트된다.

**출력 디렉토리**: `~/dev/phage/`
**스킬 위치**: `~/.claude/skills/prophage-miner/`

## Prerequisites

의존성 설치 확인 (최초 1회):
```bash
pip install -r ~/.claude/skills/prophage-miner/requirements.txt
```

## Orchestration

### 단일 실행

사용자가 "prophage 분석 실행" 등을 요청하면 Phase 1-6을 순차 수행한다.

### N회 반복 실행

사용자가 "10회 반복" 등을 지시하면 for loop으로 Phase 1-6을 반복한다:

```
for i in 1..N:
  1. Phase 1: search_papers.py (기존 PMID 제외, run 자동 생성 + 논문 등록) + Pydantic 검증
  2. Phase 2: fetch_fulltext.py (미다운로드만)
  3. Phase 3: 서브에이전트 위임 (미추출만, 4 병렬) + Pydantic 검증
  4. Phase 4: Expert Panel (i <= 4이면 Full Panel, i >= 5이면 Quick Panel)
  5. Phase 5: build_graph.py (승인된 추출만 재구축) + Pydantic 검증
  6. Phase 6: generate_report.py
  7. run_tracker.complete_run(run_id)  # run_id는 search_papers가 반환
  8. Report: "Run {i}/{N} | 누적 {total}편 | 그래프 {nodes}노드 {edges}엣지"

최종: run_tracker.summary() 출력
```

### 출력 디렉토리 초기화

최초 실행 시 다음 디렉토리 구조를 생성한다:

```bash
mkdir -p ~/dev/phage/{00_config,01_papers/full_texts,02_extractions/per_paper,03_graph/exports,04_analysis,05_reports}
cp ~/.claude/skills/prophage-miner/assets/prophage_schema.json ~/dev/phage/00_config/schema.json
```

---

## Phase 1: PubMed Search (자동, 증분)

사전 정의된 키워드로 PubMed을 검색하고 기존 수집 PMID를 제외한 후 ~20편을 랜덤 선정한다.

**실행**:
```bash
cd ~/.claude/skills/prophage-miner
python -m scripts.search_papers \
  --output ~/dev/phage \
  --exclude-file ~/dev/phage/00_config/run_registry.json \
  --select-n 20
# search_papers가 자동으로 run을 생성하고 논문을 run_registry에 등록한다.
# 오케스트레이터가 이미 run을 생성한 경우: --run-id run_002
```

**Pydantic 검증**:
```bash
python -m scripts.validate_data --papers ~/dev/phage/01_papers/paper_list.json
```

검증 실패 시 에러 목록을 출력하고 자동 수정을 시도한다. 심각한 위반 시 Phase 1을 재실행한다.

---

## Phase 2: Full Text Download (자동, 증분)

`has_full_text: false`인 논문만 PMC/Europe PMC에서 full text를 다운로드한다.

**실행**:
```bash
python -m scripts.fetch_fulltext \
  --input ~/dev/phage/01_papers/paper_list.json \
  --output ~/dev/phage \
  --pending-only
```

다운로드 실패 시 abstract만으로 진행 (Phase 3에서 confidence 페널티).

---

## Phase 3: Prophage Extraction (서브에이전트 위임)

**핵심**: 이 Phase는 메인 에이전트가 직접 추출하지 않고, **서브에이전트에 위임**하여 컨텍스트 윈도우를 보호한다.

### 절차

1. 미추출 논문 목록을 조회한다:
```python
import sys; sys.path.insert(0, str(Path.home() / ".claude/skills/prophage-miner"))
from scripts.run_tracker import RunTracker
tracker = RunTracker(Path.home() / "dev/phage")
pending = tracker.get_pending_extractions()
```

2. pending 논문을 4편씩 묶어 **병렬 서브에이전트에 위임**한다 (Task 도구, subagent_type="generalPurpose"):

각 서브에이전트에 전달할 프롬프트:

```
You are a prophage biology extraction specialist.

1. Read ~/.claude/skills/prophage-miner/references/extraction_prompts.md for extraction guidelines.
2. Read ~/.claude/skills/prophage-miner/references/prophage_biology.md for domain context.
3. Read ~/dev/phage/00_config/schema.json for the entity/relationship schema.
4. Read ~/dev/phage/01_papers/full_texts/{paper_id}.txt for the full text.
5. Extract ALL prophage-related entities and relationships following the schema.
6. Apply section-based confidence weights:
   - Results: 0.9, Methods: 0.85, Abstract: 0.85, Introduction: 0.7, Discussion: 0.6
   - Abstract-only papers: apply -0.2 penalty
7. Save the extraction result:
   python -m scripts.extract_prophage save \
     --paper-id {paper_id} \
     --output ~/dev/phage/02_extractions/per_paper/
   Provide the extraction JSON via stdin.
8. Return a brief summary ONLY: entity count, relationship count, key prophage names found.
```

3. 서브에이전트 완료 후, 메인 에이전트가 상태를 업데이트한다:
```python
tracker.mark_extracted(paper_id)
# 또는 실패 시:
tracker.mark_extract_failed(paper_id, "reason")
```

4. **Pydantic 검증** (각 추출 결과):
```bash
python -m scripts.validate_data --extraction ~/dev/phage/02_extractions/per_paper/{paper_id}_extraction.json
```

---

## Phase 4: Expert Panel Review (3인 자유토론 + 합의)

Read `~/.claude/skills/prophage-miner/references/panel_protocol.md` for the full protocol.
Read `~/.claude/skills/prophage-miner/assets/panel_config.json` for panel configuration.

### Full Panel (기본, 처음 4회)

**Round 1 - 독립 검토** (3인 병렬 서브에이전트):

각 전문가에게 전달할 입력:
- 이번 run의 추출 요약 (엔티티/관계 타입별 개수 + 대표 예시)
- 신뢰도 분포 (min, max, mean)
- unschemaed 발견 목록

각 전문가(서브에이전트) 프롬프트:
```
You are {expert_name}, {persona_description}.
Review the following extraction summary and evaluate:
- Entity accuracy (accept/flag with reason)
- Relationship plausibility (accept/flag with reason)
- Missing entities or relationships
- Schema improvement suggestions

Input: {extraction_summary}

Output your assessment as JSON with: assessments (per paper), schema_suggestions, overall_quality.
```

**Round 2 - 자유 토론** (순차 서브에이전트):
- Round 1의 3인 의견을 모두 공개
- 각 전문가가 다른 의견을 참고하여 재평가
- 최대 2회 왕복

**Round 3 - 합의 투표**:
- 각 전문가 최종 판정: accept / flag_recheck / flag_reextract / reject
- 2/3 이상 동의 시 합의로 확정

### Quick Panel (5회 이상 연속)

조건: 연속 5회 이상 + 평균 panel_confidence >= 0.8
- Round 1만 수행
- 심각한 flag가 없으면 자동 승인
- 심각한 flag 발견 시 즉시 Full Panel로 복귀

### 판정 처리

- `accept`: 그래프에 포함
- `flag_reextract`: extraction_status를 "pending"으로 복원 → Phase 3에서 재추출
- `flag_recheck`: 메인 에이전트가 extraction을 직접 수정 후 재검증
- `reject`: extraction 삭제, extraction_status를 "rejected", 그래프에서 제외

---

## Phase 5: Knowledge Graph Construction (자동, idempotent)

승인된 추출 결과만 통합하여 그래프를 재구축한다.

**실행**:
```bash
python -m scripts.build_graph \
  --input ~/dev/phage/02_extractions/per_paper \
  --output ~/dev/phage/03_graph \
  --registry ~/dev/phage/00_config/run_registry.json
```

**Pydantic 검증**:
```bash
python -m scripts.validate_data --graph ~/dev/phage/03_graph/
```

참조 무결성 검증: 모든 edge의 from_id/to_id가 존재하는 node를 가리키는지 확인.

---

## Phase 6: Analysis & Report (자동, idempotent)

그래프 데이터를 기반으로 분석 카탈로그와 리포트를 생성한다.

**실행**:
```bash
python -m scripts.generate_report \
  --input ~/dev/phage/03_graph \
  --output ~/dev/phage
```

**출력 파일**:
- `04_analysis/prophage_catalog.json`: 발견된 prophage 카탈로그
- `04_analysis/host_range_matrix.json`: 호스트-파지 감염 범위
- `04_analysis/gene_inventory.json`: 유전자/단백질 인벤토리
- `05_reports/research_report.md`: 영문 연구 리포트

---

## Run Completion

매 run 종료 시:
```python
tracker.complete_run(run_id)
s = tracker.summary()
```

누적 통계 출력:
```
Run {i}/{N} completed
Total: {total_papers} papers | Extracted: {extracted} | Failed: {failed}
Graph: {nodes} nodes, {edges} edges
Panel confidence: {confidence}
```

---

## Schema Reference

스키마 파일: `~/dev/phage/00_config/schema.json`

### 엔티티 타입 (8종)
Prophage, Gene, Protein, Host, IntegrationSite, Receptor, InductionCondition, Paper

### 관계 타입 (10종)
ENCODES, TRANSLATES_TO, INTEGRATES_INTO, INFECTS, BINDS, REPRESSES, INDUCES, HOMOLOGOUS_TO, LYSIS_COMPONENT, EXTRACTED_FROM

상세 정의는 `~/.claude/skills/prophage-miner/assets/prophage_schema.json` 참조.

---

## Stability Notes

- **컨텍스트 보호**: 메인 에이전트는 full text를 직접 로드하지 않음. 스크립트 실행 + 서브에이전트 위임만 수행
- **파일 기반 상태**: 모든 상태가 run_registry.json에 영속적으로 저장
- **실패 격리**: 서브에이전트 실패 시 해당 논문만 failed로 표시, 나머지 계속 진행
- **재시도**: 다음 run에서 failed 논문을 자동 재시도 (pending으로 복원)
- **Idempotent Phase 5/6**: 그래프/리포트는 항상 전체 재구축이므로 언제든 안전
