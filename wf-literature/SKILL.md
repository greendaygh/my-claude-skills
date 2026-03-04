---
skill: wf-literature
trigger: /wf-literature
description: >
  Collect and evaluate scientific literature for biofoundry workflow composition.
  Searches OpenAlex, fetches PMC full text via Python scripts, validates data
  integrity with Pydantic, evaluates quality, and extracts case cards.
version: 3.1.0
author: SBLab KRIBB
tags: [biofoundry, literature, case-extraction, openalex, pubmed, pmc, validation]
---

# WF-Literature v3.0 — Literature Collection

Collect scientific literature and extract structured case cards for a resolved workflow.

v3.0 upgrade: Script-based full text acquisition (PMC/Europe PMC API) and
Pydantic validation replace external skill dependencies for paper details.

## Invocation

```
/wf-literature {wf_dir}
```

**Prerequisite**: `{wf_dir}/00_metadata/workflow_context.json` must exist (created by `/workflow-composer` Phase 1).

## Reference Files

| File | Purpose |
|------|---------|
| `references/case-collection-guide.md` | 6 extraction principles, case card structure |
| `references/panel_protocol.md` | Per-paper expert panel review protocol (mandatory) |
| `assets/case_template.json` | Case card JSON template |
| `assets/literature_panel_config.json` | 3-expert panel configuration |
| `scripts/fetch_fulltext.py` | PMC/Europe PMC full text download |
| `scripts/validate_papers.py` | Pydantic validation + content cross-checking |
| `scripts/repair_paper_metadata.py` | Abstract-title mismatch repair via DOI re-resolution |
| `scripts/cleanup_abstract_fulltexts.py` | Remove abstract-only P*.txt files |
| `scripts/batch_repair.py` | Batch repair pipeline (metadata→cleanup→fetch→validate) |
| `scripts/collect_case.py` | Case card creation and validation |

## Execution

### 2.1 Literature Search — Invoke `scientific-skills:openalex-database`

Search for 10-15 highly relevant papers. Build queries from `workflow_context.json` fields in priority order:

1. **`search_terms`** (if non-empty): use directly as primary query terms
2. **`workflow_name`** + **`domain_keywords`**: combine for secondary/fallback queries
3. **`search_config.json` technique_templates** (if workflow ID exists): use keywords + synonyms

```
Query examples for WB030 "DNA Assembly":
- "DNA assembly" AND ("Gibson" OR "Golden Gate" OR "restriction cloning")
- Filter: type=journal-article, open_access=true, from_publication_date=2018
```

- **Update mode**: If `{wf_dir}/01_papers/paper_list.json` exists, exclude papers already listed (match by DOI/PMID)
- Output: candidate list with DOIs, PMIDs, PMCIDs, titles, abstracts → save `01_papers/paper_list.json`
- **Important**: Ensure PMCID is included for each paper (required for full text fetch)

### 2.2 Full Text Acquisition — Run `scripts/fetch_fulltext.py`

Fetch structured full text from PMC Open Access for all papers with PMCID.

```bash
python3 ~/.claude/skills/wf-literature/scripts/fetch_fulltext.py \
  --input {wf_dir}/01_papers/paper_list.json \
  --output {wf_dir}
```

How it works:
1. Reads `paper_list.json` and processes papers with PMCID that lack `has_full_text=True`
2. Downloads PMC XML via NCBI efetch API (with Europe PMC fallback)
3. Parses XML into structured sections: ABSTRACT, INTRODUCTION, METHODS, RESULTS, DISCUSSION
4. Saves each paper as `01_papers/full_texts/{paper_id}.txt` with `=== SECTION ===` headers
5. Updates `has_full_text` and `text_source` fields in `paper_list.json`

Features:
- Incremental processing (skips already-fetched papers)
- NCBI API key support (`NCBI_API_KEY` env var)
- Adaptive retry with circuit breaker on consecutive failures
- Europe PMC batch limit compliance (max 50 per run)

**MANDATORY — Full Text File Verification**:

After `fetch_fulltext.py` completes, verify that actual `.txt` files exist on disk for every paper with a non-empty PMCID. Do NOT rely solely on the `has_full_text` flag in `paper_list.json`.

