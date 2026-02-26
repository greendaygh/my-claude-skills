---
skill: wf-literature
trigger: /wf-literature
description: >
  Collect and evaluate scientific literature for biofoundry workflow composition.
  Searches OpenAlex, fetches PubMed details, evaluates quality, and extracts case cards.
version: 2.0.0
author: SBLab KRIBB
tags: [biofoundry, literature, case-extraction, openalex, pubmed]
---

# WF-Literature v2.0 — Literature Collection

Collect scientific literature and extract structured case cards for a resolved workflow.

## Invocation

```
/wf-literature {wf_dir}
```

**Prerequisite**: `{wf_dir}/00_metadata/workflow_context.json` must exist (created by `/workflow-composer` Phase 1).

## Reference Files

| File | Purpose |
|------|---------|
| `references/case-collection-guide.md` | 6 extraction principles, case card structure |
| `assets/case_template.json` | Case card JSON template |

## Execution

### 2.1 Literature Search — Invoke `scientific-skills:openalex-database`

Search for 10-15 highly relevant papers. Build queries from workflow name + domain keywords from `workflow_context.json`.

```
Query examples for WB030 "DNA Assembly":
- "DNA assembly" AND ("Gibson" OR "Golden Gate" OR "restriction cloning")
- Filter: type=journal-article, open_access=true, from_publication_date=2018
```

- **Update mode**: If `{wf_dir}/01_papers/paper_list.json` exists, exclude papers already listed (match by DOI/PMID)
- Output: candidate list with DOIs, PMIDs, titles, abstracts → save `01_papers/paper_list.json`

### 2.2 Paper Details — Invoke `scientific-skills:pubmed-database`

For each paper with PMID, fetch structured abstract and MeSH terms via PubMed E-utilities.
- Save extracted details to `01_papers/full_texts/{paper_id}.txt`

### 2.3 Quality Evaluation — Invoke `scientific-skills:scholar-evaluation`

Evaluate papers on 3 criteria (0-1 scale):
- **Protocol Detail (PD)**: How detailed are the methods?
- **UO Coverage (UC)**: How many workflow steps are described?
- **Equipment Specificity (ES)**: Are equipment models named?

Composite = 0.4*PD + 0.4*UC + 0.2*ES. Threshold >= 0.4. Select top 8 papers.
- Output: `01_papers/paper_ranking.json`

### 2.4 Case Extraction

For each qualifying paper, create one case card per `references/case-collection-guide.md`:
- Follow the 6 extraction principles (source fidelity, exhaustive check, etc.)
- Use `assets/case_template.json` structure
- Save `02_cases/case_C001.json` through `case_C0XX.json`
- Save `02_cases/case_summary.json`
- **Update mode**: continue numbering from existing cases

## External Skill Dependencies

| Skill | Purpose | Step |
|-------|---------|------|
| `scientific-skills:openalex-database` | Structured scholarly search | 2.1 |
| `scientific-skills:pubmed-database` | PubMed abstract/details fetch | 2.2 |
| `scientific-skills:scholar-evaluation` | Paper quality scoring | 2.3 |

## Output Contract

```
{wf_dir}/
├── 01_papers/
│   ├── paper_list.json
│   ├── paper_ranking.json
│   └── full_texts/
└── 02_cases/
    ├── case_C001.json ... case_C0XX.json
    └── case_summary.json
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
