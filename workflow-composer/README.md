# Workflow Composer v2.2

**과학 문헌으로부터 바이오파운드리 워크플로우를 체계적으로 구성하는 Claude Code 스킬**

> Version 2.2.0 | Author: SBLab KRIBB

## 개요

Workflow Composer는 과학 논문에서 개별 실험 사례(Case)를 수집하고, 귀납적 비교 분석을 통해 공통 패턴을 도출한 뒤, 이를 표준화된 Unit Operation(UO)에 매핑하고 시각화된 워크플로우 구성을 생성하는 Claude Code 스킬입니다.

**핵심 철학: Case-First 접근법**

```
논문 → 개별 사례 수집 → 비교 분석 → 공통 패턴 도출 → UO 매핑 → 시각화
```

하향식(top-down) 설계 대신, 실제 논문 데이터로부터 귀납적으로 패턴을 도출합니다. 이를 통해 예상치 못한 변이(variant)와 실험 조건을 놓치지 않고 포착할 수 있습니다.

## 아키텍처: 4-스킬 분리

v2.1.0에서 도입된 **4-스킬 아키텍처**는 컨텍스트 격리와 독립적 단계 재실행을 지원합니다.

```
/workflow-composer (오케스트레이터)
    |
    +-- /wf-literature   (Phase 2: 문헌 수집)
    +-- /wf-analysis     (Phase 3+4: 분석 및 구성)
    +-- /wf-output       (Phase 5: 출력 및 시각화)
```

각 서브-스킬은 독립된 컨텍스트에서 실행되어 단계별 컨텍스트 사용량을 ~60% 절감합니다.

### 위임 모드

| 모드 | 설명 | 적합한 상황 |
|------|------|------------|
| **서브-스킬 체이닝** (기본) | Phase 2-5를 `/wf-literature` → `/wf-analysis` → `/wf-output` 순서로 위임 | 단일 워크플로우, 정밀한 품질 관리 |
| **Deep-Executor** (`--deep`) | Phase 2-5를 단일 `oh-my-claudecode:deep-executor` 에이전트에 위임 | 배치 처리, 여러 워크플로우 연속 실행 |

## 실행 방법

### 전체 파이프라인 (오케스트레이터)

```bash
/workflow-composer WB030                  # 워크플로우 ID로 실행
/workflow-composer "DNA Assembly"         # 워크플로우 이름으로 실행
/workflow-composer WB030 --fresh          # 기존 데이터 백업 후 새로 시작
/workflow-composer WB030 --deep           # Deep-Executor 모드 사용
/workflow-composer WB* --fresh --deep     # 배치: WB* 전체, Deep-Executor
```

**모드**: **New** (기존 데이터 없음) | **Update** (기존 데이터 발견 시, 새 논문 추가 + 재분석). `--fresh` = 기존 데이터 백업 후 New로 실행.

### 독립 단계 재실행

```bash
/wf-literature {wf_dir}    # Phase 2: 논문 검색 + 사례 추출
/wf-analysis {wf_dir}      # Phase 3+4: 분석 + UO 매핑
/wf-output {wf_dir}        # Phase 5: 보고서 + 시각화
```

### 독립 실행 시 필수 입력

| 스킬 | 필수 입력 파일 |
|------|--------------|
| `wf-literature` | `00_metadata/workflow_context.json` |
| `wf-analysis` | `02_cases/case_C*.json`, `case_summary.json` |
| `wf-output` | `04_workflow/variant_V*.json`, `uo_mapping.json` |

## 5-Phase 파이프라인

### Phase 1: Resolve (오케스트레이터)

오케스트레이터가 직접 수행하는 단계입니다.

