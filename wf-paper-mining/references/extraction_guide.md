# 리소스 추출 가이드

## 개요

바이오파운드리 워크플로 관련 논문에서 리소스를 추출하는 가이드.
7-component UO 구조를 기반으로 하며, 추출 결과는 `ExtractionResult` Pydantic 모델에 맞춰 JSON으로 저장한다.

---

## 추출 대상 (8 카테고리)

### 1. 워크플로 (`workflows`)

논문에서 수행된 실험 워크플로를 식별한다.

- 카탈로그 ID 매핑 시도: `WD` (설계) / `WB` (벤치) / `WT` (테스트) / `WL` (학습)
- `assets/workflow_catalog.json` 참조하여 가장 가까운 워크플로 매칭
- 카탈로그에 없으면 `is_new: true`, `catalog_id: null`로 설정

```json
{
  "catalog_id": "WB005",
  "name": "Gibson Assembly Workflow",
  "description": "다중 DNA 단편의 등온 조립을 통한 플라스미드 구축",
  "is_new": false,
  "confidence": 0.9,
  "source_section": "Methods"
}
```

하나의 논문에서 여러 워크플로가 수행될 수 있다. 각각 별도 항목으로 기록한다.

### 2. 하드웨어 UO (`hardware_uos`)

실물(샘플, 시약, 플레이트 등)을 다루는 유닛오퍼레이션. 7개 구성요소를 기록한다.

| 구성요소 | 필드명 | 기록 내용 |
|---------|--------|----------|
| Input | `input` | 투입 실물 (이전 UO 출력에서 유래) |
| Output | `output` | 생성 실물 (정제 DNA, colony plate 등) |
| Equipment | `equipment` | 사용 장비 + 설정값 (온도, rpm, 시간) |
| Consumables | `consumables` | 팁, 튜브, 플레이트, 키트, 멤브레인 등 |
| Material & Method | `material_and_method` | 실험 환경 + 구체적 절차 |
| Result | `result` | 관측값/상태 (수율, colony 수, 농도) |
| Discussion | `discussion` | 해석, 특이사항, 실패/예외 노트 |

- 카탈로그 매핑: `assets/uo_catalog.json`에서 `UHW` 시리즈 참조
- 장비명 기반 매핑 힌트: `equipment_keywords.json` 참조
- 매칭 불가 시 `is_new: true` + 상세 설명

```json
{
  "catalog_id": "UHW100",
  "name": "Thermocycling",
  "is_new": false,
  "input": "PCR-amplified DNA fragments (100-500 ng, 20 µL)",
  "output": "Assembled circular plasmid (~5-10 kb)",
  "equipment": "Bio-Rad T100 thermal cycler, 50°C 60 min",
  "consumables": "Gibson Assembly Master Mix (NEB E2611), 0.2 mL PCR tubes",
  "material_and_method": "Equimolar DNA fragments를 ice 위에서 혼합, Master Mix 10 µL 첨가 후 50°C 60분 반응",
  "result": "Assembly efficiency 90%, colony PCR 확인",
  "discussion": "4개 이상 단편 조립 시 효율 감소 관찰",
  "confidence": 0.85,
  "source_section": "Methods"
}
```

### 3. 소프트웨어 UO (`software_uos`)

데이터/모델을 다루는 유닛오퍼레이션. 7개 구성요소를 기록한다.

| 구성요소 | 필드명 | 기록 내용 |
|---------|--------|----------|
| Input | `input` | 투입 데이터/파일 |
| Output | `output` | 생성 산출물 (분석 결과, 모델 출력) |
| Parameters | `parameters` | 설정값/하이퍼파라미터/seed |
| Environment | `environment` | 실행 환경 (OS, 패키지, 버전, 컨테이너) |
| Method | `method` | 처리 절차 (자연어 또는 스크립트 요약) |
| Result | `result` | 성능/QC 지표, 중간 결과 |
| Discussion | `discussion` | 해석, 특이사항, 실패/예외 |

- 카탈로그 매핑: `assets/uo_catalog.json`에서 `USW` 시리즈 참조

```json
{
  "catalog_id": "USW110",
  "name": "Sequence Alignment",
  "is_new": false,
  "input": "FASTQ files (paired-end, 150bp reads)",
  "output": "Sorted BAM files with index",
  "parameters": "BWA-MEM2, -t 8, default parameters",
  "environment": "Ubuntu 20.04, BWA-MEM2 v2.2.1, samtools v1.15",
  "method": "Reference genome에 paired-end reads alignment 후 coordinate sort",
  "result": "Mapping rate 98.2%, mean coverage 30x",
  "discussion": "저복잡도 영역에서 mapping quality 낮음",
  "confidence": 0.9,
  "source_section": "Methods"
}
```

