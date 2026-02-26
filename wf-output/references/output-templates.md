# Output Templates

## Directory Structure Template
When the skill runs for a workflow, create this structure:
```
./workflow-compositions/
├── {WF_ID}_{WF_NAME}/
│   ├── 00_metadata/
│   │   ├── workflow_context.json
│   │   ├── validation_report.json
│   │   └── execution_log.json
│   ├── 01_papers/
│   │   ├── paper_list.json
│   │   └── search_log.md
│   ├── 02_cases/
│   │   ├── case_C001.json ... case_C0XX.json
│   │   └── case_summary.json
│   ├── 03_analysis/
│   │   ├── step_alignment.json
│   │   ├── cluster_result.json
│   │   ├── common_pattern.json
│   │   └── parameter_ranges.json
│   ├── 04_workflow/
│   │   ├── uo_mapping.json
│   │   ├── variant_V1_*.json ... variant_VN_*.json
│   │   └── qc_checkpoints.json
│   ├── 05_visualization/
│   │   ├── workflow_graph_V1.mmd + .png
│   │   ├── workflow_graph_V2.mmd + .png
│   │   ├── variant_comparison.mmd + .png
│   │   └── case_cluster_heatmap.png
│   ├── 06_review/
│   │   └── peer_review.md
│   ├── composition_report.md        # Final human-readable report (English)
│   ├── composition_report_ko.md     # Final report (Korean)
│   ├── composition_data.json        # Final machine-readable JSON
│   ├── composition_workflow.md      # Workflow reference card (English)
│   └── composition_workflow_ko.md   # Workflow reference card (Korean)
└── index.json
```

## composition_report.md Template

```markdown
# {WF_ID}: {WF_NAME} — Workflow Composition Report

**Generated**: {date}
**Domain**: {domain_group}
**Papers analyzed**: {paper_count}
**Cases collected**: {case_count}
**Variants identified**: {variant_count}
**Total UOs**: {uo_count}
**QC Checkpoints**: {qc_count}
**Overall Confidence**: {confidence_score}

---

## 1. Workflow Overview
{workflow_description}

## 2. Literature Search Summary
- Databases searched: {databases}
- Papers analyzed: {papers_analyzed}
- Papers after screening: {screened_papers}
- Cases collected: {case_count}

## 3. Case Summary
### Distribution by Technique
| Technique | Cases | Papers |
|-----------|-------|--------|
| {technique} | {count} | {papers} |

### Distribution by Scale
...

### Distribution by Organism
...

## 4. Common Workflow Structure
{common_skeleton_description}

### Mandatory Steps
{mandatory_steps_table}

### Branch Points
{branch_points_description}

### QC Checkpoints
{qc_checkpoints_table}

## 5. Variants

### V1: {variant_name}
**Cases**: {case_ids}
**Defining features**: {features}

#### UO Sequence
{uo_sequence_table_with_7_components_summary}

#### UO Graph
![V1 Workflow Graph](05_visualization/workflow_graph_V1.png)

### V2: {variant_name}
...

## 6. Variant Comparison
![Variant Comparison](05_visualization/variant_comparison.png)

## 7. Parameter Ranges
{parameter_ranges_table}

## 8. Equipment & Software Inventory

### 8.1 Equipment Summary
| # | Equipment | Model | Manufacturer | Used In (UO) | Variants | Cases | Evidence |
|---|-----------|-------|--------------|--------------|----------|-------|----------|
| {n} | {name} | {model} | {manufacturer} | {uo_ids} | {variants} | {case_refs} | {evidence_tag} |

### 8.2 Software Summary
| # | Software | Version | Developer | License | Used In (UO) | Variants | Cases | Evidence |
|---|----------|---------|-----------|---------|--------------|----------|-------|----------|
| {n} | {name} | {version} | {developer} | {license} | {uo_ids} | {variants} | {case_refs} | {evidence_tag} |

### 8.3 Coverage Statistics
- Equipment detail level: {equipment_with_model}/{total_equipment} items have model info ({pct}%)
- Equipment manufacturer level: {equipment_with_manufacturer}/{total_equipment} items have manufacturer info ({pct}%)
- Software detail level: {software_with_version}/{total_software} items have version info ({pct}%)
- Software developer level: {software_with_developer}/{total_software} items have developer info ({pct}%)

## 9. Evidence and Confidence
| Component | literature-direct | literature-consensus | expert-inference | Total |
|-----------|------------------|---------------------|-----------------|-------|
| ... | ... | ... | ... | ... |

## 10. Modularity and Service Integration
This workflow is a modular building block designed for assembly into larger services/capabilities.

### Boundary Interface
| Direction | Connected Workflow | Transferred Material/Data |
|-----------|-------------------|--------------------------|
| **Input from** | {upstream_wf_id}: {upstream_wf_name} | {boundary_input_description} |
| **Output to** | {downstream_wf_id}: {downstream_wf_name} | {boundary_output_description} |

### Common Service Chains (from case evidence)
{service_chain_patterns_from_cases}

### Interoperability Notes
{notes_on_connecting_with_adjacent_workflows}

## 11. Limitations and Notes

### 11.1 Data Limitations
{numbered list of limitations regarding cases, coverage, bias}

### 11.2 Methodological Notes
{numbered list of notes about approach, assumptions, expert-inference items}

## 12. Catalog Feedback: Workflow & Unit Operation Improvement Suggestions

Based on this composition analysis, the following improvements to the WF/UO catalogs are suggested:

### 12.1 UO Catalog Issues
| # | Category | UO ID | Issue | Evidence | Suggested Action |
|---|----------|-------|-------|----------|-----------------|
| 1 | {missing/duplicate/inappropriate/mapping} | {UO_ID or "NEW"} | {description} | {case_refs} | {action} |

### 12.2 Workflow Catalog Issues
| # | Category | WF ID | Issue | Evidence | Suggested Action |
|---|----------|-------|-------|----------|-----------------|
| 1 | {missing/duplicate/inappropriate/boundary} | {WF_ID or "NEW"} | {description} | {case_refs} | {action} |

### 12.3 Component Coverage Gaps
| UO ID | Component | Gap Description | Affected Variants |
|-------|-----------|-----------------|-------------------|
| {uo_id} | {component_name} | {systematically missing info} | {variants} |

### 12.4 Summary
- Total findings: {count}
- Critical (blocking): {count}
- Improvement suggestions: {count}
- New UO proposals: {count}
- New WF proposals: {count}

## 13. Execution Metrics
- Total elapsed time: {total_elapsed_seconds}s
- Phase timings: [see execution_log.json]
```