- 사용자 입력 파싱: 워크플로우 ID/이름, `--fresh`/`--deep` 플래그 추출
- `workflow_catalog.json`에서 워크플로우 정보 로드 (~37개 표준 워크플로우)
- `domain_classification.json`으로 도메인 분류 (검색 키워드 결정)
- 모드 자동 감지 (New/Update): 기존 `composition_data.json` 존재 여부로 판별
- 출력 디렉터리 생성 및 `workflow_context.json` 저장
- **스크립트**: `resolve_workflow.py` (입력 파싱, 모드 감지, 디렉터리 생성), `simple_logger.py` (실행 로깅)

### Phase 2: 문헌 수집 (`wf-literature`)

과학 문헌을 검색하고, 논문 품질을 평가한 뒤, 구조화된 사례 카드를 추출합니다.

- **2.1 문헌 검색**: OpenAlex API로 10-15편의 관련 논문 검색. 워크플로우명 + 도메인 키워드로 쿼리 구성
- **2.2 논문 상세 정보**: PubMed E-utilities로 구조화된 초록, MeSH 용어 가져오기
- **2.3 품질 평가**: Protocol Detail(0.4) + UO Coverage(0.4) + Equipment Specificity(0.2) 가중 점수. 임계값 >= 0.4
- **2.4 사례 추출**: 6가지 추출 원칙에 따라 논문당 1개 사례 카드 생성. 장비는 `{name, model, manufacturer}` 구조화 배열
- **참조 파일**: `case-collection-guide.md` (6가지 추출 원칙), `case_template.json` (사례 카드 JSON 템플릿)

### Phase 3+4: 분석 및 구성 (`wf-analysis`)

수집된 사례 카드를 비교 분석하여 공통 패턴을 도출하고, UO에 매핑한 뒤, 7-컴포넌트 구조로 구성합니다.

- **3.1 사례 비교 분석**: 기능적 등가성 기준 스텝 정렬, 필수/조건부/분기점 식별, 기법/규모/생물체별 변이 클러스터링
- **3.2 UO 매핑**: 다중 신호 점수 산정 — 장비 0.35 + 기능 0.30 + I/O 0.20 + 컨텍스트 0.15. 0.7 이상 = 강한 매칭
- **3.3 동료 심사**: 변이 분류, UO 매핑 정확도, QC 체크포인트 배치에 대한 구조화된 리뷰 (최대 1회 수정)
- **4.1 7-컴포넌트 구성**: 각 UO 인스턴스에 HW(Input/Output/Equipment/Consumables/Material&Method/Result/Discussion) 또는 SW(Input/Output/Parameters/Environment/Method/Result/Discussion) 컴포넌트 채움
- **4.2 QC 체크포인트 설계**: Go/No-Go, 정량적 임계값, 분기 결정 유형
- **참조 파일**: `case-analysis-guide.md`, `unit-operation-mapping.md`, `hw-component-guide.md`, `sw-component-guide.md`, `qc-checkpoint-guide.md`

### Phase 5: 출력 및 시각화 (`wf-output`)

최종 보고서, 데이터 파일, 시각화, 한국어 번역을 생성합니다.

- **5.1 보고서 생성**: `composition_report.md` (필수 13개 섹션), `composition_workflow.md` (필수 5개 섹션), `composition_data.json` (Schema v4.0.0)
- **5.2 검증 게이트 (GATE)**: `validate_report_sections()`으로 13개 섹션 존재 여부 확인. **통과해야만 한국어 번역 진행**. 50% 이상 섹션명 변경된 보고서도 비표준으로 차단
- **5.3 한국어 번역**: `oh-my-claudecode:writer` 에이전트에 위임하여 한국어 보고서 생성. 기술 용어는 번역하지 않음
- **5.4 시각화**: Mermaid 형식 UO 워크플로우 그래프 생성. 서브그래프-per-UO 스타일, 6색 컬러 스킴, 컬러 범례 포함
- **참조 파일**: `visualization-guide.md` (Mermaid 그래프 사양), `output-templates.md` (보고서/JSON 템플릿)
- **검증 스크립트**: `validate.py` (보고서 섹션 검증), `validate_workflow.py` (크로스-스킬 검증)

### 단계간 검증 게이트