### 4. 장비 (`equipment`)

논문에서 사용된 장비를 기록한다.

- **이름**: 장비 유형 (예: "Thermal cycler", "Liquid handler")
- **제조사**: 명시되어 있으면 반드시 기록 (예: "Bio-Rad", "Hamilton")
- **모델명**: 명시되어 있으면 반드시 기록 (예: "T100", "STAR")
- **설정값**: 주요 운전 조건 (온도, rpm, 시간 등)
- **UO 매핑**: 해당 장비가 사용되는 UO의 카탈로그 ID

동일 장비가 여러 UO에서 사용될 수 있다. 각 UO별로 별도 기록한다.

```json
{
  "name": "Thermal cycler",
  "manufacturer": "Bio-Rad",
  "model": "T100",
  "settings": "50°C 60 min, lid 55°C",
  "mapped_uo_id": "UHW100",
  "confidence": 0.9,
  "source_section": "Methods"
}
```

### 5. 소모품 (`consumables`)

팁, 튜브, 플레이트, 키트, 멤브레인, 컬럼 등 1회용 소모품을 기록한다.

- **카탈로그 번호가 있으면 반드시 기록**
- `type`: tip / tube / plate / kit / membrane / column / filter 등

```json
{
  "name": "Gibson Assembly Master Mix",
  "type": "kit",
  "manufacturer": "NEB",
  "catalog_number": "E2611",
  "specification": "10 reactions",
  "confidence": 0.9,
  "source_section": "Methods"
}
```

### 6. 시약 (`reagents`)

효소, 버퍼, 배지, 화학물질, 염료, 항체 등을 기록한다.

- **카탈로그 번호가 있으면 반드시 기록**
- `type`: enzyme / buffer / media / chemical / dye / antibody 등

```json
{
  "name": "Phusion High-Fidelity DNA Polymerase",
  "type": "enzyme",
  "manufacturer": "NEB",
  "catalog_number": "M0530",
  "concentration": "2 U/µL, 0.5 µL per 50 µL reaction",
  "confidence": 0.9,
  "source_section": "Methods"
}
```

### 7. UO 연결 (`uo_connections`)

선행 UO의 output이 후속 UO의 input으로 이어지는 관계를 추적한다.

- `transfer_type`: `sample` (실물) / `data` (데이터 파일) / `control_signal` (제어 신호)
- `transfer_object`: 구체적으로 전달되는 대상 (정제 DNA, FASTQ 파일 등)

```json
{
  "from_uo": "UHW100 (PCR Amplification)",
  "to_uo": "UHW250 (Nucleic Acid Purification)",
  "transfer_type": "sample",
  "transfer_object": "PCR product (amplified DNA fragments)",
  "confidence": 0.85
}
```

### 8. QC 체크포인트 (`qc_checkpoints`)

워크플로 중 품질을 확인하는 지점을 기록한다.

- `after_uo`: 어떤 UO 수행 후 QC가 이루어지는지
- `metric`: 측정 지표 (농도, 순도, colony 수, mapping rate 등)
- `threshold`: 통과 기준값 (명시된 경우)
- `action_on_fail`: 실패 시 조치 (재실행, 조건 변경, 중단 등)

```json
{
  "name": "PCR Product Gel Verification",
  "after_uo": "UHW100",
  "metric": "Agarose gel band size",
  "threshold": "Expected size ± 10%",
  "action_on_fail": "Primer 재설계 또는 annealing 온도 최적화",
  "confidence": 0.85
}
```

---

## 섹션별 신뢰도 가중치

논문의 어떤 섹션에서 추출했는지에 따라 기본 신뢰도 상한이 달라진다.

| 섹션 | 가중치 | 근거 |
|------|--------|------|
| Results | 0.9 | 실제 수행/관측된 내용이므로 가장 신뢰도 높음 |
| Methods | 0.85 | 구체적 실험 방법 기술 |
| Abstract | 0.85 | 핵심 정보 요약 |
| Introduction | 0.7 | 배경 정보, 타 연구 참조가 많음 |
| Discussion | 0.6 | 저자의 해석과 추론 포함 |

**Abstract-only 논문**: full text가 없는 논문은 모든 항목의 confidence에 **-0.2 페널티**를 적용한다. 예: Methods에서 추출 가능한 0.85 → abstract-only면 최대 0.65.

---

## 추출 원칙

### 원칙 1: 원문 명시 정보만 추출

원문에 명시적으로 기술된 정보만 추출한다. 추론, 외삽, 일반 지식 기반 보충은 **금지**한다.

