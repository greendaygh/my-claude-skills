# 도메인별 스키마 패턴

## 1. 생의학 (Biomedical) — 범용

```json
{
  "entity_types": [
    {"label": "Gene", "primary_key": "name", "properties": ["symbol", "full_name", "organism", "function"]},
    {"label": "Protein", "primary_key": "name", "properties": ["uniprot_id", "function", "organism"]},
    {"label": "Disease", "primary_key": "name", "properties": ["mesh_id", "category", "icd_code"]},
    {"label": "Drug", "primary_key": "name", "properties": ["drugbank_id", "mechanism", "status", "phase"]},
    {"label": "Pathway", "primary_key": "name", "properties": ["database", "pathway_id"]},
    {"label": "CellType", "primary_key": "name", "properties": ["tissue", "organism"]},
    {"label": "Organism", "primary_key": "name", "properties": ["taxonomy_id"]}
  ],
  "relationship_types": [
    {"type": "ASSOCIATED_WITH", "from_label": "Gene", "to_label": "Disease"},
    {"type": "INTERACTS_WITH", "from_label": "Protein", "to_label": "Protein"},
    {"type": "TARGETS", "from_label": "Drug", "to_label": "Protein"},
    {"type": "TREATS", "from_label": "Drug", "to_label": "Disease"},
    {"type": "PARTICIPATES_IN", "from_label": "Gene", "to_label": "Pathway"},
    {"type": "EXPRESSED_IN", "from_label": "Gene", "to_label": "CellType"},
    {"type": "REGULATES", "from_label": "Gene", "to_label": "Gene"}
  ]
}
```

## 2. 약물 탐색 (Drug Discovery)

```json
{
  "entity_types": [
    {"label": "Compound", "primary_key": "name", "properties": ["smiles", "molecular_weight", "logP", "chembl_id"]},
    {"label": "Target", "primary_key": "name", "properties": ["uniprot_id", "gene_symbol", "protein_class"]},
    {"label": "Disease", "primary_key": "name", "properties": ["mesh_id", "therapeutic_area"]},
    {"label": "Assay", "primary_key": "name", "properties": ["assay_type", "endpoint", "organism"]},
    {"label": "ClinicalTrial", "primary_key": "name", "properties": ["nct_id", "phase", "status"]},
    {"label": "AdverseEvent", "primary_key": "name", "properties": ["meddra_code", "severity"]},
    {"label": "Biomarker", "primary_key": "name", "properties": ["biomarker_type", "measurement"]}
  ],
  "relationship_types": [
    {"type": "BINDS_TO", "from_label": "Compound", "to_label": "Target", "properties": ["affinity_nM", "assay_type"]},
    {"type": "INHIBITS", "from_label": "Compound", "to_label": "Target", "properties": ["IC50_nM", "selectivity"]},
    {"type": "INDICATED_FOR", "from_label": "Compound", "to_label": "Disease"},
    {"type": "TESTED_IN", "from_label": "Compound", "to_label": "Assay", "properties": ["activity", "value"]},
    {"type": "CAUSES", "from_label": "Compound", "to_label": "AdverseEvent", "properties": ["frequency"]},
    {"type": "ENROLLED_IN", "from_label": "Compound", "to_label": "ClinicalTrial"},
    {"type": "PREDICTS", "from_label": "Biomarker", "to_label": "Disease"}
  ]
}
```

## 3. 유전체학/GWAS (Genomics)

```json
{
  "entity_types": [
    {"label": "Gene", "primary_key": "name", "properties": ["symbol", "chromosome", "position", "ensembl_id"]},
    {"label": "Variant", "primary_key": "name", "properties": ["rsid", "chromosome", "position", "ref", "alt", "maf"]},
    {"label": "Trait", "primary_key": "name", "properties": ["efo_id", "category"]},
    {"label": "Locus", "primary_key": "name", "properties": ["chromosome", "start", "end"]},
    {"label": "Pathway", "primary_key": "name", "properties": ["pathway_id", "database"]},
    {"label": "Population", "primary_key": "name", "properties": ["ancestry", "sample_size"]},
    {"label": "Study", "primary_key": "name", "properties": ["study_id", "design", "sample_size"]}
  ],
  "relationship_types": [
    {"type": "ASSOCIATED_WITH", "from_label": "Variant", "to_label": "Trait", "properties": ["p_value", "beta", "odds_ratio", "confidence_interval"]},
    {"type": "LOCATED_IN", "from_label": "Variant", "to_label": "Gene"},
    {"type": "MAPS_TO", "from_label": "Variant", "to_label": "Locus"},
    {"type": "ENRICHED_IN", "from_label": "Gene", "to_label": "Pathway", "properties": ["enrichment_score"]},
    {"type": "IDENTIFIED_IN", "from_label": "Variant", "to_label": "Population"},
    {"type": "INTERACTS_WITH", "from_label": "Gene", "to_label": "Gene", "properties": ["interaction_type"]}
  ]
}
```

