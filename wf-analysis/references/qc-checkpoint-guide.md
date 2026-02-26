# QC Checkpoint Design Guide

## Overview
QC (Quality Control) checkpoints are critical decision points between Unit Operations where the output is evaluated before proceeding.

## QC Checkpoint Structure
```json
{
  "qc_id": "QC001",
  "position": "Between UHW100a (PCR) and UHW010 (Fragment Mixing)",
  "measurement_items": [
    {
      "metric": "Band size on gel",
      "method": "1% agarose gel electrophoresis or fragment analyzer",
      "pass_criteria": "Single band at expected size ± 10%",
      "fail_action": "Re-optimize PCR conditions (annealing temp, extension time)",
      "evidence_tag": "literature-consensus",
      "case_refs": ["C001", "C004", "C007"]
    },
    {
      "metric": "DNA concentration",
      "method": "NanoDrop or Qubit",
      "pass_criteria": ">10 ng/µL for each fragment",
      "fail_action": "Scale up PCR or concentrate",
      "evidence_tag": "literature-consensus",
      "case_refs": ["C001", "C004"]
    }
  ]
}
```

## QC Identification from Cases

### Signal Phrases in Papers
Look for these phrases to identify QC steps:
- "was verified by...", "was confirmed using..."
- "was checked with...", "was validated through..."
- "gel electrophoresis showed...", "sequencing confirmed..."
- "purity was assessed...", "concentration was measured..."
- "was analyzed by...", "quality was evaluated..."
- "only samples that...", "samples passing... were used"
- "if [condition], then [repeat/discard]..."

### Implicit QC (from workflow logic)
Even if not explicitly stated, QC checkpoints are expected:
- After any amplification step (PCR products verified)
- After any purification step (yield and purity checked)
- After assembly (verification of correct construct)
- After transformation (colony count, correct phenotype)
- After sequencing (sequence accuracy, coverage)
- Between HW and SW transitions (data quality check)

## QC Types

### Go/No-Go QC
Binary decision: proceed or stop.
- Example: "Correct band on gel → proceed; No band → troubleshoot"

### Quantitative QC
Numerical threshold determines action.
- Example: "DNA concentration >50 ng/µL → proceed; 10-50 ng/µL → concentrate; <10 ng/µL → repeat"

### Branching QC
Result determines which path to follow.
- Example: "Colony count >100 → pick 8 colonies; <100 → re-transform with higher DNA amount"

## Parameter Derivation from Cases
When cases report different QC criteria:
1. Collect all criteria from cases
2. Report range and most common value
3. Note case-specific conditions that affect criteria
4. Panel confirms final criteria in Round 4

## QC in Visualization
- Represented as diamond nodes in workflow graph
- Pass → green edge to next UO
- Fail → red dashed edge to previous UO (loop-back) or termination
- Multiple QC criteria shown as tooltip/annotation
