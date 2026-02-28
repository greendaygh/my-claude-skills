# Software UO 7-Component Writing Guide

## Overview
Each Software Unit Operation (USW series) has 7 components that must be populated from case card data.

## Canonical Variant File Structure

Variant files MUST use this top-level structure:
```json
{
  "variant_id": "V1",
  "variant_name": "Descriptive Name",
  "case_ids": ["C001", "C003"],
  "description": "...",
  "unit_operations": [
    {
      "uo_id": "USW200a",
      "uo_name": "Sequence Alignment",
      "instance_label": "Read Mapping",
      "type": "software",
      "step_position": 1,
      "input": { "items": [...] },
      "output": { "items": [...] },
      "parameters": { "items": [...] },
      "environment": { "items": [...] },
      "method": { "items": [...] },
      "result": { "items": [...] },
      "discussion": { "items": [...] }
    }
  ]
}
```

Key rules:
- Use `unit_operations` (NOT `uo_sequence`)
- Use `variant_name` (NOT `name`)
- Use `case_ids` (NOT `case_refs`, `cases`, `supporting_cases`)
- Components are flat fields on the UO object (NOT nested under a `components` wrapper)
- `step_position` must be an integer

## Component Definitions and Extraction Rules

### 1. Input
**What**: Data, files, or models entering this UO.
**Format**:
```json
{
  "items": [
    {
      "name": "Raw FASTQ files",
      "source_uo": "UHW260 (Short-read Sequencing)",
      "format": "FASTQ, paired-end 150bp",
      "specifications": "Illumina NovaSeq output, ~30M reads per sample",
      "case_refs": ["C001", "C003"],
      "evidence_tag": "literature-direct"
    }
  ]
}
```

### 2. Output
**What**: Generated data, files, analysis results.
**Format**:
```json
{
  "items": [
    {
      "name": "Filtered FASTQ files",
      "destination_uo": "USW130 (Read Mapping)",
      "format": "FASTQ",
      "specifications": "Quality-filtered, adapter-trimmed reads",
      "case_refs": ["C001", "C003"],
      "evidence_tag": "literature-direct"
    }
  ]
}
```

### 3. Parameters
**What**: Software options, hyperparameters, settings for reproducibility.
**Format**:
```json
{
  "items": [
    {
      "name": "quality_threshold",
      "value": 30,
      "range": [20, 30],
      "description": "Minimum base quality score (Phred)",
      "case_refs": ["C001: Q30", "C003: Q20"],
      "evidence_tag": "literature-consensus"
    },
    {
      "name": "min_length",
      "value": 50,
      "range": [36, 100],
      "description": "Minimum read length after trimming",
      "case_refs": ["C001: 50bp", "C003: 100bp"],
      "evidence_tag": "literature-consensus"
    }
  ]
}
```

### 4. Environment
**What**: Computational environment, software tools with version/developer details, hardware.
**Format**:
```json
{
  "software": [
    {
      "name": "fastp",
      "version": "0.23.x",
      "developer": "OpenGene (Shifu Chen)",
      "source": "https://github.com/OpenGene/fastp",
      "license": "MIT",
      "case_refs": ["C001: v0.23.2", "C003: v0.23.4"],
      "evidence_tag": "literature-direct"
    }
  ],
  "runtime": {
    "os": "Linux",
    "container": "Docker/Singularity (optional)",
    "conda_env": "ngs-qc",
    "hardware": "Standard compute node, 16GB RAM minimum",
    "case_refs": ["C001"],
    "evidence_tag": "literature-supplementary"
  }
}
```

**Software field rules (v1.3.0)**:
- **name**: Tool/software name (e.g., "fastp", "SnapGene", "BLAST")
- **version**: Version string or range aggregated from cases (e.g., "0.23.x" covering 0.23.2-0.23.4)
- **developer**: Developer, vendor, or organization (e.g., "OpenGene", "Dotmatics", "NCBI"). Use `[미기재]` if not identified.
- **source**: URL to official repository or website (optional, use `[미기재]` if not available)
- **license**: Software license type if known (optional, e.g., "MIT", "GPL-3.0", "Commercial")
- Aggregate across cases: if different cases use different versions, show the range and individual case contributions
- Include both commercial and open-source tools
```

### 5. Method
**What**: Procedure/algorithm description using environment resources.
**Format**:
```json
{
  "procedure": "1. Run fastp on paired-end FASTQ files with specified quality threshold [C001, C003]. 2. Adapter detection: automatic (fastp built-in) [C001] or specified adapter sequences [C003]. 3. Quality trimming: sliding window approach, remove bases below threshold [C001, C003]. 4. Length filtering: discard reads shorter than min_length [C001, C003]. 5. Generate QC report (HTML + JSON) [C001].",
  "case_refs": ["C001", "C003"],
  "evidence_tag": "literature-consensus"
}
```

### 6. Result
**What**: Performance metrics, QC indicators, intermediate results.
**Format**:
```json
{
  "measurements": [
    {
      "metric": "Reads retained",
      "value": "90-98%",
      "case_refs": ["C001: 95.2%", "C003: 92.1%"],
      "evidence_tag": "literature-direct"
    },
    {
      "metric": "Q30 ratio after filtering",
      "value": ">95%",
      "case_refs": ["C001: 97.1%", "C003: 95.8%"],
      "evidence_tag": "literature-direct"
    }
  ],
  "qc_checkpoint": {
    "measurement": "Q30 ratio and read count",
    "pass_criteria": "Q30 > 90%, retained reads > 80%",
    "fail_action": "Check sequencing run quality, consider re-sequencing",
    "evidence_tag": "literature-consensus"
  }
}
```

### 7. Discussion
**What**: Interpretation, issues, troubleshooting.
Same format as HW Discussion component.

## Case Reference and Evidence Tagging
Same principles as HW guide — every value traceable to case IDs, evidence tags mandatory.
