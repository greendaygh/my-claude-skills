# wf-extraction-review: 워크플로 추출 데이터 검토·보강

기존 wf-paper-mining으로 추출된 데이터를 full text와 대조하여 검토·보강·수정하는 스킬.

## Trigger Phrases

"추출 검토", "extraction review", "데이터 보강", "워크플로 검토", "wf-extraction-review"

## Architecture

- **Thin Controller** 패턴: 오케스트레이터는 스크립트 실행 + 서브에이전트 스폰만 수행.
- **순차 실행 전용**: 워크플로 간 병렬 실행 금지.
- **서브에이전트 최대 3회**: 검토·보강, Panel C, flag_reextract 처리
- **wf-paper-mining 공유**: assets, scripts (aggregate_summary, validate_outputs, run_tracker)를 공유 참조.

## Prerequisites

- wf-paper-mining 스킬이 설치되어 있어야 함 (`~/.claude/skills/wf-paper-mining/`)
- Python 3.10+ with `pydantic>=2.0`
- 출력 디렉토리: `~/dev/wf-mining/`

---

## Execution Checklist (5단계)

### 0. 세션 설정

```
SKILL_DIR=~/.claude/skills/wf-extraction-review
MINING_SKILL=~/.claude/skills/wf-paper-mining
ASSETS=$MINING_SKILL/assets
ROOT_DIR=~/dev/wf-mining
```

**중요: wf-paper-mining의 python 스크립트를 실행할 때는 반드시 `cd $MINING_SKILL &&`를 붙일 것.**

사용자가 지정한 워크플로 ID를 `WF_ID`로 설정.

### 1. 대상 파악 + 백업

대상 논문 목록 확인 (full text + extraction 모두 존재하는 논문):

```bash
python3 -c "
import json, os, glob
root = os.path.expanduser('~/dev/wf-mining')
wf_id = '{WF_ID}'
ext_dir = f'{root}/{wf_id}/02_extractions'
ft_dir = f'{root}/{wf_id}/01_papers/full_texts'
targets = []
for f in sorted(glob.glob(f'{ext_dir}/*.json')):
    pid = os.path.basename(f).replace('.json','')
    ft = f'{ft_dir}/{pid}.txt'
    if os.path.exists(ft):
        targets.append(pid)
print(json.dumps({'workflow_id': wf_id, 'total_targets': len(targets), 'targets': targets}, indent=2))
"
```

사용자에게 대상 수를 보고한 후 백업:

```bash
cp -r $ROOT_DIR/{WF_ID}/02_extractions $ROOT_DIR/{WF_ID}/02_extractions_backup_$(date +%Y%m%d)
```

### 2. 검토·보강 (서브에이전트 1회)

**서브에이전트** 스폰:

