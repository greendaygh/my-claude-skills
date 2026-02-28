# Hardware UO 7-Component Writing Guide

## Overview
Each Hardware Unit Operation (UHW series) has 7 components that must be populated from case card data.

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
      "uo_id": "UHW100a",
      "uo_name": "PCR Amplification",
      "instance_label": "Insert Amplification",
      "type": "hardware",
      "step_position": 1,
      "input": { "items": [...] },
      "output": { "items": [...] },
      "equipment": { "items": [...] },
      "consumables": { "items": [...] },
      "material_and_method": { "items": [...] },
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
**What**: Physical materials entering this UO from a preceding UO or external source.
**Extract from cases**: Look at what each case feeds into this step.
**Format**:
```json
{
  "items": [
    {
      "name": "PCR-amplified DNA fragments",
      "source_uo": "UHW100a (PCR Amplification)",
      "specifications": "100-500 ng each fragment, 20 µL volume",
      "case_refs": ["C001", "C004"],
      "evidence_tag": "literature-direct"
    }
  ]
}
```

### 2. Output
**What**: Physical materials produced by this UO, passed to the next UO.
**Extract from cases**: What does each case produce from this step?
**Format**:
```json
{
  "items": [
    {
      "name": "Assembled DNA construct",
      "destination_uo": "UHW090 (Transformation)",
      "specifications": "circular plasmid, ~5-10 kb",
      "case_refs": ["C001", "C004"],
      "evidence_tag": "literature-direct"
    }
  ]
}
```

### 3. Equipment
**What**: Laboratory equipment used and their settings.
**Extract from cases**: Specific equipment models, manufacturers, and parameter settings.
**Format**:
```json
{
  "items": [
    {
      "name": "Thermal cycler",
      "model": "T100",
      "manufacturer": "Bio-Rad",
      "settings": {
        "temperature": {"value": 50, "unit": "°C", "range": [50, 50], "evidence_tag": "literature-consensus"},
        "duration": {"value": 60, "unit": "min", "range": [15, 60], "evidence_tag": "literature-consensus"},
        "lid_temperature": {"value": 55, "unit": "°C", "evidence_tag": "expert-inference", "reasoning": "Standard 5°C above reaction temperature"}
      },
      "case_refs": ["C001:Bio-Rad T100", "C004:[미기재]"],
      "evidence_tag": "literature-direct"
    }
  ]
}
```

**Equipment field rules (v1.3.0)**:
- **name**: Equipment type/category (e.g., "Thermal cycler", "Microplate reader")
- **model**: Specific model name, separated from manufacturer (e.g., "T100", "CLARIOstar Plus")
- **manufacturer**: Equipment maker/brand (e.g., "Bio-Rad", "BMG Labtech")
- Aggregate across cases: if different cases report different models for the same function, list all as separate items with respective `case_refs`
- Use `[미기재]` for model/manufacturer when not reported in any case

### 4. Consumables
**What**: Single-use items consumed during the UO.
**Extract from cases**: Specific kits, tubes, tips, plates.
**Format**:
```json
{
  "items": [
    {
      "name": "Gibson Assembly Master Mix",
      "catalog": "NEB E2611",
      "quantity": "10 µL per reaction",
      "case_refs": ["C001", "C007"],
      "evidence_tag": "literature-direct"
    },
    {
      "name": "PCR tubes",
      "catalog": "[미기재]",
      "quantity": "0.2 mL thin-wall",
      "case_refs": ["C001"],
      "evidence_tag": "literature-supplementary"
    }
  ]
}
```

### 5. Material and Method
**What**: The experimental environment and detailed procedure using the equipment and consumables.
**Extract from cases**: Synthesize from case step descriptions, preserving case-specific language.
**Format**: Narrative text with case references.
```json
{
  "environment": "Standard molecular biology lab, room temperature (22-25°C)",
  "procedure": "1. Combine equimolar amounts of purified DNA fragments (total 100-500 ng) in a PCR tube on ice [C001, C004]. 2. Add 10 µL Gibson Assembly Master Mix (NEB E2611) to 10 µL of fragment mix [C001, C007]. 3. Incubate at 50°C for 15-60 minutes in thermal cycler [C001: 60min, C004: 15min, C007: 30min]. 4. Place on ice or store at -20°C until transformation [C001].",
  "case_refs": ["C001", "C004", "C007"],
  "evidence_tag": "literature-consensus"
}
```

### 6. Result
**What**: Measurable outcomes and QC data from this UO.
**Extract from cases**: Any quantitative results, gel images, measurements.
**Format**:
```json
{
  "measurements": [
    {
      "metric": "Assembly efficiency",
      "value": "80-95% correct assemblies",
      "method": "Colony PCR + sequencing",
      "case_refs": ["C001: 90%", "C004: 85%"],
      "evidence_tag": "literature-direct"
    }
  ],
  "qc_checkpoint": {
    "measurement": "Colony PCR band pattern",
    "pass_criteria": "Expected band size ± 10%",
    "fail_action": "Re-optimize fragment ratios or assembly conditions",
    "evidence_tag": "literature-consensus"
  }
}
```

### 7. Discussion
**What**: Interpretation of results, troubleshooting notes, exceptions, SOP knowledge.
**Extract from cases**: Notes, tips, troubleshooting sections, observations.
**Format**:
```json
{
  "interpretation": "Gibson Assembly consistently yields high efficiency for 2-4 fragment assemblies. Efficiency decreases with >5 fragments [C001, C007].",
  "troubleshooting": [
    {"issue": "Low colony count", "solution": "Increase fragment concentration or extend incubation", "case_ref": "C004"},
    {"issue": "Wrong assembly products", "solution": "Verify overlap sequences and Tm", "case_ref": "C007"}
  ],
  "special_notes": "For GC-rich regions, adding 3% DMSO to the reaction improves results [C007].",
  "evidence_tag": "literature-consensus"
}
```

## Case Reference Principle
EVERY value must be traceable to specific case IDs. When aggregating across cases, show the range and individual case contributions.

## Handling [미기재] Items
- If most cases report a value → use literature-consensus
- If no case reports → use expert-inference (requires panel vote) OR leave as [미기재] with note
- Never silently fill in missing data
