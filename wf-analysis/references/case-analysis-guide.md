# Case Analysis Guide: From Individual Cases to Common Workflows

## Overview
After collecting individual case cards (Phase 4), this guide directs the comparative analysis to derive common workflow patterns and variants inductively.

## Analysis Pipeline

### Phase 6.1: Step Alignment

**Goal**: Align steps across all cases to identify functionally equivalent steps.

**Method**:
1. List all steps from all cases in a matrix (rows = cases, columns = aligned step positions)
2. Identify functionally equivalent steps across cases by:
   - Same biological purpose (e.g., "amplify DNA fragments" regardless of specific method)
   - Same position in workflow sequence
   - Same input/output types
3. Create an alignment table:

```json
{
  "alignment": [
    {
      "aligned_position": 1,
      "function": "Design primers/sequences",
      "cases": {
        "C001": {"step_number": 1, "step_name": "Primer design with SnapGene"},
        "C002": {"step_number": 1, "step_name": "In silico assembly design"},
        "C003": {"step_number": 1, "step_name": "Fragment design using Benchling"}
      }
    },
    {
      "aligned_position": 2,
      "function": "Amplify DNA fragments",
      "cases": {
        "C001": {"step_number": 2, "step_name": "PCR with Phusion"},
        "C002": {"step_number": 3, "step_name": "PCR amplification"},
        "C003": null  // This case used synthesized fragments, no PCR
      }
    }
  ]
}
```

**Rules**:
- Allow gaps (null) when a case skips a step
- Allow multiple cases steps to align to one position
- Preserve original step numbering for traceability

### Phase 6.2: Common Step Identification

**Categories**:
| Category | Criterion | Example |
|----------|-----------|---------|
| **Mandatory Common** | Present in ≥80% of cases | Assembly reaction, transformation |
| **Conditional Common** | Present in specific technique/condition subsets | PCR (for non-synthesized fragments) |
| **Branch Point** | Where cases diverge into different techniques | Assembly method choice (Gibson vs Golden Gate) |
| **Optional** | Present in <30% of cases | Special optimization steps |

**Output**: `common_pattern.json` with mandatory, conditional, branch, and optional steps.

### Phase 6.3: Variant Derivation (Inductive Clustering)

**Goal**: Group cases into variants based on shared characteristics.

**Clustering Approach**:
1. Define feature vectors for each case:
   - Core technique used
   - Number of steps
   - Step presence/absence pattern
   - Equipment types used
   - Scale/volume
   - Organism type
   - Automation level

2. Cluster cases:
   - Primary axis: Core technique (most discriminating)
   - Secondary axes: Scale, organism, automation
   - Each cluster = one variant

3. Name variants descriptively:
   - V1: Gibson Assembly (manual, tube-scale)
   - V2: Golden Gate Assembly (automated, plate-scale)
   - V3: SLIC Assembly (manual, tube-scale)

**Output**: `cluster_result.json`
```json
{
  "clustering_method": "technique-first hierarchical",
  "primary_axis": "core_technique",
  "secondary_axes": ["scale", "automation_level"],
  "variants": [
    {
      "variant_id": "V1",
      "name": "Gibson Assembly",
      "qualifier": "manual, tube-scale",
      "case_ids": ["C001", "C004", "C007"],
      "case_count": 3,
      "defining_features": {...}
    }
  ]
}
```

### Phase 6.4: Common Workflow Derivation

**Structure**:
```json
{
  "common_skeleton": [
    {"position": 1, "function": "Sequence Design", "mandatory": true, "uo_hint": "USW030"},
    {"position": 2, "function": "Fragment Preparation", "mandatory": true, "branches": ["PCR", "Synthesis"]},
    {"position": 3, "function": "QC: Fragment Verification", "mandatory": true, "type": "qc_checkpoint"},
    {"position": 4, "function": "Assembly Reaction", "mandatory": true, "branches": ["Gibson", "Golden Gate", "SLIC"]},
    ...
  ],
  "variant_paths": {
    "V1_Gibson": [1, "2a_PCR", 3, "4a_Gibson", 5, 6, 7],
    "V2_Golden_Gate": [1, "2a_PCR", 3, "4b_GoldenGate", 5, 6, 7]
  }
}
```

### Phase 6.5: Parameter Range Derivation

For each step where multiple cases provide numerical parameters:

```json
{
  "step_function": "Assembly Reaction",
  "parameter": "incubation_temperature",
  "unit": "°C",
  "values_by_case": {
    "C001": 50, "C004": 50, "C007": 50, "C002": 37, "C005": 37
  },
  "by_variant": {
    "V1_Gibson": {"range": [50, 50], "typical": 50, "n": 3},
    "V2_Golden_Gate": {"range": [37, 37], "typical": 37, "n": 2}
  },
  "overall": {"range": [37, 50], "typical": 50, "n": 5}
}
```

### Phase 6.6: Modularity Analysis

**Goal**: Derive this workflow's modular interface from case-level `workflow_context` data.

**Method**:
1. Aggregate `paper_workflows` from all cases → frequency count of co-occurring workflows
2. Aggregate `upstream_workflow` → identify most common upstream workflow(s) and their output
3. Aggregate `downstream_workflow` → identify most common downstream workflow(s) and their input
4. Aggregate `boundary_inputs` → define standard input interface for this workflow
5. Aggregate `boundary_outputs` → define standard output interface for this workflow
6. Identify recurring service chains (workflow sequences appearing in ≥3 cases)

**Output**: Added to `common_pattern.json`
```json
{
  "modularity": {
    "boundary_inputs": [
      {"name": "Designed fragment sequences", "frequency": 0.85, "typical_source": "WD070", "case_refs": ["C001", "C003", "C005"]}
    ],
    "boundary_outputs": [
      {"name": "Assembled circular plasmid", "frequency": 0.92, "typical_destination": "WB120", "case_refs": ["C001", "C002", "C004"]}
    ],
    "common_upstream": [{"workflow_id": "WD070", "frequency": 0.75}],
    "common_downstream": [{"workflow_id": "WB120", "frequency": 0.80}, {"workflow_id": "WB040", "frequency": 0.45}],
    "service_chains": [
      {"chain": ["WD070", "WB030", "WB120", "WT010"], "frequency": 0.60, "label": "Standard Cloning Pipeline", "case_refs": ["C001", "C003"]}
    ]
  }
}
```

**Why this matters**: Workflows must interoperate. Defining boundary I/O ensures that when workflows are assembled into a service, the output of one workflow is compatible with the input of the next. This is the foundation for composable biofoundry services.

## Analysis Quality Checklist
- [ ] All cases included in alignment
- [ ] No step information lost during alignment
- [ ] Variants derived inductively (not predefined)
- [ ] Each variant has ≥2 supporting cases
- [ ] Parameter ranges have case-level traceability
- [ ] Branch points clearly identified
- [ ] QC checkpoints positioned in common skeleton
- [ ] **Boundary I/O defined** with case-level traceability
- [ ] **Upstream/downstream workflows identified** from case evidence
- [ ] **Service chain patterns** documented (≥3 cases for each pattern)
