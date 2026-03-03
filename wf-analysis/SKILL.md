---
skill: wf-analysis
trigger: /wf-analysis
description: >
  Analyze collected case cards to derive common workflow patterns, variants,
  and map to standardized Unit Operations with typed 7-component structures.
version: 2.1.0
author: SBLab KRIBB
tags: [biofoundry, workflow, analysis, unit-operation, variant]
---

# WF-Analysis v2.1 — Case Analysis & UO Mapping

Analyze case cards, derive workflow patterns, map to Unit Operations, and compose typed variant structures.

## Invocation

```
/wf-analysis {wf_dir}
```

**Prerequisites**:
- `{wf_dir}/02_cases/case_C*.json` — at least 3 case cards
- `{wf_dir}/02_cases/case_summary.json` — case summary

## Reference Files

| Phase | Files |
|-------|-------|
| 3 Analyze | `references/case-analysis-guide.md`, `references/unit-operation-mapping.md` |
| 4 Compose | `references/hw-component-guide.md`, `references/sw-component-guide.md`, `references/qc-checkpoint-guide.md` |

## Phase 3 — Analyze

### 3.1 Case Comparative Analysis — per `references/case-analysis-guide.md`

- Step alignment: align cases by functional equivalence
- Common step identification: mandatory (>=60%), conditional, branch points
- Variant derivation: cluster by technique, scale, organism (min 2 cases per variant)
- Parameter ranges: aggregate per-step statistics
- Modularity analysis: boundary I/O, upstream/downstream workflows

Save to `03_analysis/`.

### 3.2 UO Mapping — per `references/unit-operation-mapping.md`

- Multi-signal scoring: equipment 0.35, function 0.30, I/O 0.20, context 0.15
- Score >= 0.7 = strong match
- Classify HW vs SW per decision tree

Save `04_workflow/uo_mapping.json`, `04_workflow/qc_checkpoints.json`.

## Phase 4 — Compose

### 4.1 7-Component Population

For each UO in each variant, populate typed components from case data:
- **HW UO**: Input, Output, Equipment, Consumables, Material/Method, Result, Discussion → `references/hw-component-guide.md`
- **SW UO**: Input, Output, Parameters, Environment, Method, Result, Discussion → `references/sw-component-guide.md`
- Every value must include `case_refs` and `evidence_tag`

Save `04_workflow/variant_V1_*.json`, etc.

#### Canonical Variant File Format (MANDATORY)

All variant files MUST use the canonical format:

| Field | Canonical Key | Legacy (do NOT use) |
|-------|---------------|---------------------|
| UO sequence | `unit_operations` | ~~`uo_sequence`~~ |
| Variant name | `variant_name` | ~~`name`~~ |
| Case references | `case_ids` | ~~`case_refs`~~, ~~`cases`~~, ~~`supporting_cases`~~ |
| Step position | `step_position` (integer) | ~~string position~~ |
| Components | Flat on UO object (`input`, `output`, `equipment`, ...) | ~~nested under `components` wrapper~~ |
| Material/Method | `material_and_method` | ~~`Material_Method`~~ |

### 4.2 QC Checkpoint Design — per `references/qc-checkpoint-guide.md`

### 4.3 Gap-Fill Search

For components with many `[미기재]` items:
- Targeted WebSearch for manufacturer protocols, application notes
- Generate expert-inference items list

### 4.4 Pydantic Gate 3 — MANDATORY

Validate all Phase 3+4 outputs. Uses `wf-audit/scripts/models/` canonical models.

```python
from wf_audit.scripts.models.analysis import StepAlignment, ClusterResult, CommonPattern, ParameterRanges
from wf_audit.scripts.models.uo_mapping import UoMapping
from wf_audit.scripts.models.variant import Variant
from wf_audit.scripts.models.qc_checkpoints import QcCheckpoints
import json, glob

errors = []
checks = [
    ("03_analysis/step_alignment.json", StepAlignment),
    ("03_analysis/cluster_result.json", ClusterResult),
    ("03_analysis/common_pattern.json", CommonPattern),
    ("03_analysis/parameter_ranges.json", ParameterRanges),
    ("04_workflow/uo_mapping.json", UoMapping),
    ("04_workflow/qc_checkpoints.json", QcCheckpoints),
]
for fname, model_cls in checks:
    with open(f"{wf_dir}/{fname}") as f:
        try: model_cls.model_validate(json.load(f))
        except Exception as e: errors.append((fname, str(e)))

for fp in glob.glob(f"{wf_dir}/04_workflow/variant_V*.json"):
    with open(fp) as f:
        try: Variant.model_validate(json.load(f))
        except Exception as e: errors.append((fp, str(e)))
```

