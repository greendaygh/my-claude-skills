# Unit Operation Mapping Guide

## Overview
This guide defines how to map common workflow steps (derived from case analysis) to the standardized Unit Operation catalog (~80 UOs). Each workflow step maps to one or more UOs.

## HW vs SW Classification

### Hardware UO (UHW series)
- Involves physical manipulation of samples/reagents
- Uses laboratory equipment
- Input/Output are physical materials (DNA, cells, plates, solutions)
- Examples: liquid handling, thermocycling, centrifugation, sequencing

### Software UO (USW series)
- Involves data processing, analysis, or computational design
- Uses software tools, scripts, or algorithms
- Input/Output are digital (files, data, models, sequences)
- Examples: sequence alignment, primer design, variant calling, ML training

### Classification Decision Tree
```
Is the step primarily manipulating physical materials?
├─ YES → Hardware UO (UHW)
│   └─ Does it involve specific equipment?
│       ├─ YES → Match to specific UHW by equipment type
│       └─ NO → UHW400 (Manual) or most relevant UHW
└─ NO → Is it processing data or running software?
    ├─ YES → Software UO (USW)
    │   └─ Match to specific USW by software/algorithm type
    └─ MIXED → Split into separate HW and SW UOs
```

## Multi-Signal Matching

When mapping a workflow step to a UO, use multiple signals:

### Signal 1: Equipment/Software Match (weight: 0.35)
Compare the equipment or software mentioned in the step to the UO's equipment/software field.
- Exact match: 1.0
- Same category: 0.7
- Related: 0.4
- No match: 0.0

### Signal 2: Function Match (weight: 0.30)
Compare the biological/computational function of the step to the UO description.
- Exact function: 1.0
- Closely related: 0.7
- Partially related: 0.4
- Unrelated: 0.0

### Signal 3: Input/Output Type Match (weight: 0.20)
Compare what goes in and comes out.
- Same I/O types: 1.0
- Similar I/O: 0.5
- Different I/O: 0.0

### Signal 4: Context Match (weight: 0.15)
Consider the workflow context (what comes before and after).
- Typical workflow position: 1.0
- Unusual but valid: 0.5
- Unlikely context: 0.0

### Combined Score
```
mapping_score = 0.35*equipment + 0.30*function + 0.20*io + 0.15*context
```
- Score ≥ 0.7: Strong match → use this UO
- Score 0.5-0.7: Moderate match → review with panel
- Score < 0.5: Weak match → consider alternative UO or UHW400/USW340

## One-to-Many and Many-to-One Mappings

### One step → Multiple UOs
A single workflow step may map to multiple sequential UOs:
- "PCR amplification followed by gel verification" → UHW100 (Thermocycling) + UHW230 (Nucleic Acid Fragment Analysis)

### Multiple steps → One UO
Multiple described steps may map to a single UO:
- "wash 3 times with buffer, elute" → part of UHW250 (Nucleic Acid Purification)

### UO Instances
The same UO type can appear multiple times in a workflow:
- UHW100 instance 1: "PCR amplification"
- UHW100 instance 2: "Colony PCR verification"
Label instances: UHW100a, UHW100b, etc.

## Common Mapping Patterns

### Molecular Biology Workflows
| Common Step | Primary UO | Notes |
|-------------|-----------|-------|
| Primer design | USW020 | Software UO |
| Vector design | USW030 | Software UO |
| PCR amplification | UHW100 | Thermocycling |
| Gel electrophoresis | UHW230 | Fragment Analysis |
| DNA purification | UHW250 | Nucleic Acid Purification |
| Restriction digest | UHW100 | Thermocycling (enzyme reaction) |
| Ligation/Assembly | UHW100 | Thermocycling (isothermal or cycling) |
| Transformation | UHW090 | Electroporation; or UHW400 for chemical |
| Colony picking | UHW060 | Colony Picking |
| Miniprep | UHW250 | Nucleic Acid Purification |
| Sequencing | UHW260/265/270 | By platform type |
| Liquid handling | UHW010/020/030/040 | By throughput/volume |

### Fermentation Workflows
| Common Step | Primary UO | Notes |
|-------------|-----------|-------|
| Media preparation | UHW400 | Manual |
| Inoculation | UHW010 | Liquid Handling |
| Microplate culture | UHW190/200 | Aerobic/Anaerobic |
| Bioreactor fermentation | UHW220 | Bioreactor |
| Sampling | UHW010 | Liquid Handling |
| OD measurement | UHW380 | Microplate Reading |
| Metabolite analysis | UHW290-350 | By instrument type |

### Computational Workflows
| Common Step | Primary UO | Notes |
|-------------|-----------|-------|
| Data preprocessing | USW120/150/290 | By data type |
| Sequence alignment | USW110/130 | By purpose |
| Assembly | USW140/145 | Genome/metagenome |
| Variant calling | USW170 | |
| Expression analysis | USW180 | RNA-Seq |
| ML data prep | USW220 | Deep Learning Data Prep |
| Model training | USW240 | |
| Model evaluation | USW250 | |

## Evidence Tagging for Mapping

Every UO assignment must include an evidence tag:

| Priority | Tag | Description |
|----------|-----|-------------|
| 1 | `literature-direct` | Paper explicitly names the UO's equipment/software |
| 2 | `literature-supplementary` | From supplementary materials |
| 3 | `literature-consensus` | Multiple cases agree on this mapping |
| 4 | `manufacturer-protocol` | Equipment/kit manufacturer's protocol |
| 5 | `expert-inference` | Panel inference (reasoning required) |
| 6 | `catalog-default` | UO catalog default assignment |

## Mapping Output Format

```json
{
  "step_function": "Assembly Reaction",
  "mapped_uo": {
    "uo_id": "UHW100",
    "uo_name": "Thermocycling",
    "instance_label": "Gibson Assembly Reaction",
    "mapping_score": 0.85,
    "evidence_tag": "literature-consensus",
    "supporting_cases": ["C001", "C004", "C007"],
    "signals": {
      "equipment": 0.9,
      "function": 0.8,
      "io": 0.85,
      "context": 0.8
    }
  }
}
```