```python
import json, os
with open(f"{wf_dir}/01_papers/paper_list.json") as f:
    papers = json.load(f)["papers"]
pmcid_papers = [p for p in papers if p.get("pmcid", "").strip()]
missing = [p["paper_id"] for p in pmcid_papers
           if not os.path.exists(f"{wf_dir}/01_papers/full_texts/{p['paper_id']}.txt")]
assert len(missing) == 0, f"Full text files missing for: {missing}. Re-run fetch_fulltext.py."
```

If assertion fails: re-run `fetch_fulltext.py`, then re-verify. Max 2 retries.

### 2.2.1 Data Validation — Run `scripts/validate_papers.py`

Validate paper metadata integrity and full text consistency.

```bash
python3 ~/.claude/skills/wf-literature/scripts/validate_papers.py \
  --paper-list {wf_dir}/01_papers/paper_list.json \
  --full-texts {wf_dir}/01_papers/full_texts/ \
  --check-pmid
```

Checks performed:
- **Schema validation**: Pydantic v2 model conformance (paper_id, title, DOI format)
- **Abstract-title cross-validation**: Keyword cosine similarity (critical if < 0.05)
- **Full text-title matching**: First 2000 chars vs title keywords (critical if < 0.05)
- **PMID cross-validation** (optional): Fetches PubMed title, compares with paper_list title
- **Duplicate DOI detection**: Flags papers sharing the same DOI

Severity levels:
- `critical`: Auto-reject. Remove or replace the paper before proceeding.
- `warning`: Proceed with caution. Log for post-collection review (wf-audit).

**Gate rules** (ALL must pass to proceed):
1. `validate_papers.py` reports 0 critical issues (abstract-title and fulltext mismatches)
2. Full text files with `=== SECTION ===` headers have average size >= 500 bytes
3. No single-line P*.txt files exist in `full_texts/` (abstract-only contamination)

If gate fails:
- Critical abstract-title issues → run `repair_paper_metadata.py`, then re-validate
- Abstract-only files → run `cleanup_abstract_fulltexts.py --backup`, then re-fetch
- If still failing → remove problematic papers and search for replacements (return to 2.1)

### 2.3 Quality Evaluation — Invoke `scientific-skills:scholar-evaluation`

Evaluate papers on 3 criteria (0-1 scale):
- **Protocol Detail (PD)**: How detailed are the methods?
- **UO Coverage (UC)**: How many workflow steps are described?
- **Equipment Specificity (ES)**: Are equipment models named?

Composite = 0.4*PD + 0.4*UC + 0.2*ES. Threshold >= 0.4. Select top 8 papers.
- Output: `01_papers/paper_ranking.json`

### 2.4 Per-Paper Expert Panel Review — MANDATORY

3명 전문가가 **각 논문을 개별 리뷰**하여 accept/reject를 판정한다. accept된 논문만 케이스 추출(2.5)로 진행.
See `references/panel_protocol.md`.

**Panel composition** (3명, see `assets/literature_panel_config.json`):
- **문헌 전문가 (Literature Specialist)**: PMID/DOI/PMCID 매핑 정확성, 메타데이터 완전성, 저널 적합성
- **도메인 전문가 (Domain Expert)**: 워크플로우 관련성, 프로토콜 상세도, 핵심 기술 커버리지
- **비판적 검토자 (Critical Reviewer)**: 근거 수준, 방법론 독창성, 재현 가능성

**Protocol**: 논문마다 3-round process (독립 리뷰 → 쟁점 토론 → 합의 투표).

**논문별 verdict**: `accept` | `flag_recheck` | `reject`
- `accept`: 케이스 추출 대상
- `flag_recheck`: 메타데이터 보완 후 재평가 (max 1 retry)
- `reject`: 케이스 추출 제외, 대체 논문 검색 권고

**출력 언어**: 한국어 (assessment, issues, discussion_summary 모두 한국어. JSON 키는 영어 유지)

**Output**: `06_review/literature_panel.json`

