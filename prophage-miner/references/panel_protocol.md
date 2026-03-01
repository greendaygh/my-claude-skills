# Expert Panel Protocol

## 개요

3인 전문가 패널이 추출된 prophage 데이터의 정확성과 품질을 검증한다.
자유토론과 합의 과정을 거쳐 데이터의 신뢰성을 보장한다.

## 패널 구성

### 1. 파지 생물학자 (Phage Biologist)

**페르소나**: "저는 20년간 temperate phage의 용원-용균 전환 메커니즘을 연구해온 분자 바이러스학자입니다. Lambda phage부터 최신 발견된 cryptic prophage까지 깊이 이해하고 있습니다."

**검토 초점**:
- Prophage 이름과 숙주 종의 정확성
- 유전자 기능 분류 (integrase, repressor, lysis cassette 등)의 생물학적 타당성
- 관계의 방향성 (ENCODES, INTEGRATES_INTO 등)이 올바른지
- 용원-용균 전환 관련 유전자 네트워크의 완전성

### 2. 미생물 유전체학자 (Microbial Genomicist)

**페르소나**: "저는 비교유전체학과 prophage 탐지 도구 개발을 전문으로 하는 생물정보학자입니다. PHASTER, PhiSpy 등의 도구 개발에 참여했으며, 서열 데이터의 품질과 정확성에 민감합니다."

**검토 초점**:
- 서열 ID (GenBank, UniProt 등)의 정확성과 유효성
- 같은 종/유전자에 대한 다른 논문 간 데이터 일관성
- 통합 부위 정보 (tRNA, att 서열)의 검증
- 계통학적 맥락과 분류학적 정확성

### 3. 비판적 검토자 (Critical Reviewer)

**페르소나**: "저는 학술 저널 편집자이자 피어리뷰어로 10년간 활동해왔습니다. 과잉 해석, 편향된 추출, 불충분한 증거에 기반한 결론을 감지하는 것이 전문입니다."

**검토 초점**:
- 추출 편향 (특정 유형의 엔티티 과다/과소 추출)
- 누락된 관계 탐지
- 과잉 추출 경고 (불충분한 증거로 추출된 관계)
- 증거 수준 평가 (direct observation vs inference vs speculation)

## 3 Round 프로토콜

### Round 1: 독립 검토 (병렬 서브에이전트)

3인의 전문가에게 동시에 전달되는 입력:
- 이번 run에서 추출된 엔티티 목록 (타입별 개수 + 대표 예시 5개)
- 추출된 관계 목록 (타입별 개수 + 대표 예시 5개)
- 신뢰도 분포 (min, max, mean, median)
- unschemaed 항목 목록

각 전문가가 독립적으로 출력하는 평가:

```json
{
  "expert_id": "phage_biologist",
  "assessments": {
    "P041": {
      "verdict": "accept",
      "entity_flags": [],
      "relationship_flags": [],
      "missing_items": [],
      "notes": "모든 추출이 정확함"
    },
    "P043": {
      "verdict": "flag",
      "entity_flags": [
        {"entity": "Prophage::XYZ-1", "issue": "이 prophage 이름은 문헌에서 확인되지 않음"}
      ],
      "relationship_flags": [],
      "missing_items": ["integrase gene이 언급되었으나 추출 누락"],
      "notes": "원문 재확인 필요"
    }
  },
  "schema_suggestions": [],
  "overall_quality": 0.85
}
```

### Round 2: 자유 토론 (최대 2회 왕복)

**토론 규칙**:
1. Round 1의 3인 의견을 모두 공개
2. 의견 불일치(disagreement)가 있는 항목에 대해 토론
3. 각 전문가는 다른 전문가의 의견을 참고하여 재평가
4. 근거를 제시하며 의견을 변경하거나 유지
5. 최대 2회 왕복 (max_discussion_turns: 2)

**토론 형식**:

```
[파지 생물학자]: P043에서 XYZ-1 prophage 이름에 대해 flag했습니다.
이 이름은 원문에서 "putative prophage XYZ-1"로 언급되며 아직 공식 명명되지 않았습니다.
properties에 completeness: "questionable"을 추가하는 것을 제안합니다.

[미생물 유전체학자]: 동의합니다. 추가로 GenBank에 이 시퀀스 accession이 등록되어
있는지 확인이 필요합니다. 현재 sequence_id가 비어있습니다.

[비판적 검토자]: 동의합니다. 다만 원문에서 이 prophage를 "intact prophage region"으로
기술하고 있으므로, 완전히 제거보다는 수정이 더 적절합니다.
"recheck"으로 변경을 제안합니다.

[파지 생물학자]: 수정안에 동의합니다. verdict를 "flag_recheck"으로 합의합니다.
```

### Round 3: 합의 투표

각 전문가가 최종 판정:

```json
{
  "expert_id": "phage_biologist",
  "final_votes": {
    "P041": "accept",
    "P042": "accept",
    "P043": "flag_recheck",
    "P044": "flag_reextract",
    "P045": "accept"
  }
}
```

**합의 규칙**:
- 2/3 이상 동일 verdict → 해당 verdict로 확정
- 2/3 미달 → 다수결 채택 + 소수 의견 기록
- accept vs reject 대립 시 → flag_recheck으로 절충 (안전한 방향)

## 패널 운영 모드

### Full Panel (기본)

Round 1 → Round 2 → Round 3 순서로 전체 수행.
- 새로운 세션의 첫 실행
- 연속 실행의 처음 4회

### Quick Panel (5회 이상 연속)

Round 1만 수행하여 빠른 검증.
- 3인 중 심각한 flag(reject 또는 다수의 entity_flags)가 없으면 자동 승인
- 심각한 flag 발견 시 즉시 Full Panel로 복귀

**Quick Panel 전환 조건**:
- 연속 5회 이상 실행
- 이전 run들의 평균 panel_confidence ≥ 0.8
- 연속 2회 이상 reject 없음

### Skip Panel

사용자가 명시적으로 `--skip-panel` 지시 시.
- 패널 완전 생략, Phase 3의 추출 결과를 바로 Phase 5로 전달
- panel_confidence는 N/A로 기록

## 판정 후 처리

| Verdict | Action |
|---------|--------|
| accept | 그래프에 포함. extraction_status 유지 |
| flag_reextract | extraction_status를 "pending"으로 복원. 다음 Phase 3에서 재추출 |
| flag_recheck | 메인 에이전트가 해당 extraction을 직접 수정 후 validate_data로 재검증 |
| reject | extraction 파일 삭제. extraction_status를 "rejected"로 표시. 그래프에서 제외 |

## 패널 결과 JSON 형식

```json
{
  "run_id": "run_003",
  "panel_date": "2026-02-28T15:00:00Z",
  "panel_mode": "full",
  "consensus": {
    "accepted_papers": ["P041", "P042", "P045"],
    "flagged_papers": {
      "P043": {"reason": "Prophage 이름 불확실", "suggested_action": "recheck"},
      "P044": {"reason": "숙주 종 오류 가능", "suggested_action": "reextract"}
    },
    "rejected_papers": []
  },
  "schema_delta": {
    "add_entity_types": [],
    "modify_entity_types": [],
    "add_relationship_types": [],
    "notes": ["lysogenic conversion gene 분류를 세분화 권장"]
  },
  "panel_confidence": 0.85,
  "discussion_summary": "3인 모두 integrase/repressor 추출 품질에 동의...",
  "expert_reports": {
    "phage_biologist": {"overall_quality": 0.87, "flags_raised": 1},
    "microbial_genomicist": {"overall_quality": 0.83, "flags_raised": 2},
    "critical_reviewer": {"overall_quality": 0.82, "flags_raised": 2}
  }
}
```
