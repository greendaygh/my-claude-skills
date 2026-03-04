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
│   │   ├── resource_summary.json
│   │   └── variant_summary.json
│   └── reviews/
│       ├── panel_A_uo_candidates.json
│       ├── panel_B_run_1.json
│       ├── panel_C_run_1.json
│       └── panel_D_run_1.json
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

### 5. Phase 2.5: Panel B - 논문 관련성 평가

**조건**: `manifest.panels.panel_b.run == true`

**범위**: `paper_list_{manifest.run_id}.json`의 논문만 평가 (현재 run의 새 논문만)

executor 서브에이전트에게 아래 프롬프트를 전달:

> "paper_list_{manifest.run_id}.json을 읽고, 각 논문의 abstract를 바탕으로 워크플로 {WF_ID}에 대한 관련성을 평가한다.
>
> 패널 프로토콜에 따라 Panel B를 {manifest.panels.panel_b.mode} 모드로 실행.
> 3인 전문가 (Domain Expert, Methodology Reviewer, Critical Reviewer)가 평가.
>
> **핵심 원칙: 관대한 수용** - 부분적으로라도 관련 정보가 포함될 가능성이 있으면 accept.
> 각 워크플로는 전체 실험의 일부이므로, 정확히 해당 워크플로만 다루는 논문은 드물다.
> 관련 내용이 포함되어 있을 것 같으면 accept.
>
> Verdict: accept / reject
>
> 결과를 {manifest.file_paths.wf_output_dir}/reviews/panel_B_run_{manifest.run_id}.json에 저장."

### 5-1. Panel B verdict 적용

Panel B 결과를 `paper_list_{manifest.run_id}.json`에 반영:
- reject된 논문: `extraction_status`를 `"rejected"`로 변경
- 이를 통해 `fetch_fulltext`가 rejected 논문을 자동으로 스킵

```python
# 오케스트레이터가 직접 실행하거나 서브에이전트에게 위임
import json
paper_list_path = f"$ROOT_DIR/{WF_ID}/01_papers/paper_list_{manifest.run_id}.json"
panel_b_path = f"$ROOT_DIR/{WF_ID}/reviews/panel_B_run_{manifest.run_id}.json"

data = json.loads(open(paper_list_path).read())
verdicts = json.loads(open(panel_b_path).read())

for paper in data["papers"]:
    pid = paper["paper_id"]
    if pid in verdicts.get("final_verdicts", {}) and verdicts["final_verdicts"][pid] == "reject":
        paper["extraction_status"] = "rejected"

open(paper_list_path, "w").write(json.dumps(data, indent=2, ensure_ascii=False))
```

run_tracker에도 verdict 반영:

```bash
python -m scripts.run_tracker apply-verdict \
  --wf-id {WF_ID} --paper-id {PAPER_ID} --verdict {accept|reject} \
  --registry $REGISTRY
```

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
> 결과를 {wf_output_dir}/reviews/panel_C_run_{manifest.run_id}.json에 저장."

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

## Session Management

- 같은 세션에서 10회 이상 반복 가능
- 각 run은 독립적인 RunManifest로 실행
- 상태는 run_registry.json에 영구 저장
- 서브에이전트는 자체 완결적 프롬프트로 스폰 (컨텍스트 독립)
