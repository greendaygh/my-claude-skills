# wf-paper-mining: Biofoundry 워크플로 논문 마이닝

Scientific literature에서 biofoundry 워크플로 관련 정보(UO, 장비, 소모품, 시약, 샘플)를 체계적으로 수집·추출하는 스킬.

## Trigger Phrases

"워크플로 논문 마이닝", "paper mining", "논문 수집", "wf-paper-mining 실행"

## Architecture

- **Thin Controller** 패턴: 오케스트레이터 LLM은 스크립트를 실행하고 서브에이전트를 스폰하는 최소 컨트롤러 역할만 수행
- **RunManifest**: `plan_run.py`가 생성하는 결정론적 실행 계획
- **Per-run paper list**: `paper_list_{run_id}.json`으로 run별 분리 저장
- **PubMed 주 검색 + OpenAlex 보조**: MeSH 기반 정밀 검색

## Prerequisites

- Python 3.10+ with `pydantic>=2.0`, `requests`, `lxml`
- 인터넷 접속 (PubMed, OpenAlex, PMC API)
- 출력 디렉토리 (e.g., `~/dev/wf-mining/`)

## Directory Structure

```
~/dev/wf-mining/                    # ROOT_DIR
├── run_registry.json               # 전체 상태 관리
├── WB030/                          # 워크플로별 출력
│   ├── 01_papers/
│   │   ├── paper_list_1.json       # per-run paper list
│   │   ├── paper_list_2.json
│   │   └── full_texts/
│   │       ├── P0001.txt
│   │       └── P0002.txt
│   ├── 02_extractions/
│   │   ├── P0001_WB030.json
│   │   └── P0002_WB030.json
│   ├── 03_summaries/
│   │   ├── WB030_resource_summary.json
│   │   └── WB030_variants.json
│   └── reviews/
│       ├── panel_A_uo_candidates.json
│       ├── panel_B_runs/
│       │   ├── run_1_2026-03-04.json
│       │   └── run_2_2026-03-05.json
│       ├── panel_C_runs/
│       │   └── run_1_2026-03-04.json
│       └── panel_D_runs/
│           └── run_1_2026-03-04.json
└── WD010/
    └── ...
```

---

## Execution Checklist (Thin Controller)

오케스트레이터는 아래 번호를 순서대로 실행한다. 각 단계에서 **스크립트를 실행**하거나 **executor 서브에이전트를 스폰**한다. 의사결정은 하지 않는다.

### 0. 세션 설정

```
SKILL_DIR=~/.claude/skills/wf-paper-mining
ASSETS=$SKILL_DIR/assets
ROOT_DIR=~/dev/wf-mining
REGISTRY=$ROOT_DIR/run_registry.json
```

### 1. 대상 워크플로 결정

사용자가 지정한 워크플로 ID 또는 `extraction_config.json`의 `domain_groups`에서 대상을 선택한다.
세션 예산: 최대 8개 워크플로/세션 (`execution.session_budget`).

### 2. RunManifest 생성 (워크플로별)

```bash
python -m scripts.plan_run \
  --wf-id {WF_ID} \
  --registry $REGISTRY \
  --assets $ASSETS \
  --output $ROOT_DIR/{WF_ID}/runs/
```

출력: `run_manifest_{run_id}.json`. 이 파일이 이후 모든 단계의 입력이 된다.

- `action == "skip"` → 해당 워크플로 건너뛰기 (saturated)
- `action == "execute"` → 아래 단계 진행

### 3. Phase 1: UO 후보 확인 (Panel A)

**조건**: `manifest.phases.phase1_resolve == true`

executor 서브에이전트에게 아래 프롬프트를 전달:

> "워크플로 {WF_ID}({manifest.session_context.wf_description})의 UO 후보를 검토한다.
> UO 카탈로그: {manifest.file_paths.extraction_guide}
> 도메인: {manifest.session_context.domain}
>
> 패널 프로토콜({manifest.file_paths.panel_protocol})에 따라 Panel A를 Full 모드로 실행.
> 3인 전문가가 UO 후보의 적절성을 평가한다.
>
> 결과를 {manifest.file_paths.wf_output_dir}/reviews/panel_A_uo_candidates.json에 저장."

### 4. Phase 2: 논문 검색

**조건**: `manifest.phases.phase2_search == true`

```bash
python -m scripts.search_papers \
  --workflow-id {WF_ID} \
  --run-id {manifest.run_id} \
  --config $ASSETS/extraction_config.json \
  --assets $ASSETS \
  --output $ROOT_DIR/{WF_ID} \
  --exclude-file $REGISTRY \
  --select-n {manifest.search_config.select_n} \
  --seed {manifest.search_config.seed}
```

출력: `paper_list_{manifest.run_id}.json`

**검색 스크립트 실행 직후** 경량 검증 (오케스트레이터가 파일을 직접 읽지 않음):

```bash
python -m scripts.validate_outputs \
  --output-dir $ROOT_DIR/{WF_ID} \
  --quick --run-id {manifest.run_id}
```

출력: `{"ok": true}` 또는 `{"ok": false, "reason": "..."}`. ok가 false일 때만 출력을 인용해 재실행 또는 보고.

### 5. Phase 2.5: Panel B - 논문 관련성 평가

**조건**: `manifest.panels.panel_b.run == true`

**범위**: `paper_list_{manifest.run_id}.json`의 논문만 평가 (현재 run의 새 논문만)

executor 서브에이전트에게 아래 프롬프트를 전달:

> "**필수**: `{manifest.file_paths.wf_output_dir}/01_papers/paper_list_{manifest.run_id}.json` 파일을 **반드시 읽어서** 각 논문의 `title`과 `abstract` 필드를 **그대로 인용**할 것.
>
> **필수**: 리뷰 JSON의 각 논문 항목에 `title` 필드를 포함하고, paper_list의 해당 논문 `title` 필드를 **정확히 복사**할 것 (직접 생성·추측 금지).
> 파일을 읽지 않고 워크플로 컨텍스트에서 그럴듯한 제목을 생성하지 말 것.
>
> 각 논문의 abstract를 바탕으로 워크플로 {WF_ID}에 대한 관련성을 평가한다.
> 패널 프로토콜에 따라 Panel B를 {manifest.panels.panel_b.mode} 모드로 실행.
> 3인 전문가 (Domain Expert, Methodology Reviewer, Critical Reviewer)가 평가.
>
> **핵심 원칙: 관대한 수용** - 부분적으로라도 관련 정보가 포함될 가능성이 있으면 accept.
> 각 워크플로는 전체 실험의 일부이므로, 정확히 해당 워크플로만 다루는 논문은 드물다.
> 관련 내용이 포함되어 있을 것 같으면 accept.
>
> Verdict: accept / reject
>
> 결과를 {manifest.file_paths.wf_output_dir}/reviews/panel_B_runs/run_{manifest.run_id}_{YYYY-MM-DD}.json에 저장.
> (panel_B_runs 디렉토리가 없으면 생성)"

### 5-0. Panel B 결과 교차 검증

Panel B 결과를 paper_list와 교차 검증:
- Panel B 리뷰의 `paper_id`가 paper_list에 모두 존재하는지 확인
- Panel B 출력에 `reviews[]` 내 논문별 `title` 필드가 포함된 경우, paper_list의 해당 `title`과 일치하는지 확인
- 불일치 발견 시 Panel B를 재실행

### 5-1. Panel B verdict 적용

Panel B 결과를 `paper_list`와 `run_registry`에 일괄 반영하는 스크립트를 실행한다.
오케스트레이터가 paper_list이나 Panel B 파일을 직접 읽지 않는다 (Context Discipline 참조).