## composition_data.json Template (Schema v4.0.0)
```json
{
  "schema_version": "4.0.0",
  "workflow_id": "{WF_ID}",
  "workflow_name": "{WF_NAME}",
  "category": "Build|Test",
  "domain": "{domain_group}",
  "version": 3.0,
  "composition_date": "YYYY-MM-DD",
  "description": "",
  "statistics": {
    "papers_analyzed": 0,
    "cases_collected": 0,
    "variants_identified": 0,
    "total_uos": 0,
    "qc_checkpoints": 0,
    "confidence_score": 0.0
  },
  "modularity": {
    "boundary_inputs": [
      {
        "name": "Designed fragment sequences",
        "type": "data|material",
        "typical_source_workflow": "WD070",
        "specifications": "",
        "case_refs": []
      }
    ],
    "boundary_outputs": [
      {
        "name": "Assembled circular plasmid",
        "type": "data|material",
        "typical_destination_workflow": "WB120",
        "specifications": "",
        "case_refs": []
      }
    ],
    "common_upstream_workflows": ["WD070"],
    "common_downstream_workflows": ["WB120", "WB040"],
    "service_chains_observed": [
      {
        "chain": ["WD070", "WB030", "WB120", "WT010", "WL010"],
        "description": "Vector design → Assembly → Transformation → Sequencing → Verification",
        "case_refs": []
      }
    ]
  },
  "common_skeleton": [],
  "variants": {
    "V1": {
      "name": "",
      "case_ids": [],
      "uo_sequence": [
        {
          "uo_id": "",
          "uo_name": "",
          "instance_label": "",
          "type": "hardware|software",
          "components": { "input": {}, "output": {} },
          "evidence_tag": "",
          "case_refs": []
        }
      ],
      "qc_checkpoints": []
    }
  },
  "parameter_ranges": {},
  "equipment_software_inventory": {
    "equipment": [
      {
        "name": "Thermal cycler",
        "model": "T100",
        "manufacturer": "Bio-Rad",
        "used_in_uos": ["UHW100a"],
        "variants": ["V1", "V2"],
        "case_refs": ["C001", "C004"],
        "evidence_tag": "literature-direct"
      }
    ],
    "software": [
      {
        "name": "fastp",
        "version": "0.23.x",
        "developer": "OpenGene",
        "license": "MIT",
        "source": "https://github.com/OpenGene/fastp",
        "used_in_uos": ["USW050"],
        "variants": ["V1"],
        "case_refs": ["C001", "C003"],
        "evidence_tag": "literature-direct"
      }
    ],
    "coverage": {
      "equipment_with_model": 0,
      "equipment_with_manufacturer": 0,
      "total_equipment": 0,
      "software_with_version": 0,
      "software_with_developer": 0,
      "total_software": 0
    }
  },
  "related_workflows": {
    "upstream": [],
    "downstream": []
  },
  "limitations": [
    {
      "category": "data|methodology|coverage",
      "description": "",
      "case_refs": []
    }
  ],
  "catalog_feedback": {
    "uo_issues": [
      {
        "category": "missing|duplicate|inappropriate|mapping",
        "uo_id": "",
        "description": "",
        "evidence": [],
        "suggested_action": ""
      }
    ],
    "wf_issues": [
      {
        "category": "missing|duplicate|inappropriate|boundary",
        "wf_id": "",
        "description": "",
        "evidence": [],
        "suggested_action": ""
      }
    ],
    "component_gaps": [
      {
        "uo_id": "",
        "component": "",
        "gap_description": "",
        "affected_variants": []
      }
    ],
    "summary": {
      "total_findings": 0,
      "critical": 0,
      "improvements": 0,
      "new_uo_proposals": 0,
      "new_wf_proposals": 0
    }
  },
  "confidence_score": 0.0
}
```