```json
{
  "workflow_id": "WB005",
  "panel_date": "2026-03-03",
  "panel_type": "per_paper_review",
  "language": "ko",
  "total_papers": 9,
  "accepted_count": 7,
  "rejected_count": 1,
  "flagged_count": 1,
  "paper_reviews": [
    {
      "paper_id": "P001",
      "title": "...",
      "reviews": {
        "literature_specialist": { "score": 0.85, "assessment": "...(한국어)" },
        "domain_expert": { "score": 0.80, "assessment": "...(한국어)" },
        "critical_reviewer": { "score": 0.78, "assessment": "...(한국어)" }
      },
      "discussion_summary": "토론 요약 (한국어)",
      "verdict": "accept",
      "aggregate_score": 0.81
    }
  ],
  "overall_summary": "전체 논문 선별 결과 요약 (한국어)",
  "action_items": ["reject된 논문 대체 검색 권고 등"]
}
```

**Gate**: `accepted_count` >= 3. If not met, return to 2.1 with modified queries.

**MANDATORY — Literature Panel Schema Verification**:

```python
import json
with open(f"{wf_dir}/06_review/literature_panel.json") as f:
    panel = json.load(f)
assert panel.get("panel_type") == "per_paper_review", "panel_type must be 'per_paper_review'"
assert "paper_reviews" in panel, "paper_reviews array missing"
for pr in panel["paper_reviews"]:
    assert "reviews" in pr, f"Paper {pr.get('paper_id')}: reviews dict missing"
    for role in ["literature_specialist", "domain_expert", "critical_reviewer"]:
        assert role in pr["reviews"], f"Paper {pr.get('paper_id')}: {role} review missing"
    assert pr.get("verdict") in ("accept", "flag_recheck", "reject"), "Invalid verdict"
```

If assertion fails: regenerate `literature_panel.json` following the per-paper 3-expert schema above. Max 2 retries.

### 2.5 Case Extraction

For each **accepted** paper (verdict = `accept` in `literature_panel.json`), create one case card per `references/case-collection-guide.md`:
- Follow the 6 extraction principles (source fidelity, exhaustive check, etc.)
- Use `assets/case_template.json` structure
- Save `02_cases/case_C001.json` through `case_C0XX.json`
- Save `02_cases/case_summary.json`
- **Update mode**: continue numbering from existing cases

### 2.6 Pydantic Gate 2 — MANDATORY

Validate all Phase 2 outputs before proceeding. Uses `wf-audit/scripts/models/` canonical models.

```python
from wf_audit.scripts.models.paper_list import PaperList
from wf_audit.scripts.models.case_card import CaseCard
from wf_audit.scripts.models.case_summary import CaseSummary
import json, glob

errors = []
# paper_list.json
with open(f"{wf_dir}/01_papers/paper_list.json") as f:
    try: PaperList.model_validate(json.load(f))
    except Exception as e: errors.append(("paper_list.json", str(e)))

# case_C*.json
for fp in glob.glob(f"{wf_dir}/02_cases/case_C*.json"):
    with open(fp) as f:
        try: CaseCard.model_validate(json.load(f))
        except Exception as e: errors.append((fp, str(e)))

# case_summary.json
with open(f"{wf_dir}/02_cases/case_summary.json") as f:
    try: CaseSummary.model_validate(json.load(f))
    except Exception as e: errors.append(("case_summary.json", str(e)))
```

**Pass**: 0 ValidationError. **Fail**: fix using error hints, re-validate (max 2 retries).

## External Skill Dependencies

| Skill | Purpose | Step |
|-------|---------|------|
| `scientific-skills:openalex-database` | Structured scholarly search | 2.1 |
| `scientific-skills:scholar-evaluation` | Paper quality scoring | 2.3 |

**Removed dependency**: `scientific-skills:pubmed-database` is replaced by `scripts/fetch_fulltext.py` (direct PMC API access).

## Output Contract

```
{wf_dir}/
├── 01_papers/
│   ├── paper_list.json
│   ├── paper_ranking.json
│   └── full_texts/
│       ├── P001.txt      (structured: === ABSTRACT === ... === METHODS === ...)
│       ├── P002.txt
│       └── ...
├── 02_cases/
│   ├── case_C001.json ... case_C0XX.json
│   └── case_summary.json
└── 06_review/
    └── literature_panel.json
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