```bash
python -m scripts.apply_panel_b_verdicts \
  --wf-id {WF_ID} \
  --panel-b-path $ROOT_DIR/{WF_ID}/reviews/panel_B_runs/run_{manifest.run_id}_{YYYY-MM-DD}.json \
  --paper-list-path $ROOT_DIR/{WF_ID}/01_papers/paper_list_{manifest.run_id}.json \
  --registry $REGISTRY
```

출력: `{"ok": true, "accepted": N, "rejected": M}`. ok가 false이거나 warnings가 있을 때만 내용을 확인한다.

### 6. Phase 3: Full Text 수집

**조건**: `manifest.phases.phase3_fetch == true`

```bash
python -m scripts.fetch_fulltext \
  --input $ROOT_DIR/{WF_ID}/01_papers/paper_list_{manifest.run_id}.json \
  --output $ROOT_DIR/{WF_ID} \
  --pending-only
```

`extraction_status == "rejected"`인 논문은 자동으로 스킵된다.

각 수집 완료 후 run_tracker 상태 업데이트:

```bash
python -m scripts.run_tracker mark-fetched \
  --wf-id {WF_ID} --paper-id {PAPER_ID} --registry $REGISTRY
```

### 7. Phase 4: 정보 추출

**조건**: `manifest.phases.phase4_extract == true`

accept되고 full text가 있는 각 논문에 대해 executor 서브에이전트를 스폰:

> "논문 {paper_id}의 full text ({wf_output_dir}/01_papers/full_texts/{paper_id}.txt)를 읽고
> 워크플로 {WF_ID}에 대한 정보를 추출한다.
>
> **추출 범위 (우선순위 순)**:
> 1. **타깃 워크플로 {WF_ID}**: 이 워크플로에 해당하는 UO, 장비, 시약, 소모품, 샘플 정보를 최우선으로 상세 추출
> 2. **선행 워크플로 (upstream)**: 타깃 워크플로 전에 수행되는 단계가 논문에 기술되어 있으면 함께 추출
>    (예: 균주 구축, 배지 준비, 시료 전처리, 형질전환 등)
> 3. **후행 워크플로 (downstream)**: 타깃 워크플로 후에 수행되는 단계가 논문에 기술되어 있으면 함께 추출
>    (예: 정제, 분석, 품질 검증, 스케일업 등)
>
> workflows 배열에 타깃 워크플로와 관련 전/후 워크플로를 모두 포함한다.
> 타깃 워크플로는 높은 confidence, 전/후 워크플로는 논문의 기술 정도에 따라 적절한 confidence를 부여한다.
> uo_connections에 워크플로 간 연결 관계(순서, 데이터 흐름)를 기록한다.
>
> extraction_template.json의 스키마에 따라:
> - workflows, hardware_uos, software_uos (7-component 구조)
> - equipment, consumables, reagents, samples
> - uo_connections, qc_checkpoints
> - 기존 카탈로그에 없는 신규 UO/워크플로 후보 (is_new=true)
>
> UO 카탈로그: {extraction_guide}
> 워크플로 카탈로그: $ASSETS/workflow_catalog.json
>
> 결과를 {wf_output_dir}/02_extractions/{paper_id}_{WF_ID}.json에 저장.
> ExtractionResult Pydantic 모델과 호환되는 JSON 형식으로 출력."

추출 완료 후:

```bash
python -m scripts.run_tracker mark-extracted \
  --wf-id {WF_ID} --paper-id {PAPER_ID} --registry $REGISTRY
```

### 8. Phase 4.1: Panel C - 추출 검증

**조건**: `manifest.panels.panel_c.run == true`

executor 서브에이전트에게:

> "워크플로 {WF_ID}의 추출 결과를 검증한다.
>
> 각 추출 결과({wf_output_dir}/02_extractions/*.json)에 대해 Panel C를 실행.
> 3인 전문가가 정확성, 완전성, 카탈로그 매핑, 신규 후보를 평가.
>
> Verdict: accept / flag_reextract / reject
>
> 결과를 {wf_output_dir}/reviews/panel_C_runs/run_{manifest.run_id}_{YYYY-MM-DD}.json에 저장.
> (panel_C_runs 디렉토리가 없으면 생성)"

Verdict 적용:

```bash
python -m scripts.run_tracker apply-verdict \
  --wf-id {WF_ID} --paper-id {PAPER_ID} --verdict {verdict} --registry $REGISTRY
```

### 9. Phase 4.5: Aggregation + Panel D

**조건**: `manifest.phases.phase4_5_aggregate == true`

executor 서브에이전트에게:

> "워크플로 {WF_ID}의 모든 추출 결과를 집계한다.
>
> 1. 02_extractions/의 모든 accept된 추출 결과를 읽는다
> 2. 리소스 요약(resource_summary.json)을 생성한다:
>    - UO 출현 빈도, 장비/시약/소모품/샘플 통계
>    - 신규 카탈로그 후보 목록
> 3. 워크플로 변종(variant_summary.json)을 생성한다:
>    - UO 구성이 다른 변종을 식별
>
> Panel D를 실행하여 변종의 적절성을 검증 (필요시).
>
> 결과를 {wf_output_dir}/03_summaries/에 저장."

### 10. Run 완료 기록

```bash
python -m scripts.run_tracker complete-run \
  --wf-id {WF_ID} \
  --run-id {manifest.run_id} \
  --papers-searched {N} \
  --papers-selected {N} \
  --papers-accepted {N} \
  --new-extractions {N} \
  --new-variants {N} \
  --panels-run "panel_b,panel_c" \
  --panel-mode {manifest.panels.panel_b.mode} \
  --registry $REGISTRY
```

### 11. Pydantic 검증

```bash
python -m scripts.validate_outputs \
  --output-dir $ROOT_DIR/{WF_ID} \
  --verbose
```

### 12. 다음 워크플로로 이동

세션 예산이 남아있으면 Step 2로 돌아가 다음 워크플로를 처리한다.

---

## Incremental Execution

- 매 run은 새로운 논문만 검색 (known DOI/PMID 제외)
- per-run paper_list로 기존 데이터와 분리
- Panel B는 현재 run의 논문만 평가
- 기존 추출 결과는 유지하고 새 논문의 결과만 추가
- Saturation detection으로 검색 포화 워크플로는 자동 스킵

## Context Discipline (컨텍스트 절약 규칙)

오케스트레이터의 컨텍스트 한도 도달을 방지하기 위한 필수 규칙:

1. **서브에이전트 결과 보고**: 서브에이전트 완료 시 전체 응답을 채팅에 붙여넣지 않는다. `"Phase X 완료, 출력: {path}"` 수준의 한 줄 요약만 보고.
2. **스크립트 출력 인용**: 스크립트 stdout/stderr는 **실패 시에만** 관련 부분을 인용. 성공 시에는 종료 코드와 출력 파일 경로만 보고.
3. **파일 읽기 금지**: 교차 검증이 필요한 경우 전용 스크립트(`apply_panel_b_verdicts.py`, `validate_outputs.py --quick`)를 사용. 오케스트레이터가 paper_list, panel 결과, 추출 결과를 직접 읽지 않는다. 검증 실패 시에만 해당 파일 내용을 인용.
4. **서브에이전트 프롬프트**: 모든 executor 서브에이전트 프롬프트 끝에 다음을 추가: `"완료 시 출력 파일 경로와 처리 결과(accept/reject 수 등)만 한 줄로 보고할 것."`

## Session Management

- 권장: 세션당 1-2개 워크플로. 3개 초과 시 컨텍스트 한도 도달 위험
- 논문 수가 많을 경우 select_n을 10-15로 제한
- 각 run은 독립적인 RunManifest로 실행
- 상태는 run_registry.json에 영구 저장
- 서브에이전트는 자체 완결적 프롬프트로 스폰 (컨텍스트 독립)