- **허용**: "PCR was performed at 55°C for 30 cycles" → `equipment: "55°C, 30 cycles"`
- **금지**: 논문에 온도 미기재 → "일반적으로 55°C이므로" 라고 채우기
- 미기재 항목은 빈 문자열(`""`)로 남긴다

### 원칙 2: 출처 섹션 필수 기록

모든 추출 항목에 `source_section` 필드를 반드시 기록한다.

- 값: `Methods` / `Results` / `Abstract` / `Introduction` / `Discussion` / `Supplementary`
- 여러 섹션에서 정보가 나오면 가장 구체적인 섹션을 기록

### 원칙 3: 장비 모델명 필수 기록

장비 모델명이 논문에 명시되면 반드시 기록한다.

- 예: "Hamilton STAR", "Bio-Rad C1000", "Beckman Biomek i7"
- 모델명이 없으면 `model: ""`

### 원칙 4: 시약/소모품 카탈로그 번호 기록

카탈로그 번호가 명시되어 있으면 반드시 기록한다.

- 예: "NEB #E2611", "Sigma-Aldrich #T1503"
- 없으면 `catalog_number: ""`

### 원칙 5: UO 카탈로그 매핑 시도

`assets/uo_catalog.json`의 UO 목록과 `equipment_keywords.json`의 장비 키워드를 참조하여 매핑한다.

- 장비명 → UO 매핑: 예) "thermal cycler" → `UHW100`, "colony picker" → `UHW060`
- 기능 → UO 매핑: 예) "DNA purification" → `UHW250`, "flow cytometry" → `UHW070`
- 소프트웨어 → UO 매핑: 예) "BWA alignment" → `USW110`, "DESeq2" → `USW180`

### 원칙 6: 신규 UO 후보 처리

카탈로그에 없는 UO는 다음 두 곳에 기록한다:
1. 해당 UO 항목에 `is_new: true`, `catalog_id: null` 설정
2. 최상위 `new_uo_candidates` 리스트에 UO 이름 추가

### 원칙 7: UO 간 연결 추적

실물/데이터 흐름을 기준으로 선행 UO → 후속 UO 연결을 기록한다.

- 실물 흐름: "PCR product를 gel purification" → `UHW100 → UHW250`, transfer_type: `sample`
- 데이터 흐름: "sequencing reads를 alignment" → `UHW260 → USW110`, transfer_type: `data`

### 원칙 8: 다중 워크플로 인식

하나의 논문에서 여러 워크플로가 수행될 수 있다. 각 워크플로를 별도로 식별하고 해당 UO를 올바른 워크플로에 귀속시킨다.

---

## 추출 결과 저장

### JSON 구조

`ExtractionResult` Pydantic 모델을 준수하는 JSON을 생성한다.

```json
{
  "paper_id": "W1234567890",
  "workflow_id": "WB005",
  "extraction_date": "2026-03-04",
  "workflows": [],
  "hardware_uos": [],
  "software_uos": [],
  "equipment": [],
  "consumables": [],
  "reagents": [],
  "samples": [],
  "uo_connections": [],
  "qc_checkpoints": [],
  "new_uo_candidates": [],
  "notes": ""
}
```

### 저장 명령

```bash
echo '<JSON>' | python -m scripts.extract_resources save \
  --paper-id {paper_id} \
  --workflow-id {workflow_id} \
  --output {output_dir}
```

- stdin으로 JSON 전달
- 저장 경로: `{output_dir}/{paper_id}_{workflow_id}.json`
- 저장 시 자동으로 Pydantic 검증 수행

### 검증 명령

```bash
python -m scripts.extract_resources validate \
  --extraction {extraction_file_path}
```

- 검증 성공: `{"valid": true, "errors": []}`
- 검증 실패: `{"valid": false, "errors": [...]}`

### 요약 명령

```bash
python -m scripts.extract_resources summary \
  --input {extraction_dir} \
  --workflow-id {workflow_id}
```

---

## 주의사항

1. **Abstract-only 논문**: full text가 없으면 abstract에서만 추출하고, 모든 confidence에 -0.2 페널티 적용
2. **동일 장비 다중 사용**: 같은 장비가 여러 UO에서 사용되면 각각 별도 equipment 항목으로 기록
3. **신규 UO 이중 기록**: `is_new: true` UO는 반드시 `new_uo_candidates` 필드에도 이름 추가
4. **confidence 범위**: 0.0 ~ 1.0 사이 값만 허용. 섹션 가중치와 abstract-only 페널티를 반영하여 결정
5. **빈 필드 허용**: 정보가 없는 필드는 빈 문자열(`""`)로 남김. 추론으로 채우지 않음
6. **Supplementary Materials**: Methods에 "see Supplementary"로 언급된 경우, supplementary에서 추출한 정보도 포함 (source_section: `Supplementary`)
