# 전문가 패널 프로토콜

## 개요

wf-paper-mining 스킬에서 사용하는 4개 전문가 패널의 실행 프로토콜을 정의한다.

## 공통 규칙

- 각 패널은 3인 이상의 전문가로 구성
- Full 모드: 3라운드 (독립 평가 → 자유 토론 → 최종 투표)
- Quick 모드: 1라운드 (합의 점수만)
- 모든 패널 결과는 JSON으로 기록 (audit trail)
- 언어: 한국어

---

## Panel A: UO 후보 검증

**실행 조건**: 워크플로의 첫 실행 시에만 (결과는 캐시)

**입력**: 워크플로 ID, UO 카탈로그, 도메인 정보

**라운드 1 - 독립 평가**:
각 전문가가 독립적으로 UO 후보 목록을 평가:
- UO 후보가 해당 워크플로에 적절한가?
- 누락된 UO가 있는가?
- 불필요한 UO가 포함되어 있는가?

**라운드 2 - 자유 토론**:
전문가 간 의견 차이를 논의하고 합의 도출

**라운드 3 - 최종 투표**:
- accept: UO 후보 목록 확정
- revise: 수정 필요 (구체적 수정 사항 명시)

**캐시**: 한 번 accept된 결과는 이후 run에서 재사용

---

## Panel B: 논문 관련성 평가

**실행 조건**: 매 run마다 실행. 현재 run의 `paper_list_{run_id}.json`의 논문만 평가

### 핵심 원칙: 관대한 수용

Panel B의 목적은 명백히 무관한 논문만 걸러내는 것이다. 부분적으로라도 관련 정보가 포함될 가능성이 있으면 **accept**한다.

**수용 기준**:
- 워크플로와 직접 관련된 실험이 포함 → accept
- 워크플로의 일부 UO와 관련된 내용이 포함 → accept
- 관련 장비, 시약, 프로토콜이 언급 → accept
- 해당 도메인의 자동화/high-throughput 내용 포함 → accept

**거부 기준**:
- 워크플로와 전혀 다른 분야 (예: 임상 시험만 다루는 논문이 DNA assembly 워크플로에 할당)
- 리뷰/메타분석으로 실험 상세가 전혀 없음
- 초록만으로 관련성 판단 불가하고 워크플로 키워드도 없음

**평가 기준** (전문가별):
- 도메인 적합성 (0-1점)
- 방법론 관련성 (0-1점)
- 정보 추출 가능성 (0-1점)

**임계값**: accept 합의 0.4 이상

**Verdicts**: `accept` / `reject`

**Verdict 처리**:
- accept → extraction_status 유지 ("pending"), full text 다운로드 진행
- reject → extraction_status를 "rejected"로 변경, full text 다운로드 스킵

---

## Panel C: 추출 검증

**실행 조건**: 매 run마다, 추출 완료된 논문에 대해 실행

**입력**: ExtractionResult JSON, 원본 논문 full text, UO/워크플로 카탈로그

**평가 항목**:
1. **정확성**: 추출된 UO, 장비, 시약이 논문 내용과 일치하는가?
2. **완전성**: 논문에 언급된 모든 관련 항목이 추출되었는가?
3. **카탈로그 매핑**: 기존 카탈로그와의 매핑이 올바른가?
4. **신규 후보**: is_new=true인 항목이 실제로 카탈로그에 없는 새로운 것인가?
5. **변종 감지**: 워크플로의 UO 구성이 기존과 다른 변종인가?

**Verdicts**: `accept` / `flag_reextract` / `reject`

**임계값**: accept 합의 0.6 이상

**Verdict 처리**:
- accept → 추출 결과 확정
- flag_reextract → 구체적 가이드와 함께 재추출
- reject → 추출 결과 폐기

---

## Panel D: 변종 검증

**실행 조건**: aggregate phase에서 실행

**입력**: VariantDefinition 목록, 워크플로 카탈로그, 전체 추출 결과

**평가 항목**:
1. 변종의 UO 구성이 논리적으로 타당한가?
2. 실제 실험에서 사용되는 방식인가?
3. 기존 카탈로그의 워크플로와 충분히 다른가?
4. 여러 논문에서 확인되는 패턴인가?

**Verdicts**: `accept` / `merge` / `reject`

**임계값**: accept 합의 0.6 이상

---

## Quick 모드에서 Full 복귀 조건

Quick 모드에서 다음 조건 발생 시 Full 모드로 전환:
- 전문가 간 점수 차이가 0.4 이상
- reject 비율이 30% 이상
- 합의 점수가 임계값 ±0.1 범위 내

---

## Audit Trail

모든 패널 실행 결과는 다음 형식으로 저장:

```json
{
  "run_id": 1,
  "panel_mode": "full",
  "input_prompt": {},
  "round_1_responses": {},
  "round_2_discussion": [],
  "round_3_votes": {},
  "final_verdicts": {},
  "timestamp": "2025-01-01T00:00:00Z"
}
```

파일 위치: `{wf_output_dir}/reviews/panel_{type}_run_{run_id}.json`