오케스트레이터는 각 서브-스킬 실행 사이에 검증 게이트를 수행합니다:

| 게이트 | 검증 조건 |
|--------|----------|
| Phase 2 완료 후 | `case_summary.json` 존재 및 >= 3 사례 |
| Phase 3+4 완료 후 | `uo_mapping.json` + 최소 1개 `variant_V*.json` 존재 |
| Phase 5 완료 후 | `composition_data.json` + `composition_report.md` 존재 |

## 의존 스킬 상세

Workflow Composer는 3종의 **내부 서브-스킬**과 7종의 **외부 스킬**에 의존합니다.

### 내부 서브-스킬 (로컬)

이 스킬들은 `~/.claude/skills/` 아래 별도 디렉터리로 존재하며, 오케스트레이터가 순차적으로 위임합니다.

| 스킬 | 트리거 | 버전 | 역할 |
|------|--------|------|------|
| **wf-literature** | `/wf-literature` | 2.0.0 | 문헌 검색, 논문 품질 평가, 구조화된 사례 카드 추출 |
| **wf-analysis** | `/wf-analysis` | 2.0.0 | 사례 비교 분석, 변이 클러스터링, UO 매핑, 7-컴포넌트 구성, 동료 심사 |
| **wf-output** | `/wf-output` | 2.1.0 | 보고서(13섹션) 생성, 검증 게이트, 한국어 번역, Mermaid 시각화 |

### 외부 스킬: 데이터베이스 (`scientific-skills`)

