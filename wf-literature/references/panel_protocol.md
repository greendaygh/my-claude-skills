# Literature Quality Panel Protocol

Expert panel review protocol for workflow literature quality assurance.
Adapted from prophage-miner's panel_protocol.md for literature validation context.

## Panel Composition

| Expert | Role | Focus |
|--------|------|-------|
| Literature Specialist | Metadata accuracy, ID mapping | High strictness |
| Domain Expert | Workflow relevance, protocol fitness | Medium strictness |
| Critical Reviewer | Collection bias, evidence level, gaps | High strictness |

## Activation Conditions

- **ALWAYS**: Panel review is MANDATORY for every workflow composition run. No skip conditions.

## Review Protocol

### Round 1: Independent Review

Each expert independently reviews the paper collection:

1. **Literature Specialist** reviews:
   - All PMID/DOI/PMCID mappings for consistency
   - Title-abstract-fulltext alignment
   - Journal appropriateness for the workflow domain
   - Metadata completeness

2. **Domain Expert** reviews:
   - Each paper's relevance to the target workflow
   - Protocol detail level for case extraction viability
   - Equipment/reagent specificity
   - Coverage of key techniques in the workflow domain

3. **Critical Reviewer** reviews:
   - Overall collection balance (geographic, temporal, methodological)
   - Evidence level distribution
   - Presence of landmark/seminal papers
   - Potential gaps in coverage

Each expert produces a structured review per `review_template` in panel_config.json.

### Round 2: Discussion

Experts share their independent reviews and discuss:
- Disagreements on specific papers
- Papers flagged by any expert
- Gaps identified by the Critical Reviewer
- Domain relevance concerns from Domain Expert

### Round 3: Consensus Voting

Each expert votes on the overall collection:

| Verdict | Meaning | Action |
|---------|---------|--------|
| `accept` | Collection is suitable for case extraction | Proceed to Phase 2.4 |
| `flag_recheck` | Issues found but fixable | Re-download flagged papers, re-run validation |
| `reject` | Fundamental problems in collection | Return to Phase 2.1 (new search) |

**Consensus rules:**
- 2/3 majority for `accept` or `flag_recheck`
- `reject` requires unanimous vote OR 2/3 with Critical Reviewer agreeing
- Tie: defaults to `flag_recheck`

## Mode Switching

### Full Panel Mode (default)
- All 3 experts participate in all 3 rounds
- Used for first 5 workflows in a batch run

### Quick Panel Mode
- Only Critical Reviewer reviews
- Single-round verdict
- Activated after 5 successful Full Panel reviews with avg confidence >= 0.8
- Reverts to Full Panel on any `reject` or severe `flag_recheck`

## 출력 언어

모든 `06_review/` 리뷰 파일의 텍스트 필드는 **한국어**로 작성:
- assessment, issues, recommendations, discussion_notes, discussion_summary
- independent_review, conditions
- JSON 키 이름은 영어 유지 (시스템 호환성)

이 규칙은 Literature Panel (`literature_panel.json`)과 Analysis Panel (`variant_clustering_review.json`, `uo_mapping_review.json`, `qc_checkpoint_review.json`) 모두에 적용.

## Output Format

```json
{
  "panel_mode": "full|quick",
  "workflow_id": "WB030",
  "language": "ko",
  "reviews": {
    "literature_specialist": { "assessment": "평가 내용 (한국어)", "issues": ["이슈 (한국어)"] },
    "domain_expert": { "assessment": "...", "paper_relevance": { "P001": "관련성 판정 (한국어)" } },
    "critical_reviewer": { "assessment": "...", "issues": ["..."] }
  },
  "discussion_summary": "3명 전문가 토론 요약 (한국어)",
  "consensus": {
    "verdict": "accept|flag_recheck|reject",
    "conditions": ["조건 (한국어)"],
    "recommendations": ["권고 (한국어)"]
  },
  "confidence": 0.85,
  "flagged_papers": ["P003", "P007"]
}
```

## Integration with wf-literature

Panel review is Phase 2.6 in wf-literature SKILL.md (MANDATORY):
1. After Pydantic Gate 2 (Phase 2.5) passes
2. Panel reviews the full collection
3. If `accept`: proceed to Phase 3+4 (Analysis)
4. If `flag_recheck`: fix flagged papers, re-validate, re-run panel (max 1 retry)
5. If `reject`: return to literature search with modified queries

**Output**: `06_review/literature_panel.json`
