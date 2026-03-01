# Extraction Prompt Templates

## 검색 키워드 (Search Keywords)

```
"prophage identification" OR "prophage induction" OR "lysogeny decision"
OR "prophage genomics" OR "temperate bacteriophage integration"
OR "prophage-host interaction" OR "prophage gene expression"
```

## 서브에이전트 추출 프롬프트

### 메인 추출 프롬프트

서브에이전트가 full text에서 엔티티/관계를 추출할 때 사용하는 프롬프트 구조:

```
You are a prophage biology expert extracting structured data from a research paper.

## Task
Read the paper text below and extract ALL prophage-related entities and their
relationships according to the provided schema.

## Schema
Read ~/dev/phage/00_config/schema.json for the full list of:
- Entity types (8): Prophage, Gene, Protein, Host, IntegrationSite, Receptor, InductionCondition, Paper
- Relationship types (10): ENCODES, TRANSLATES_TO, INTEGRATES_INTO, INFECTS, BINDS, REPRESSES, INDUCES, HOMOLOGOUS_TO, LYSIS_COMPONENT, EXTRACTED_FROM

## Extraction Rules

1. **Entity identification**: For each entity, provide:
   - label: one of the 8 entity types
   - properties: fill all relevant properties from the schema definition

2. **Relationship identification**: For each relationship, provide:
   - type: one of the 10 relationship types
   - from/to: reference to extracted entities by label + key (primary key value)
   - properties: include "confidence", "source_section", and "evidence" (verbatim text)

3. **Section-based confidence weighting**:
   - Results section: confidence 0.9 (direct experimental evidence)
   - Methods section: confidence 0.85 (confirmed by methodology)
   - Abstract: confidence 0.85 (summarized finding)
   - Introduction: confidence 0.7 (may be citing other work)
   - Discussion: confidence 0.6 (may be speculative)
   - Abstract-only papers: apply -0.2 penalty to all confidence scores

4. **Evidence text**: Include a brief quote (1-2 sentences) from the paper
   that supports each extracted entity or relationship.

5. **Unschemaed findings**: If you find important prophage-related information
   that doesn't fit the schema, add it to the "unschemaed" list.

## Output Format
Save as JSON matching the PaperExtraction model:
{
  "paper_id": "{paper_id}",
  "paper_doi": "...",
  "entities": [...],
  "relationships": [...],
  "unschemaed": [...]
}

## Paper Text
{full_text_content}
```

### 섹션별 추출 가이드라인

#### Results 섹션 (confidence: 0.9)
- 실험적으로 확인된 prophage 이름, 크기, 완전성
- 동정된 유전자와 그 기능
- 숙주 감염 실험 결과
- 유도 실험 결과와 효율

#### Methods 섹션 (confidence: 0.85)
- 사용된 prophage 탐지 도구 (참고용, 엔티티 아님)
- 실험에 사용된 균주 정보 → Host 엔티티
- 시퀀스 ID (GenBank accession) → Gene/Protein properties

#### Abstract (confidence: 0.85)
- 주요 발견 요약
- 결론적 관계 (단, Introduction과 겹치면 Results 기반 우선)

#### Introduction (confidence: 0.7)
- 다른 논문의 결과를 인용하는 경우가 많음
- 인용된 prophage/유전자는 추출하되 confidence 하향

#### Discussion (confidence: 0.6)
- 추론/추측이 포함될 수 있음
- "may", "could", "suggests" 등 조건적 표현이 있으면 confidence -0.1 추가 페널티

### 엔티티 추출 세부 지침

#### Prophage
- 이름이 명시적이면 사용 (예: "DLP12", "Gifsy-1", "CTXφ")
- 이름이 없으면 "Prophage_[숙주종]_[통합부위]" 형식으로 명명
- completeness는 논문에서 직접 언급하거나 크기/유전자 보존 정도로 판단

#### Gene
- 정식 유전자 이름 또는 약어 사용
- category 분류: structural, regulatory, lysis, integration, replication
- sequence_id는 GenBank/RefSeq accession이 있으면 포함

#### Protein
- UniProt ID가 논문에 있으면 반드시 포함
- PDB structure ID가 있으면 포함
- domain 정보 (예: "lysozyme domain", "HTH domain")

#### Host
- 정식 학명 사용 (Genus species format)
- strain 정보가 있으면 반드시 포함
- NCBI Taxonomy ID가 있으면 포함

## 추출 결과 저장

서브에이전트는 추출 완료 후 다음 명령으로 결과를 저장:

```bash
python ~/.claude/skills/prophage-miner/scripts/extract_prophage.py save \
  --paper-id {paper_id} \
  --output ~/dev/phage/02_extractions/per_paper/
```

추출 결과를 stdin으로 전달하거나 `--input` 옵션으로 파일 경로를 지정한다.

## 메인 에이전트로 반환할 요약

서브에이전트는 메인 에이전트에 다음 요약만 반환:

```
Paper {paper_id}: {entity_count} entities, {relationship_count} relationships
Key prophages: {prophage_names}
Key genes: {gene_names} (top 5)
Notable findings: {1-2 sentence summary}
```
