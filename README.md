# my-claude-skills

SBLab KRIBB의 Claude Code 커스텀 스킬 모음.
바이오파운드리 워크플로 구성, 과학 문헌 분석, 스킬 자동 생성 등을 지원합니다.

**Version**: 1.12.0

---

## Skills Overview

### Workflow Composer Pipeline

바이오파운드리 워크플로를 5-Phase 파이프라인으로 구성하는 스킬 세트입니다.

```
workflow-composer (Orchestrator v2.4)
    ├── Phase 1: Resolve       ─ 워크플로 식별, 디렉토리 생성
    ├── Phase 2: wf-literature ─ 논문 검색, 케이스 추출
    ├── Phase 3+4: wf-analysis ─ 비교 분석, UO 매핑, 7-Component 구성
    └── Phase 5: wf-output     ─ 리포트, 시각화, 한국어 번역
```

| Skill | Version | Description |
|-------|---------|-------------|
| **workflow-composer** | 2.6.0 | 5-Phase 오케스트레이터. Pydantic gate 각 Phase, fresh 모드 전체 디렉토리 이동, full text 검증 통합 |
| **wf-literature** | 3.1.0 | OpenAlex 검색, PMC full text 스크립트 기반 취득, Pydantic 검증, 3인 전문가 패널 리뷰, 배치 복구 파이프라인 |
| **wf-analysis** | 2.2.0 | Step Alignment, 변형 클러스터링, 3인 Analysis Panel (자체 수행), Pydantic Gate 3, lenient canonical 모델 |
| **wf-output** | 2.4.0 | 13섹션 리포트, Full Validation Gate 4 (3단계: 스크립트+감사+시각화 구조), Mermaid 8-criteria 검증 |
| **wf-audit** | 2.4.0 | 15-step 감사 (content validation 추가), lenient canonical 모델 (legacy 필드 호환), abstract-title mismatch 탐지 |
| **wf-migrate** | 2.6.0 | PMID cross-validation 후 merge, full text policy (abstract fallback 금지), 구조화된 섹션 파싱 |

### Paper Mining

| Skill | Version | Description |
|-------|---------|-------------|
| **wf-paper-mining** | 1.0.3 | PubMed/OpenAlex 논문 검색, PMC full text 추출, 4-패널 전문가 검증, 7-Component UO 기반 리소스 추출. Thin Controller + RunManifest 아키텍처, 워크플로별 키워드 캐시, 순차 실행 전용 |

### Science & Analysis Skills

| Skill | Description |
|-------|-------------|
| **rna-seq-analysis** | Bulk RNA-seq 분석 파이프라인 (pydeseq2, scanpy 기반) |
| **mutation-kinetics-miner** | 논문에서 단백질 변이-동역학 관계 자동 추출 |
| **literature-knowledge-graph** | 문헌 기반 지식 그래프 구축 |
| **prophage-miner** | PubMed 논문 자동 검색, PMC full text 추출, 3인 전문가 패널 합의, knowledge graph 구축 |
| **debate** | 낙관주의자 vs 비관주의자 에이전트 토론 (한국어) |

### Meta Skills

| Skill | Version | Description |
|-------|---------|-------------|
| **skill-learn** | — | 멀티 에이전트 협업으로 새 스킬 자동 생성 |
| **skill-evolve** | 2.2.0 | 전문가 패널 분석을 통한 기존 스킬 품질 개선 |

---

## Architecture

### Workflow Composer Pipeline

5단계 파이프라인으로 ~64개 표준 워크플로, ~80개 Unit Operation을 구성합니다.

| Phase | Skill | Input | Output | 핵심 동작 |
|-------|-------|-------|--------|-----------|
| 1. Resolve | workflow-composer | 사용자 입력 (ID/이름) | `workflow_context.json`, 디렉토리 구조 | 카탈로그 조회, 모드 감지, 도메인 분류 |
| 2. Literature | wf-literature | `workflow_context.json` | `paper_list.json`, `case_C*.json`, `full_texts/` | OpenAlex 검색, PMC full text 취득, 검증, 케이스 추출 |
| 3. Analyze | wf-analysis | `case_C*.json` | `step_alignment.json`, `uo_mapping.json`, `variant_V*.json` | Step Alignment, UO 매핑, 변형 도출, 7-Component |
| 4. Compose | wf-analysis | `uo_mapping.json` | `variant_V*.json`, `qc_checkpoints.json` | 7-Component 채우기, Gap-Fill |
| 5. Output | wf-output | `variant_V*.json` | `composition_report.md`, `composition_data.json`, `*.mmd` | 13섹션 리포트, Mermaid 시각화, 한국어 번역 |

