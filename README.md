# my-claude-skills

SBLab KRIBB의 Claude Code 커스텀 스킬 모음.
바이오파운드리 워크플로 구성, 과학 문헌 분석, 스킬 자동 생성 등을 지원합니다.

**Version**: 1.3.0

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
| **workflow-composer** | 2.4.0 | 5-Phase 오케스트레이터. 카탈로그 조회, 모드 감지(New/Update/Fresh), 서브스킬 위임 |
| **wf-literature** | 2.0.0 | OpenAlex/PubMed 논문 검색, 품질 평가(PD+UC+ES), 7대 원칙 기반 케이스 카드 추출 |
| **wf-analysis** | 2.0.0 | Step Alignment, 변형 클러스터링, Multi-signal UO 매핑, QC 체크포인트 설계, 7-Component 구조 |
| **wf-output** | 2.1.0 | Schema v4.0.0 JSON, 13섹션 리포트, Mermaid 시각화, Validation Gate, 한국어 번역 |
| **wf-audit** | 2.1.0 | Pydantic v2 기반 40개 워크플로 일괄 감사. 14-step verbose 진행률, chunked 배치, 13 파일 타입 검증 |
| **wf-migrate** | 2.2.0 | 레거시 마이그레이션 + audit-driven targeted fix. variant/composition_data 변환, fix_status 추적 |

### Science & Analysis Skills

| Skill | Description |
|-------|-------------|
| **rna-seq-analysis** | Bulk RNA-seq 분석 파이프라인 (pydeseq2, scanpy 기반) |
| **mutation-kinetics-miner** | 논문에서 단백질 변이-동역학 관계 자동 추출 |
| **literature-knowledge-graph** | 문헌 기반 지식 그래프 구축 |
| **debate** | 낙관주의자 vs 비관주의자 에이전트 토론 (한국어) |

### Meta Skills

| Skill | Version | Description |
|-------|---------|-------------|
| **skill-learn** | — | 멀티 에이전트 협업으로 새 스킬 자동 생성 |
| **skill-evolve** | 2.2.0 | 전문가 패널 분석을 통한 기존 스킬 품질 개선 |

---

## Architecture

### Workflow Composer Pipeline

5단계 파이프라인으로 ~37개 표준 워크플로, ~80개 Unit Operation을 구성합니다.

| Phase | Skill | Input | Output | 핵심 동작 |
|-------|-------|-------|--------|-----------|
| 1. Resolve | workflow-composer | 사용자 입력 (ID/이름) | `workflow_context.json`, 디렉토리 구조 | 카탈로그 조회, 모드 감지, 도메인 분류 |
| 2. Literature | wf-literature | `workflow_context.json` | `paper_list.json`, `case_C*.json` | OpenAlex 검색, PubMed fetch, 케이스 추출 |
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
│   ├── scripts/          # collect_case.py
│   ├── assets/           # case_template.json
│   └── references/       # case-collection-guide.md
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
