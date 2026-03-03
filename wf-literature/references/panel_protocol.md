# Literature Quality Panel Protocol — Per-Paper Review

논문별 개별 리뷰를 통한 문헌 선별 프로토콜.
각 논문에 대해 3명 전문가가 독립 리뷰 → 토론 → 합의 투표를 수행하여 accept/reject를 판정한다.

## Panel Composition

| Expert | Role | Focus |
|--------|------|-------|
| 문헌 전문가 (Literature Specialist) | 메타데이터 정확성, ID 매핑 | PMID/DOI/PMCID 일관성, 저널 적합성 |
| 도메인 전문가 (Domain Expert) | 워크플로우 관련성, 프로토콜 적합성 | 프로토콜 상세도, 핵심 기술 커버리지 |
| 비판적 검토자 (Critical Reviewer) | 근거 수준, 방법론 품질 | 재현 가능성, 방법론 독창성 |

## Activation Conditions

- **ALWAYS**: Panel review is MANDATORY for every workflow composition run. No skip conditions.

## Review Protocol — Per Paper

각 논문(P001, P002, ...)에 대해 아래 3 라운드를 반복 수행한다.

### Round 1: Independent Review (독립 리뷰)

각 전문가가 해당 논문을 독립적으로 평가:

1. **문헌 전문가** 평가 항목:
   - PMID/DOI/PMCID 매핑 정확성
   - 제목-초록-본문 일치도
   - 저널의 워크플로우 도메인 적합성
   - 메타데이터 완전성 (연도, 저자, 저널 등)

2. **도메인 전문가** 평가 항목:
   - 대상 워크플로우와의 관련성 (직접 관련 / 부분 관련 / 무관)
   - 프로토콜 상세도 (케이스 추출 가능 수준인지)
   - 장비/시약 구체성
   - 핵심 기술 커버리지

3. **비판적 검토자** 평가 항목:
   - 근거 수준 (원저 연구 / 리뷰 / 프로토콜 논문)
   - 방법론 독창성 및 재현 가능성
   - 다른 논문과의 중복도

각 전문가는 논문별로 0.0~1.0 점수와 한국어 assessment를 생성한다.

### Round 2: Discussion (토론)

의견이 갈리는 논문에 대해 전문가 간 토론:
- 한 명이라도 reject를 제시한 논문에 대해 우선 토론
- 점수 편차가 0.3 이상인 논문에 대해 토론
- 도메인 전문가가 "부분 관련"으로 판정한 논문의 포함 여부 논의

토론 결과를 `discussion_summary`(한국어)로 기록한다.

### Round 3: Consensus Voting (합의 투표)

각 전문가가 논문별로 최종 투표:

| Verdict | Meaning | Action |
|---------|---------|--------|
| `accept` | 케이스 추출 대상으로 적합 | Phase 2.5 Case Extraction으로 진행 |
| `flag_recheck` | 보완 후 재평가 필요 | 메타데이터/본문 보완 후 재심 (max 1 retry) |
| `reject` | 케이스 추출 부적합 | 제외, 대체 논문 검색 권고 |

**Consensus rules (논문별):**
- 2/3 이상 accept → accept
- 2/3 이상 reject → reject
- 그 외 → flag_recheck

## 출력 언어

모든 `06_review/literature_panel.json` 텍스트 필드는 **한국어**로 작성:
- assessment, issues, discussion_summary, overall_summary, action_items
- JSON 키 이름은 영어 유지 (시스템 호환성)

이 규칙은 Analysis Panel (`variant_clustering_review.json`, `uo_mapping_review.json`, `qc_checkpoint_review.json`) 에도 동일 적용.

## Output Format

```json
{
  "workflow_id": "WB030",
  "panel_date": "2026-03-03",
  "panel_type": "per_paper_review",
  "language": "ko",
  "total_papers": 10,
  "accepted_count": 8,
  "rejected_count": 1,
  "flagged_count": 1,
  "paper_reviews": [
    {
      "paper_id": "P001",
      "title": "논문 제목",
      "reviews": {
        "literature_specialist": {
          "score": 0.85,
          "assessment": "메타데이터 정확하며 PMC 본문 확보됨. 저널 적합성 양호. (한국어)"
        },
        "domain_expert": {
          "score": 0.80,
          "assessment": "워크플로우 직접 관련. 프로토콜 상세도 높음. (한국어)"
        },
        "critical_reviewer": {
          "score": 0.78,
          "assessment": "원저 연구로 근거 수준 양호. 재현 가능성 확인됨. (한국어)"
        }
      },
      "discussion_summary": "전문가 간 이견 없음. 만장일치 accept. (한국어)",
      "verdict": "accept",
      "aggregate_score": 0.81
    }
  ],
  "overall_summary": "10편 중 8편 accept, 1편 reject, 1편 재검토. (한국어)",
  "action_items": ["P005 reject — 워크플로우 무관 논문으로 대체 검색 권고 (한국어)"]
}
```

## Integration with wf-literature

Panel review is Phase 2.4 in wf-literature SKILL.md (MANDATORY):
1. After Quality Evaluation (Phase 2.3) completes
2. Panel reviews each paper individually with per-paper verdict
3. `accepted_count` >= 3: proceed to Phase 2.5 (Case Extraction, accepted papers only)
4. `accepted_count` < 3: return to Phase 2.1 with modified queries
5. `flag_recheck` papers: fix metadata, re-validate, re-run panel for those papers only (max 1 retry)

**Output**: `06_review/literature_panel.json`