> "워크플로 {WF_ID}의 기존 추출 데이터를 full text와 대조하여 검토·보강한다.
>
> 각 논문에 대해 두 파일을 모두 읽는다:
> 1. 기존 추출: {wf_output_dir}/02_extractions/{paper_id}.json
> 2. Full text: {wf_output_dir}/01_papers/full_texts/{paper_id}.txt
>
> {wf_output_dir}/01_papers/full_texts/ 디렉토리의 모든 .txt 파일을 대상으로 하되,
> 해당 paper_id의 extraction 파일이 02_extractions/에 존재하는 논문만 처리한다.
>
> 기존 추출을 기반으로 아래 항목을 검토·보강한다:
>
> **유지**: 기존에 정확히 추출된 내용은 변경하지 않는다.
>
> **보강**:
> - workflow_connections 필드가 없으면 추가한다
>   - from_workflow, to_workflow: 워크플로 catalog_id (예: WB045, WT010)
>   - relationship: upstream / downstream / parallel
>   - description: 관계 설명
> - full text에 명시되어 있지만 기존 추출에서 누락된 UO, equipment, consumables, reagents, samples를 추가한다
> - 빈 문자열("")인 필드 중 full text에 정보가 있는 경우 채운다
> - doi 필드가 없으면 wf_state.json의 paper_status에서 가져와 추가한다
>
> **수정**:
> - uo_connections의 from_uo/to_uo가 워크플로 이름이나 ID인 경우:
>   → 해당 연결이 실제로 같은 파일의 hardware_uos/software_uos에 있는 UO를 가리키면 catalog_id로 수정
>   → 매핑할 수 없으면 해당 connection을 삭제하고, 대신 workflow_connections에 적절한 항목을 추가
> - catalog_id가 잘못된 경우(예: hardware_uos에 워크플로 ID가 들어간 경우) 수정
>
> **삭제 금지**: 기존에 있는 유효한 데이터를 제거하지 말 것.
>
> **uo_connections 규칙**:
> - 카탈로그에 존재하는 UO: catalog_id (예: UHW250, USW130) 사용
> - is_new=true인 UO: 해당 UO의 name 사용
> - from_uo와 to_uo는 반드시 이 파일의 hardware_uos 또는 software_uos에 존재하는 UO만 참조
>
> **workflows 규칙**:
> - 처리 대상 워크플로({WF_ID})가 논문에 언급되어 있다면 반드시 workflows 배열에 포함
>
> 결과를 {wf_output_dir}/02_extractions/{paper_id}.json에 저장 (기존 파일 덮어쓰기).
> 각 파일 저장 후 JSON 유효성을 검증. 실패 시 해당 파일 삭제하지 말고 오류를 보고.
>
> UO 카탈로그: $ASSETS/uo_catalog.json
> 워크플로 카탈로그: $ASSETS/workflow_catalog.json
> 추출 템플릿: $ASSETS/extraction_template.json
> wf_state: {wf_output_dir}/wf_state.json
>
> 완료 시 처리/보강/수정/스킵한 논문 수를 보고."

서브에이전트 완료 후 JSON cleanup:

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
        print(f'Invalid JSON (NOT removed, check manually): {f} ({e})', file=sys.stderr)
