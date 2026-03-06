# wf-paper-mining: Biofoundry 워크플로 논문 마이닝

Scientific literature에서 biofoundry 워크플로 관련 정보(UO, 장비, 소모품, 시약, 샘플)를 체계적으로 수집·추출하는 스킬.

## Trigger Phrases

"워크플로 논문 마이닝", "paper mining", "논문 수집", "wf-paper-mining 실행"

## Architecture

- **Thin Controller** 패턴: 오케스트레이터는 스크립트 실행 + 서브에이전트 스폰만 수행. 의사결정 금지.
- **순차 실행 전용**: 워크플로 간 병렬 실행 절대 금지. 한 워크플로의 6단계가 모두 완료된 후 다음 워크플로 시작.
- **서브에이전트 최대 3회**: Panel B, 배치 추출, Panel C+집계
- **RunManifest**: `plan_run.py`가 생성하는 결정론적 실행 계획
- **워크플로별 논문 ID**: `{WF_ID}_P{NNN}` 형식 (예: `WB030_P001`). 전역 ID 사용 금지.

## 멀티 워크플로 실행 규칙

사용자가 "모든 워크플로" 또는 여러 워크플로를 요청할 때:
1. 워크플로 목록을 domain_group 순서대로 정렬
2. **한 번에 1개 워크플로만** 6단계 전체를 완료
3. 완료 후 다음 워크플로로 진행
4. **절대로 하지 말 것**:
   - 여러 워크플로의 Panel B를 동시에 스폰
   - 여러 워크플로의 추출을 하나의 에이전트에 묶어서 실행
   - background agent로 다음 워크플로를 미리 시작
   - 한 워크플로 내에서 Panel B와 추출을 동시에 실행

## Prerequisites

- Python 3.10+ with `pydantic>=2.0`, `requests`, `lxml`
- 인터넷 접속 (PubMed, OpenAlex, PMC API)
- 출력 디렉토리: `~/dev/wf-mining/`

## Directory Structure

```
~/dev/wf-mining/                    # ROOT_DIR
├── run_registry.json               # 전체 상태 관리
├── WB030/                          # 워크플로별 출력
│   ├── 01_papers/
│   │   ├── paper_list_1.json
│   │   └── full_texts/
│   │       └── WB030_P001.txt
│   ├── 02_extractions/
│   │   └── WB030_P001.json
│   ├── 03_summaries/
│   │   ├── WB030_resource_summary.json
│   │   └── WB030_variants.json
│   ├── reviews/
│   │   ├── panel_B_runs/
│   │   │   └── run_1_2026-03-04.json
│   │   └── panel_C_runs/
│   │       └── run_1_2026-03-04.json
│   └── runs/
│       └── run_manifest_1.json
```

---

## Execution Checklist (6단계)

오케스트레이터는 아래 단계를 순서대로 실행한다.

### 0. 세션 설정

```
SKILL_DIR=~/.claude/skills/wf-paper-mining
ASSETS=$SKILL_DIR/assets
ROOT_DIR=~/dev/wf-mining
REGISTRY=$ROOT_DIR/run_registry.json
```

사용자가 지정한 워크플로 ID를 `WF_ID`로 설정. **세션당 1개 워크플로만 처리.**

### 1. RunManifest 생성

```bash
python -m scripts.plan_run \
  --wf-id {WF_ID} \
  --registry $REGISTRY \
  --assets $ASSETS \
  --output $ROOT_DIR/{WF_ID}/runs/
```

출력: `run_manifest_{run_id}.json`.
- `action == "skip"` → 해당 워크플로 건너뛰기 (saturated). 사용자에게 보고 후 종료.
- `action == "execute"` → 아래 단계 진행.

### 2. 논문 검색 + 검증

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

검색 직후 경량 검증:

```bash
python -m scripts.validate_outputs \
  --output-dir $ROOT_DIR/{WF_ID} \
  --quick --run-id {manifest.run_id}
```

ok가 false일 때만 출력을 확인.

### 3. Panel B: 논문 관련성 평가 + verdict 적용

**서브에이전트 1회** 스폰:

> "**필수**: `{wf_output_dir}/01_papers/paper_list_{run_id}.json` 파일을 읽어서 각 논문의 title과 abstract를 확인할 것.
>
> 3인 전문가 (Domain Expert, Methodology Reviewer, Critical Reviewer)가 2라운드로 평가:
>
> **Round 1**: 각 전문가가 독립적으로 score(0~1) + 1줄 reasoning 작성
> **Round 2**: 점수 공유 후 최종 accept/reject 투표 (과반수 결정)
>
> **핵심 원칙: 관대한 수용** — 부분적으로라도 관련 정보가 포함될 가능성이 있으면 accept.
>
> 출력 JSON 형식:
> ```json
> {
>   "papers": [
>     {
>       "paper_id": "P0001",
>       "title": "(paper_list에서 복사)",
>       "round_1": {
>         "domain_expert": {"score": 0.2, "reasoning": "1줄 이유"},
>         "methodology_reviewer": {"score": 0.2, "reasoning": "1줄 이유"},
>         "critical_reviewer": {"score": 0.25, "reasoning": "1줄 이유"}
>       },
>       "round_2_vote": {"domain_expert": "reject", "methodology_reviewer": "reject", "critical_reviewer": "reject"},
>       "verdict": "reject",
>       "reason": "1줄 요약"
>     }
>   ]
> }
> ```
>
> 결과를 {wf_output_dir}/reviews/panel_B_runs/run_{run_id}_{YYYY-MM-DD}.json에 저장.
> 완료 시 출력 파일 경로와 accept/reject 수만 한 줄로 보고."