## index.json Template
```json
{
  "generated": "{ISO_date}",
  "total_workflows": 0,
  "completed": [],
  "in_progress": [],
  "workflows": {
    "{WF_ID}": {
      "name": "{WF_NAME}",
      "category": "Build|Test",
      "domain": "{domain_group}",
      "status": "completed|in_progress",
      "version": 3.0,
      "version_count": 1,
      "papers": 0,
      "cases": 0,
      "variants": 0,
      "uos": 0,
      "path": "./{WF_ID}_{WF_NAME}/",
      "last_updated": "{ISO_date}",
      "confidence": 0.0,
      "last_upgraded": "YYYY-MM-DD"
    }
  }
}
```

## composition_workflow.md Template

```markdown
# {WF_ID}: {WF_NAME} — Workflow Reference Card

**Version**: {date} | **Confidence**: {score} | **Variants**: {count}

## Common Workflow Skeleton

| Pos | Function | Mandatory | UO | Type |
|-----|----------|-----------|----|------|
| {n} | {function} | {Y/N} | {uo_id} | {HW/SW} |

## Variants

### V{n}: {name} ({case_count} cases)
**UO Sequence**: {uo_id1} → {uo_id2} → ... → {uo_idN}

| Step | UO ID | UO Name | Instance Label | Type | Key Equipment/Software | Key Parameters |
|------|-------|---------|----------------|------|------------------------|----------------|
| {n} | {uo_id} | {uo_name} | {label} | {HW/SW} | {equipment: model (manufacturer) or software: name vX.X (developer)} | {key params summary} |

**QC Checkpoints**:
- {qc_id}: {metric} — Pass: {criteria} | Fail: {action}

## Parameter Quick-Reference

| Parameter | Range | Unit | Variants | Cases |
|-----------|-------|------|----------|-------|
| {param} | {range} | {unit} | {variants} | {cases} |

## Boundary I/O

| Direction | Workflow | Material/Data |
|-----------|----------|---------------|
| IN ← | {upstream_wf} | {description} |
| OUT → | {downstream_wf} | {description} |

## Service Chains
{numbered list of observed chains with frequencies}
```

## composition_workflow_ko.md Template

Korean version uses same structure with translated headers:

| English | Korean |
|---------|--------|
| Workflow Reference Card | 워크플로 참조 카드 |
| Common Workflow Skeleton | 공통 워크플로 골격 |
| Variants | 변이체 |
| Parameter Quick-Reference | 파라미터 참조 |
| Boundary I/O | 경계 입출력 |
| Service Chains | 서비스 체인 |
| Function | 기능 |
| Mandatory | 필수 |
| Key Equipment/Software | 주요 장비/소프트웨어 |
| Key Parameters | 주요 파라미터 |
| QC Checkpoints | QC 체크포인트 |

Technical terms (UO IDs, WF IDs, parameters, numbers) remain untranslated.

## composition_report_ko.md Template

Korean version uses same section structure (1-13) with translated headers and content.

| Section | English | Korean |
|---------|---------|--------|
| 1 | Workflow Overview | 워크플로 개요 |
| 2 | Literature Search Summary | 문헌 검색 요약 |
| 3 | Case Summary | 케이스 요약 |
| 4 | Common Workflow Structure | 공통 워크플로 구조 |
| 5 | Variants | 변이체 |
| 6 | Variant Comparison | 변이체 비교 |
| 7 | Parameter Ranges | 파라미터 범위 |
| 8 | Equipment & Software Inventory | 장비 및 소프트웨어 목록 |
| 9 | Evidence and Confidence | 근거 및 신뢰도 |
| 10 | Modularity and Service Integration | 모듈성 및 서비스 통합 |
| 11 | Limitations and Notes | 한계점 및 참고사항 |
| 12 | Catalog Feedback | 카탈로그 피드백 |
| 13 | Execution Metrics | 실행 지표 |

Technical terms, UO IDs, case IDs, table data, and numbers remain untranslated.
Prose content (descriptions, notes, limitations) is translated to Korean.

## execution_log.json Template (phase_metrics section)

The `summary` object in `execution_log.json` includes a `phase_metrics` dict and `total_elapsed_seconds`:

```json
{
  "summary": {
    "phases_completed": [1, 2, 3, 4, 5],
    "phase_metrics": {
      "phase_1": {
        "started": "2026-02-08T10:00:00",
        "completed": "2026-02-08T10:01:30",
        "elapsed_seconds": 90.0
      },
      "phase_2": {
        "started": "2026-02-08T10:01:30",
        "completed": "2026-02-08T10:05:00",
        "elapsed_seconds": 210.0
      }
    },
    "total_elapsed_seconds": 3600.0,
    "errors": {}
  }
}
```