"
```

### 3. Panel C 검증 (서브에이전트 1회)

**서브에이전트** 스폰:

> "워크플로 {WF_ID}의 업데이트된 추출 결과를 full text와 대조하여 검증한다.
>
> 각 논문에 대해 두 파일을 모두 읽는다:
> 1. 추출 결과: {wf_output_dir}/02_extractions/{paper_id}.json
> 2. Full text: {wf_output_dir}/01_papers/full_texts/{paper_id}.txt
>
> 검증 기준:
> - **완전성**: full text에 있는 주요 정보(UO, equipment, reagents)가 추출에 반영되었는지
> - **정확성**: 추출된 정보가 full text 내용과 일치하는지
> - **구조 준수**: uo_connections가 catalog_id를 사용하는지, workflow_connections가 적절한지
> - **스키마 준수**: doi 존재, 빈 필드 최소화, confidence 값 범위 0.0~1.0
>
> 3인 전문가 (Extraction Reviewer, Catalog Matcher, Completeness Reviewer):
> - Round 1: 각 전문가가 독립적으로 score(0.0~1.0 float, 소수점 필수) + notes/issues 작성
> - Round 2: 점수 공유 후 토론
> - Round 3: 최종 accept/flag_reextract/reject 투표
>
> **flag_reextract 기준**: 주요 UO 누락, 잘못된 카탈로그 매칭, 심각한 구조적 오류
> **reject 기준**: 논문과 무관한 추출, 전면적 오류
>
> 출력 JSON 형식:
> ```json
> {
>   "workflow_id": "{WF_ID}",
>   "panel": "panel_c",
>   "mode": "extraction_review",
>   "run_date": "YYYY-MM-DD",
>   "summary": {"total": N, "accept": N, "flag_reextract": N, "reject": N},
>   "papers": [
>     {
>       "paper_id": "...",
>       "round_1": {...},
>       "round_2": {...},
>       "round_3_vote": {...},
>       "final_score": 0.85,
>       "verdict": "accept",
>       "key_issues": ["..."]
>     }
>   ]
> }
> ```
>
> 결과를 {wf_output_dir}/reviews/panel_C_runs/review_{YYYY-MM-DD}.json에 저장.
> 완료 시 accept/flag_reextract/reject 수와 파일 경로를 보고."

### 4. flag_reextract 처리 (조건부)

Panel C에서 `flag_reextract` 논문이 있을 경우에만 실행:

**flag 논문의 기존 extraction 파일을 삭제** 후, **서브에이전트 1회** 스폰하여 clean slate 재추출:

> "아래 논문들의 full text에서 처음부터 새로 추출한다. 기존 추출은 참조하지 않는다.
>
> 대상 논문: {flag_paper_ids}
>
> 각 논문에 대해:
> 1. {wf_output_dir}/01_papers/full_texts/{paper_id}.txt를 읽는다
> 2. extraction_template.json 스키마에 따라 추출:
>    - workflows, hardware_uos, software_uos (7-component 구조)
>    - equipment, consumables, reagents, samples
>    - uo_connections, qc_checkpoints, workflow_connections
>
>    **uo_connections 규칙**:
>    - 카탈로그에 존재하는 UO: catalog_id (예: UHW250, USW130) 사용
>    - is_new=true인 UO: 해당 UO의 name 사용
>    - from_uo와 to_uo는 반드시 이 파일의 hardware_uos 또는 software_uos에 존재하는 UO만 참조
>    - 워크플로 간 관계는 workflow_connections에 별도 기록
>
>    **workflow_connections 규칙**:
>    - from_workflow, to_workflow: 워크플로 catalog_id 사용
>    - relationship: upstream / downstream / parallel
>
>    **workflows 규칙**:
>    - 처리 대상 워크플로({WF_ID})가 언급되어 있으면 배열에 포함
>
>    **doi 규칙**:
>    - 반드시 doi 포함. wf_state.json에서 참조.
>
> 3. 결과를 {wf_output_dir}/02_extractions/{paper_id}.json에 저장
> 4. JSON 유효성 검증. 실패 시 삭제 후 다음 논문으로 진행.
>
> UO 카탈로그: $ASSETS/uo_catalog.json
> 워크플로 카탈로그: $ASSETS/workflow_catalog.json
>
> 완료 시 처리한 논문 수를 보고."

### 5. 집계 + 검증

```bash
cd $MINING_SKILL && python -m scripts.run_tracker sync-after-cleanup \
  --wf-id {WF_ID} --root-dir $ROOT_DIR
```

```bash
cd $MINING_SKILL && python -m scripts.aggregate_summary \
  --input $ROOT_DIR/{WF_ID}/02_extractions \
  --output $ROOT_DIR/{WF_ID}/03_summaries \
  --root-dir $ROOT_DIR \
  --workflow-id {WF_ID}
```

```bash
cd $MINING_SKILL && python -m scripts.validate_outputs \
  --output-dir $ROOT_DIR/{WF_ID} --verbose
```

검증 결과를 사용자에게 보고.

### 6. 백업 정리

검토 결과가 만족스러우면:
```bash
rm -rf $ROOT_DIR/{WF_ID}/02_extractions_backup_*
```

불만족 시 롤백:
```bash
rm -rf $ROOT_DIR/{WF_ID}/02_extractions
mv $ROOT_DIR/{WF_ID}/02_extractions_backup_* $ROOT_DIR/{WF_ID}/02_extractions
```

---

## 멀티 워크플로 실행

사용자가 여러 워크플로를 요청할 때:
1. 워크플로 목록을 순서대로 정렬
2. **한 번에 1개 워크플로만** 5단계 전체를 완료
3. 완료 후 다음 워크플로로 진행