**Pass**: 0 ValidationError. **Fail**: fix using error hints, re-validate (max 2 retries).

### 4.5 Analysis Panel — MANDATORY (Self-Performed)

각 리뷰 토픽에 **3명 전문가 패널**을 구성하여 3-round 프로토콜 수행.
모든 리뷰 출력은 **한국어**로 작성 (JSON 키 이름은 영어 유지).

**1. Variant Clustering Review Panel (3명)**
- 클러스터링 방법론 전문가: 클러스터링 알고리즘/기준의 통계적 적절성, primary/secondary axis 합리성
- 도메인 워크플로우 전문가: 워크플로우 도메인 관점에서 variant 구분 합리성, 기술적 차이 유의미성
- 데이터 품질 검토자: case 배정 누락/중복, 최소 2 case/variant 충족, case_ids 정합성
- Input: `cluster_result.json` + `case_summary.json` + `case_C*.json`
- Protocol: 3-round (독립 리뷰 → 쟁점 토론 → 합의 투표)
- Output: `06_review/variant_clustering_review.json` (한국어)

**2. UO Mapping Review Panel (3명)**
- UO 카탈로그 전문가: UO catalog 매칭 정확성, 미존재 operation 식별, 신규 UO 제안
- 장비/기능 전문가: HW/SW 분류 적정성, multi-signal scoring 합리성, 가중치 타당성
- 워크플로우 간 일관성 검토자: 다른 워크플로우와의 UO 사용 일관성, 재사용 패턴
- Input: `uo_mapping.json` + `variant_V*.json` + UO catalog
- Protocol: 3-round (독립 리뷰 → 쟁점 토론 → 합의 투표)
- Output: `06_review/uo_mapping_review.json` (한국어)

**3. QC Checkpoint Review Panel (3명)**
- QC 설계 전문가: QC 배치 위치 적절성, 누락 QC 포인트 식별, 유형별 분포
- 분석 방법론 전문가: pass/fail 기준의 과학적 타당성, 정량적 임계값 근거
- 프로세스 흐름 검토자: QC-variant 매핑, 분기 로직 적절성, fail action 합리성
- Input: `qc_checkpoints.json` + `variant_V*.json` + `common_pattern.json`
- Protocol: 3-round (독립 리뷰 → 쟁점 토론 → 합의 투표)
- Output: `06_review/qc_checkpoint_review.json` (한국어)

**Review JSON Output Format** (3개 파일 공통):
```json
{
  "review_type": "variant_clustering | uo_mapping | qc_checkpoint",
  "workflow_id": "WB005",
  "date": "2026-03-03",
  "language": "ko",
  "experts": [
    {"role": "전문가 역할명", "independent_review": "독립 리뷰 내용 (한국어)", "verdict": "pass|flag|fail"},
    {"role": "전문가 역할명", "independent_review": "...", "verdict": "pass|flag|fail"},
    {"role": "전문가 역할명", "independent_review": "...", "verdict": "pass|flag|fail"}
  ],
  "discussion_summary": "3명 전문가 토론 요약 — 쟁점, 합의점, 미합의점 (한국어)",
  "consensus": {
    "verdict": "pass | revision_needed | fail",
    "conditions": ["조건 목록 (한국어)"],
    "recommendations": ["권고 사항 (한국어)"]
  },
  "issues": [{"severity": "minor|major", "description": "이슈 설명 (한국어)"}],
  "recommendations": ["전체 권고 (한국어)"]
}
```

**Consensus Rules**: 3명 중 2명 이상 pass → pass. 1명이라도 fail → revision_needed.
All 3 topics must pass → proceed to Phase 5. If `revision_needed` → fix and re-review (max 1 retry).

## External Skill Dependencies

None (peer-review replaced by self-performed Analysis Panel in Phase 4.5).

## Output Contract

```
{wf_dir}/
├── 03_analysis/
│   ├── step_alignment.json
│   ├── cluster_result.json
│   ├── common_pattern.json
│   └── parameter_ranges.json
├── 04_workflow/
│   ├── uo_mapping.json
│   ├── variant_V1_*.json ... variant_VN_*.json
│   └── qc_checkpoints.json
└── 06_review/
    ├── variant_clustering_review.json
    ├── uo_mapping_review.json
    └── qc_checkpoint_review.json
```

## Evidence Tagging

| Priority | Tag | Description |
|---|---|---|
| 1 | `literature-direct` | Paper Methods/Results direct extraction |
| 2 | `literature-supplementary` | From supplementary materials |
| 3 | `literature-consensus` | Multiple cases agree |
| 4 | `manufacturer-protocol` | Equipment/kit manufacturer docs |
| 5 | `expert-inference` | Inferred — reasoning required |
| 6 | `catalog-default` | UO catalog default (last resort) |