## 4. 단일세포 생물학 (Single-Cell Biology)

```json
{
  "entity_types": [
    {"label": "Gene", "primary_key": "name", "properties": ["symbol", "ensembl_id"]},
    {"label": "CellType", "primary_key": "name", "properties": ["cell_ontology_id", "lineage"]},
    {"label": "CellState", "primary_key": "name", "properties": ["description", "markers"]},
    {"label": "Tissue", "primary_key": "name", "properties": ["uberon_id"]},
    {"label": "Ligand", "primary_key": "name", "properties": ["type"]},
    {"label": "Receptor", "primary_key": "name", "properties": ["family"]},
    {"label": "TranscriptionFactor", "primary_key": "name", "properties": ["tf_class"]}
  ],
  "relationship_types": [
    {"type": "MARKER_OF", "from_label": "Gene", "to_label": "CellType", "properties": ["specificity", "expression_level"]},
    {"type": "DIFFERENTIATES_TO", "from_label": "CellType", "to_label": "CellType"},
    {"type": "FOUND_IN", "from_label": "CellType", "to_label": "Tissue"},
    {"type": "COMMUNICATES_VIA", "from_label": "CellType", "to_label": "CellType", "properties": ["ligand", "receptor"]},
    {"type": "REGULATES_TF", "from_label": "TranscriptionFactor", "to_label": "Gene"},
    {"type": "TRANSITIONS_TO", "from_label": "CellState", "to_label": "CellState"}
  ]
}
```

## 5. CRISPR/유전자 편집

```json
{
  "entity_types": [
    {"label": "CRISPRSystem", "primary_key": "name", "properties": ["type", "pam_sequence", "organism_source"]},
    {"label": "GuideRNA", "primary_key": "name", "properties": ["sequence", "target_gene", "off_target_score"]},
    {"label": "DeliveryMethod", "primary_key": "name", "properties": ["category", "cargo_capacity"]},
    {"label": "Gene", "primary_key": "name", "properties": ["symbol", "organism"]},
    {"label": "CellType", "primary_key": "name", "properties": ["tissue"]},
    {"label": "Disease", "primary_key": "name", "properties": ["mesh_id", "genetic_basis"]},
    {"label": "Outcome", "primary_key": "name", "properties": ["outcome_type", "efficiency"]}
  ],
  "relationship_types": [
    {"type": "EDITS", "from_label": "CRISPRSystem", "to_label": "Gene", "properties": ["edit_type", "efficiency"]},
    {"type": "DELIVERED_BY", "from_label": "CRISPRSystem", "to_label": "DeliveryMethod"},
    {"type": "TARGETS_GENE", "from_label": "GuideRNA", "to_label": "Gene"},
    {"type": "APPLIED_IN", "from_label": "CRISPRSystem", "to_label": "CellType", "properties": ["efficiency"]},
    {"type": "TREATS_DISEASE", "from_label": "CRISPRSystem", "to_label": "Disease"},
    {"type": "PRODUCES", "from_label": "CRISPRSystem", "to_label": "Outcome"}
  ]
}
```

## 스키마 설계 원칙

1. **Primary Key**: 항상 `name` 필드를 기본 키로 사용 (정규화된 이름)
2. **속성 최소화**: 필수 속성만 스키마에 포함, 나머지는 추출 시 동적 추가
3. **관계 방향성**: 의미적으로 자연스러운 방향 (Gene→Disease, Drug→Target)
4. **Provenance 필수**: 모든 관계에 `:EXTRACTED_FROM` 역추적 가능
5. **사이클 2 확장**: 사이클 1에서 발견된 패턴으로 엔티티/관계 추가 가능