### Key Concepts

- **Case-First Approach**: 논문 → 케이스 → 비교 분석 → 공통 패턴 → UO 매핑
- **Unit Operation (UO)**: HW(UHW) / SW(USW) 두 유형, 각 7-Component 구조
- **Evidence Tagging**: 6단계 신뢰도 (literature-direct → catalog-default)
- **Schema v4.0.0**: `composition_data.json` 표준 포맷
- **DOI Validation**: 공유 모듈(`doi_validator.py`)로 4단계 검증

### Shared Modules

| Module | Location | Used By |
|--------|----------|---------|
| `doi_validator.py` | `wf-audit/scripts/` | wf-audit, wf-migrate, wf-output, wf-literature |

---

## Usage

```bash
# 단일 워크플로 구성
/workflow-composer WB030

# 기존 데이터 위에 업데이트
/workflow-composer WB030          # 자동으로 Update 모드

# 처음부터 새로 구성
/workflow-composer WB030 --fresh

# 배치 처리 (deep-executor 모드)
/workflow-composer WB* --fresh --deep

# 개별 스킬 재실행
/wf-literature {wf_dir}
/wf-analysis {wf_dir}
/wf-output {wf_dir}

# 전체 감사
/wf-audit

# 워크플로 논문 마이닝 (개별/전체)
/wf-paper-mining WB030
/wf-paper-mining --all
```

---

## Directory Structure

```
my-claude-skills/
├── workflow-composer/     # Orchestrator (Phase 1 + delegation)
│   ├── SKILL.md
│   ├── scripts/          # resolve_workflow.py, simple_logger.py
│   ├── assets/           # workflow_catalog.json, uo_catalog.json, domain_classification.json
│   └── references/       # deep-executor-guide.md
├── wf-literature/        # Phase 2: Literature Collection
│   ├── SKILL.md
│   ├── scripts/          # collect_case.py, fetch_fulltext.py, validate_papers.py, repair_paper_metadata.py, cleanup_abstract_fulltexts.py, batch_repair.py
│   ├── assets/           # case_template.json, literature_panel_config.json
│   └── references/       # case-collection-guide.md, panel_protocol.md
├── wf-analysis/          # Phase 3+4: Analysis & Composition
│   ├── SKILL.md
│   └── references/       # case-analysis-guide.md, unit-operation-mapping.md, hw/sw-component-guide.md
├── wf-output/            # Phase 5: Reports & Visualization
│   ├── SKILL.md
│   ├── scripts/          # validate.py
│   └── references/       # visualization-guide.md, output-templates.md
├── wf-audit/             # Post-hoc Audit
│   ├── SKILL.md
│   ├── CHANGELOG.md
│   └── scripts/          # doi_validator.py, referential_integrity.py, models/
├── wf-migrate/           # Legacy Migration
│   ├── SKILL.md
│   ├── CHANGELOG.md
│   └── scripts/          # workflow_migrator.py, case_migrator.py, audit_fixer.py, variant_migrator.py
├── wf-paper-mining/         # Workflow Paper Mining & Resource Extraction
│   ├── SKILL.md
│   ├── CHANGELOG.md
│   ├── scripts/          # search_papers.py, fetch_fulltext.py, run_tracker.py, plan_run.py, validate_outputs.py, ...
│   │   └── models/       # Pydantic v2 models (paper_list, state, extraction, summary, variant, ...)
│   ├── assets/           # extraction_config.json, panel_configs.json, workflow_catalog.json, uo_catalog.json, wf_search_keywords.json
│   └── references/       # extraction_guide.md, panel_protocol.md
├── prophage-miner/          # Prophage Literature Mining & Knowledge Graph
│   ├── SKILL.md
│   ├── CHANGELOG.md
│   ├── scripts/          # search_papers.py, fetch_fulltext.py, build_graph.py, generate_report.py
│   ├── assets/           # prophage_schema.json, panel_config.json
│   └── references/       # extraction_prompts.md, prophage_biology.md, panel_protocol.md
├── rna-seq-analysis/
├── mutation-kinetics-miner/
├── literature-knowledge-graph/
├── debate/
├── skill-learn/
├── skill-evolve/
└── README.md
```

---

*SBLab KRIBB — 2026*