Panel B 완료 후 verdict 적용:

```bash
python -m scripts.apply_panel_b_verdicts \
  --wf-id {WF_ID} \
  --panel-b-path $ROOT_DIR/{WF_ID}/reviews/panel_B_runs/run_{run_id}_{YYYY-MM-DD}.json \
  --paper-list-path $ROOT_DIR/{WF_ID}/01_papers/paper_list_{run_id}.json \
  --registry $REGISTRY \
  --cross-validate
```

ok가 false이거나 warnings가 있을 때만 내용을 확인.

### 4. Full Text 수집 + 배치 추출

Full text 수집:

```bash
python -m scripts.fetch_fulltext \
  --input $ROOT_DIR/{WF_ID}/01_papers/paper_list_{run_id}.json \
  --output $ROOT_DIR/{WF_ID} \
  --pending-only
```

accept되고 full text가 있는 논문에 대해 **서브에이전트 1회** 스폰 (배치 추출):

> "accept된 논문들의 full text를 순차적으로 읽고 추출한다.
>
> paper_list: {wf_output_dir}/01_papers/paper_list_{run_id}.json
> → extraction_status가 'pending'이고 has_full_text가 true인 논문만 처리.
>
> 각 논문에 대해:
> 1. {wf_output_dir}/01_papers/full_texts/{paper_id}.txt를 읽는다
> 2. extraction_template.json 스키마에 따라 추출:
>    - workflows, hardware_uos, software_uos (7-component 구조)
>    - equipment, consumables, reagents, samples
>    - uo_connections, qc_checkpoints
> 3. 결과를 {wf_output_dir}/02_extractions/{paper_id}.json에 저장
> 4. 각 파일 저장 후 JSON 유효성을 검증 (python -c "import json; json.load(open('파일'))"). 실패 시 해당 파일 삭제 후 다음 논문으로 진행.
>
> **추출 범위**: 타깃 워크플로 + upstream/downstream 워크플로
> **주의**: 정보가 없는 str 필드는 null이 아닌 빈 문자열 ""을 사용할 것.
> UO 카탈로그: {extraction_guide}
> 워크플로 카탈로그: $ASSETS/workflow_catalog.json
>
> 완료 시 처리한 논문 수와 출력 경로만 한 줄로 보고."

배치 추출 서브에이전트 완료 후, 오케스트레이터는 잘린 JSON 정리:

```bash
python -c "
import json, os, sys
ext_dir = '$ROOT_DIR/{WF_ID}/02_extractions'
for f in os.listdir(ext_dir):
    if not f.endswith('.json'): continue
    path = os.path.join(ext_dir, f)
    try:
        json.load(open(path))
    except (json.JSONDecodeError, Exception) as e:
        print(f'Removing invalid extraction: {f} ({e})', file=sys.stderr)
        os.remove(path)
"
```

### 5a. Panel C: 추출 검증

**서브에이전트 1회** 스폰 (추출 검증만 수행):

> "워크플로 {WF_ID}의 추출 결과를 검증한다.
>
> {wf_output_dir}/02_extractions/*.json을 읽고 각 추출의 정확성/완전성 평가:
> - 3인 전문가 (Extraction Reviewer, Catalog Matcher, Completeness Reviewer)
> - Round 1: 각 전문가가 독립적으로 score(0~1) + notes/issues 작성
> - Round 2: 점수 공유 후 토론
> - Round 3: 최종 accept/flag_reextract/reject 투표
>
> 출력 JSON 형식:
> ```json
> {
>   "workflow_id": "{WF_ID}",
>   "panel": "panel_c",
>   "run_id": {run_id},
>   "summary": {"total_extractions": N, "accept": N, "flag_reextract": N, "reject": N},
>   "papers": [{"paper_id": "P0001", "round_1": {...}, "round_3_vote": {...}, "verdict": "accept"}]
> }
> ```
>
> **반드시** {wf_output_dir}/reviews/panel_C_runs/run_{run_id}_{YYYY-MM-DD}.json에 저장.
> 완료 시 accept/reject 수와 출력 파일 경로만 한 줄로 보고."

### 5b. 집계

Panel C 완료 후 스크립트로 집계 (서브에이전트 불필요):

```bash
python -m scripts.aggregate_summary \
  --input $ROOT_DIR/{WF_ID}/02_extractions \
  --output $ROOT_DIR/{WF_ID}/03_summaries \
  --registry $REGISTRY \
  --workflow-id {WF_ID}
```

### 6. Run 완료 + 검증

```bash
python -m scripts.run_tracker complete-run \
  --wf-id {WF_ID} \
  --run-id {run_id} \
  --papers-searched {N} \
  --papers-selected {N} \
  --papers-accepted {N} \
  --new-extractions {N} \
  --new-variants {N} \
  --panels-run "panel_b,panel_c" \
  --panel-mode {panel_mode} \
  --domain {manifest.session_context.domain} \
  --registry $REGISTRY

# Note: domain은 workflow_catalog.json의 category (design/build/test/learn)에서 자동 결정됨
```

```bash
python -m scripts.validate_outputs \
  --output-dir $ROOT_DIR/{WF_ID} \
  --verbose
```

---

## Incremental Execution

- 매 run은 새로운 논문만 검색 (known DOI/PMID 제외)
- per-run paper_list로 기존 데이터와 분리
- Panel B는 현재 run의 논문만 평가
- Saturation detection으로 검색 포화 워크플로는 자동 스킵