논문 검색과 상세 정보 취득에 사용되는 학술 데이터베이스 스킬입니다. [K-Dense](https://github.com/kdense/claude-scientific-skills) 마켓플레이스에서 제공됩니다.

| 스킬 | 사용 단계 | 설명 |
|------|----------|------|
| **`openalex-database`** | Phase 2.1 | OpenAlex REST API를 통한 학술 문헌 검색. 240M+ 학술 저작물, 저자, 기관, 주제 데이터베이스 대상으로 구조화된 쿼리 수행. API 키 불필요(오픈 액세스). 워크플로우 이름 + 도메인 키워드 조합으로 10-15편의 후보 논문을 검색하며, DOI/PMID로 중복 제거 |
| **`pubmed-database`** | Phase 2.2 | PubMed E-utilities API를 통한 생의학 문헌 접근. Boolean 연산자, MeSH 용어, 필드 태그를 활용한 고급 쿼리 구성. PMID 기반으로 구조화된 초록, MeSH 용어, 저널 정보를 가져와 `full_texts/` 디렉터리에 저장 |

### 외부 스킬: 평가 및 리뷰 (`scientific-skills`)

논문 품질 평가와 구성 결과 검증에 사용되는 학술 평가 스킬입니다.

| 스킬 | 사용 단계 | 설명 |
|------|----------|------|
| **`scholar-evaluation`** | Phase 2.3 | ScholarEval 프레임워크 기반의 정량적 학술 평가. Workflow Composer에서는 3가지 기준 — Protocol Detail(PD, 실험 방법 상세도), UO Coverage(UC, 워크플로우 스텝 포함 범위), Equipment Specificity(ES, 장비 모델명 명시도) — 으로 0-1 점수를 산출하여 합성 점수(0.4*PD + 0.4*UC + 0.2*ES >= 0.4)를 통과한 논문만 사례 추출 대상에 포함 |
| **`peer-review`** | Phase 3.3 | 체크리스트 기반의 구조화된 동료 심사. 방법론, 통계 유효성, 재현성, 보고 표준(CONSORT/STROBE) 준수 여부를 평가. Workflow Composer에서는 Protocol Specialist와 Quality Systems Expert 2명의 리뷰어가 UO 매핑 정확도, 스텝 완전성, QC 체크포인트 배치를 각 10개 항목으로 검토하며, 8점 이상이 통과 기준 |

### 외부 스킬: 작문 및 시각화

보고서 생성과 시각화에 사용되는 스킬입니다.

| 스킬 | 사용 단계 | 설명 |
|------|----------|------|
| **`scientific-writing`** | Phase 5.1 | IMRAD 구조 기반의 과학적 글쓰기 스킬. APA/AMA/Vancouver 인용 형식, 보고 가이드라인(CONSORT/STROBE/PRISMA) 지원. Workflow Composer에서는 `composition_report.md` 13개 필수 섹션의 영문 보고서 생성을 보조 |
| **`scientific-visualization`** | Phase 5.4 | 출판 품질의 과학적 시각화 메타-스킬. matplotlib/seaborn/plotly를 활용한 다중 패널 레이아웃, 색맹 안전 팔레트, 저널별 포맷(Nature/Science/Cell) 지원. Workflow Composer에서는 Mermaid 기반 UO 워크플로우 그래프와 변이 비교 다이어그램 생성에 활용 |

### 외부 스킬: 에이전트 (`oh-my-claudecode`)

OMC(oh-my-claudecode) 프레임워크의 특수 에이전트입니다.

| 스킬 | 사용 단계 | 설명 |
|------|----------|------|
| **`oh-my-claudecode:writer`** | Phase 5.3 | 경량(Haiku 모델) 기술 문서 작성 에이전트. Workflow Composer에서는 영문 보고서의 한국어 번역을 전담. 메인 에이전트의 컨텍스트 오버플로우를 방지하기 위해 별도 에이전트에 위임하며, 기술 용어(워크플로우 ID, UO ID, 장비명 등)는 번역하지 않고 원문 유지 |
| **`oh-my-claudecode:deep-executor`** | `--deep` 모드 | 복잡한 목표 지향적 작업을 자율적으로 수행하는 Opus 모델 에이전트. `--deep` 플래그 사용 시 Phase 2-5 전체를 단일 에이전트에 위임. `references/deep-executor-guide.md`를 참조하여 서브-스킬 체이닝과 동등한 품질을 보장. 배치 처리 시 효율적 |

### 의존 스킬 데이터 흐름도

```
                        Phase 2                    Phase 3+4              Phase 5
                    ┌───────────────┐          ┌──────────────┐      ┌──────────────┐
                    │ wf-literature │          │ wf-analysis  │      │  wf-output   │
                    └───────┬───────┘          └──────┬───────┘      └──────┬───────┘
                            │                         │                     │
              ┌─────────────┼──────────┐              │          ┌──────────┼──────────┐
              │             │          │              │          │          │          │
              v             v          v              v          v          v          v
         openalex      pubmed    scholar-       peer-      scientific  scientific   writer
         database     database   evaluation    review     writing    visualization  (OMC)
```

## 핵심 개념

### Unit Operation (UO)

DBTL 사이클을 커버하는 ~80개의 표준화된 단위 조작입니다.

- **Hardware UO (UHW)**: 물리적 조작 (예: UHW100 Thermocycling, UHW250 Nucleic Acid Purification, UHW010 Liquid Handling)
- **Software UO (USW)**: 데이터 처리 (예: USW020 Primer Design, USW110 Sequence Alignment)

각 UO 인스턴스는 7개 컴포넌트를 포함하며, 모든 값에 사례 추적(`case_refs`)과 근거 태그(`evidence_tag`)가 부여됩니다.

### 워크플로우 카탈로그

4개 카테고리에 걸친 ~37개 표준 워크플로우:

| 카테고리 | 접두사 | 예시 |
|---------|--------|------|
| **Design (설계)** | WD | DoE, 벡터 설계, 역합성 |
| **Build (구축)** | WB | DNA 어셈블리, 형질전환, PCR |
| **Test (테스트)** | WT | 시퀀싱, 발효, 대사체 분석 |
| **Learn (학습)** | WL | 변이 분석, 전사체학, ML |

### 7-컴포넌트 구조

각 UO 인스턴스는 유형별 7개 컴포넌트로 구성됩니다:

| HW UO 컴포넌트 | SW UO 컴포넌트 | 설명 |
|---------------|---------------|------|
| Input | Input | 입력 물질/데이터 |
| Output | Output | 출력 물질/데이터 |
| Equipment | Parameters | 장비(이름/모델/제조사) 또는 매개변수 |
| Consumables | Environment | 소모품 또는 소프트웨어 환경 |
| Material & Method | Method | 실험 방법 절차 |
| Result | Result | 정량적 측정 결과 + QC 체크포인트 |
| Discussion | Discussion | 해석, 트러블슈팅, 특이사항 |

### 근거 태깅 (Evidence Tagging)

모든 데이터 값에 출처 근거를 부여하는 6단계 우선순위 체계:

| 우선순위 | 태그 | 설명 |
|---------|------|------|
| 1 | `literature-direct` | 논문 Methods/Results에서 직접 추출 |
| 2 | `literature-supplementary` | 보충 자료에서 추출 |
| 3 | `literature-consensus` | 복수 사례가 일치 |
| 4 | `manufacturer-protocol` | 장비/키트 제조사 문서 |
| 5 | `expert-inference` | 추론 (근거 설명 필요) |
| 6 | `catalog-default` | UO 카탈로그 기본값 (최후 수단) |

## 출력 구조

```
workflow-compositions/{WF_ID}_{WF_NAME}/
├── _versions/                        # 버전 백업 (Update/Fresh 모드)
├── 00_metadata/
│   ├── workflow_context.json         # 워크플로우 컨텍스트
│   ├── validation_report.json        # 검증 결과
│   └── execution_log.json            # 실행 로그 (단계별 소요 시간)
├── 01_papers/
│   ├── paper_list.json               # 검색된 논문 목록
│   ├── paper_ranking.json            # 품질 평가 점수
│   └── full_texts/                   # 논문 전문/초록
├── 02_cases/
│   ├── case_C001.json ... case_C0XX.json  # 개별 사례 카드
│   └── case_summary.json             # 사례 요약
├── 03_analysis/
│   ├── step_alignment.json           # 스텝 정렬 결과
│   ├── cluster_result.json           # 변이 클러스터링
│   ├── common_pattern.json           # 공통 패턴 + 모듈성
│   └── parameter_ranges.json         # 파라미터 범위
├── 04_workflow/
│   ├── uo_mapping.json               # UO 매핑 결과
│   ├── variant_V1_*.json ... variant_VN_*.json  # 변이별 7-컴포넌트
│   └── qc_checkpoints.json           # QC 체크포인트
├── 05_visualization/
│   ├── workflow_graph_V*.mmd         # 변이별 UO 그래프 (Mermaid)
│   ├── variant_comparison.mmd        # 변이 비교 다이어그램
│   └── workflow_context.mmd          # 상/하류 워크플로우 맥락
├── 06_review/
│   └── peer_review.md                # 동료 심사 결과
├── composition_report.md             # 영문 보고서 (13 섹션)
├── composition_report_ko.md          # 한국어 보고서
├── composition_data.json             # 기계 가독 데이터 (Schema v4.0.0)
├── composition_workflow.md           # 영문 참조 카드 (5 섹션)
└── composition_workflow_ko.md        # 한국어 참조 카드
```

## 파일 구조

### 오케스트레이터 (`workflow-composer/`)

```
workflow-composer/
├── SKILL.md                           # 오케스트레이터 정의 (~260 lines)
├── README.md                          # 이 문서
├── CHANGELOG.md                       # 버전 이력
├── assets/
│   ├── workflow_catalog.json          # ~37 표준 워크플로우 정의
│   ├── uo_catalog.json                # ~80 Unit Operation 정의
│   ├── domain_classification.json     # 워크플로우-도메인 매핑 + 검색 키워드
│   └── v2_config.json                 # 단계별 설정 (임계값, 가중치, 에이전트 구성)
├── scripts/
│   ├── __init__.py                    # 패키지 마커 (v2.2.0)
│   ├── resolve_workflow.py            # 입력 파싱, 모드 감지, 디렉터리 생성
│   ├── simple_logger.py               # 단계별 소요 시간 + 에러 로깅
│   ├── populate_components.py         # 규칙 기반 7-컴포넌트 집계 (majority_vote, range_with_median)
│   └── validate_workflow.py           # 크로스-스킬 검증 + 인라인 13-섹션 체크
└── references/
    └── deep-executor-guide.md         # Deep-Executor 모드 통합 가이드
```

### 서브-스킬

```
wf-literature/                          # Phase 2: 문헌 수집
├── SKILL.md (101 lines)               # 단계 정의 + 외부 스킬 의존성
├── scripts/
│   └── collect_case.py                # 사례 카드 생성/검증/요약
├── references/
│   └── case-collection-guide.md       # 6가지 추출 원칙
└── assets/
    └── case_template.json             # 사례 카드 JSON 템플릿

wf-analysis/                            # Phase 3+4: 분석 및 구성
├── SKILL.md (113 lines)
├── scripts/
│   ├── analyze_cases.py               # 스텝 정렬, 클러스터링, 파라미터 범위
│   └── map_unit_operations.py         # 다중 신호 UO 매핑 (자체 포함)
├── references/
│   ├── case-analysis-guide.md         # 사례 분석 가이드
│   ├── unit-operation-mapping.md      # UO 매핑 규칙
│   ├── hw-component-guide.md          # HW 7-컴포넌트 가이드
│   ├── sw-component-guide.md          # SW 7-컴포넌트 가이드
│   └── qc-checkpoint-guide.md         # QC 체크포인트 설계 가이드
└── assets/
    └── uo_catalog.json                # UO 카탈로그 복사본

wf-output/                              # Phase 5: 출력 및 시각화
├── SKILL.md (134 lines)
├── scripts/
│   ├── generate_output.py             # 보고서 생성 — 13 섹션 (자체 포함)
│   ├── visualize_workflow.py          # Mermaid 워크플로우 그래프
│   └── validate.py                    # 검증 + validate_report_sections()
└── references/
    ├── visualization-guide.md         # Mermaid 그래프 사양
    └── output-templates.md            # 보고서/JSON 템플릿
```

## Schema v4.0.0 — composition_data.json

모든 `composition_data.json`은 Schema v4.0.0을 준수해야 합니다.

### 필수 최상위 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `schema_version` | string | `"4."` 으로 시작 (예: `"4.0.0"`) |
| `workflow_id` | string | 예: `"WB030"` |
| `workflow_name` | string | 예: `"DNA Assembly"` |
| `category` | string | `Build` / `Test` / `Design` / `Learn` |
| `domain` | string | 도메인 분류 |
| `version` | number | 숫자형 버전 |
| `composition_date` | string | `YYYY-MM-DD` 형식 |
| `statistics` | object | `papers_analyzed`, `cases_collected`, `variants_identified`, `total_uos`, `qc_checkpoints`, `confidence_score` |

## 버전 이력

| 버전 | 날짜 | 주요 변경 |
|------|------|----------|
| **2.2.0** | 2026-02-11 | 보고서 섹션 검증 게이트, >50% 섹션명 변경 감지, 섹션 9-13 자동 생성, Deep-Executor 모드 |
| **2.1.0** | 2026-02-09 | 4-스킬 분리 아키텍처, 독립적 단계 재실행, ~60% 컨텍스트 절감 |
| **2.0.0** | 2026-02-09 | 전면 재설계 — 11단계→5단계, 4모드→2모드, 외부 스킬 위임, 6-전문가 패널 제거 |
| **1.x** | ~2026-02 | 초기 버전: 모놀리식 구조, 체크포인트/다중 세션, 전문가 패널 시뮬레이션 |

## 라이선스

SBLab KRIBB 내부용으로 개발되었습니다.
