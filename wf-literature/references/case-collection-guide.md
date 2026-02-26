# Case Collection Guide: Faithful Extraction from Literature

## Core Principles

### 1. 원문 충실 (Source Fidelity)
Record exactly what the paper states. Do NOT interpret, generalize, or abstract. If the paper says "37°C for 1 hour", record "37°C for 1 hour" — not "standard incubation".

### 2. 빠짐없이 (Comprehensive Extraction)
Check ALL sections:
- Methods/Materials section (primary source)
- Supplementary Methods (often contains critical details)
- Figure legends (equipment photos, gel images reveal conditions)
- Table footnotes (parameter details)
- Results section (QC data, actual outcomes)

### 3. 차이 보존 (Preserve Differences)
Each paper may have different conditions for the same nominal step. Record each paper's specific conditions exactly. Do not merge or average across papers at this stage.

### 4. 정보 부재 표시 (Mark Missing Information)
- Use `[미기재]` for information not mentioned in the paper
- NEVER guess or fill in from general knowledge
- NEVER use default values from manufacturer protocols unless the paper explicitly references them

### 5. QC 포착 (Capture QC Steps)
Identify QC checkpoints from phrases like:
- "was verified by...", "was confirmed using...", "was checked with..."
- "gel electrophoresis showed...", "sequencing confirmed..."
- "purity was assessed...", "concentration was measured..."
- Any mention of pass/fail criteria

### 6. DOI 검증 (DOI Verification)
**CRITICAL: LLMs frequently hallucinate DOIs that look plausible but do not exist.**

When recording paper metadata:
- **NEVER fabricate or guess a DOI.** If the DOI is not explicitly provided in the source, leave it empty or use `[미기재]`.
- **DOI format**: Must start with `10.XXXX/` (e.g., `10.1038/s41467-017-02753-2`). Do NOT store as URL (`https://doi.org/...`).
- **Common hallucination patterns**: LLM-generated DOIs often have correct prefix (journal code) but wrong suffix (article ID). For example, `10.1038/s41467-017-02753-2` looks valid but the actual DOI may be `10.1038/s41467-017-02467-3`.
- **Cross-check**: If you have a PMID, verify the DOI matches PubMed's record. If you have a title, search for it rather than constructing a DOI.
- **N/A is better than fake**: Recording `"doi": ""` is always better than recording a plausible-looking but unverified DOI.

Sources of verified DOIs (in order of reliability):
1. PubMed record (via PMID lookup) — **most reliable**
2. OpenAlex API response — reliable (sourced from CrossRef)
3. Paper PDF header/footer — reliable
4. Paper HTML landing page — reliable
5. LLM memory/inference — **NEVER use, always hallucinated**

### 7. 모듈 경계 인식 (Recognize Modular Boundaries)
Workflows are modular building blocks that combine to form services/capabilities. A single paper often describes multiple workflows chained together (e.g., Vector Design → DNA Assembly → Transformation → Sequencing Verification).

**When extracting cases, you MUST identify:**
- **All workflows** mentioned in the paper (list their IDs from the catalog)
- **Upstream workflow**: What workflow preceded this one? What was its output that became this workflow's input?
- **Downstream workflow**: What workflow follows? What output does this workflow produce for the next?
- **Boundary inputs**: The exact physical materials or data entering this workflow from outside (previous workflow or external source)
- **Boundary outputs**: The exact physical materials or data leaving this workflow to the next step

**Key signals for workflow boundaries:**
- "The assembled construct was then transformed..." (Assembly → Transformation boundary)
- "Following purification, the library was sequenced..." (Purification → Sequencing boundary)
- "Designed primers were used for PCR..." (Design → Build boundary)
- Section breaks in Methods, or numbered protocol sections

## Case Card Structure

```json
{
  "case_id": "WB030-C001",
  "metadata": {
    "pmid": "12345678",
    "doi": "10.1038/...",
    "authors": "Kim et al.",
    "year": 2023,
    "journal": "Nature Methods",
    "title": "Full paper title",
    "purpose": "Brief description of what was achieved (in context of this workflow)",
    "organism": "E. coli DH5α",
    "scale": "tube-scale, 20 µL reactions",
    "automation_level": "manual|semi-automated|fully-automated",
    "core_technique": "Gibson Assembly",
    "fulltext_access": true
  },
  "steps": [
    {
      "step_number": 1, "step_name": "PCR amplification",
      "equipment": [{"name": "Thermal cycler", "model": "T100", "manufacturer": "Bio-Rad"}],
      "software": [],
      "reagents": "Phusion HF (NEB M0530)", "conditions": "98°C 30s, 35×(...)", "..."
    }
  ],
  "flow_diagram": "Step1 → Step2 → Step3 → [QC] → Step4",
  "workflow_context": {
    "service_context": "E. coli lycopene pathway construction (Design → Assembly → Transform → Verify)",
    "paper_workflows": ["WD070", "WB030", "WB120", "WT010", "WL010"],
    "upstream_workflow": {"workflow_id": "WD070", "workflow_name": "Vector Design", "output_to_this": "Designed vector map with fragment sequences and primers"},
    "downstream_workflow": {"workflow_id": "WB120", "workflow_name": "Biology-mediated DNA Transfers", "input_from_this": "Assembled circular plasmid construct"},
    "boundary_inputs": ["Designed fragment sequences (from WD070)", "Template DNA for PCR", "Primers"],
    "boundary_outputs": ["Assembled circular plasmid (verified by colony PCR)"]
  },
  "completeness": {}
}
```

## Step Extraction Protocol

For each experimental step identified in the paper:

### Step Fields
| Field | What to Extract | Example |
|-------|----------------|---------|
| step_number | Sequential order as performed | 1 |
| step_name | Descriptive name (from paper's terminology) | "PCR amplification of inserts" |
| description | What was done (paper's own words where possible) | "Fragments were amplified using Phusion HF polymerase with 30 cycles" |
| equipment | Array of equipment objects (name, model, manufacturer) | `[{"name": "Thermal cycler", "model": "T100", "manufacturer": "Bio-Rad"}]` or `[{"name": "[미기재]", "model": "[미기재]", "manufacturer": "[미기재]"}]` |
| software | Array of software objects (name, version, developer) | `[{"name": "SnapGene", "version": "7.0", "developer": "Dotmatics"}]` or `[]` if none |
| reagents | Specific reagents, kits, enzymes | "Phusion HF DNA Polymerase (NEB M0530), dNTPs 200µM each" |
| conditions | Temperature, time, concentrations, volumes | "98°C 30s, 35×(98°C 10s, 60°C 30s, 72°C 30s/kb), 72°C 5min" |
| result_qc | Any measurement or verification mentioned | "1% agarose gel, expected band at 2.1 kb observed" |
| notes | Anything unusual, troubleshooting, or tips mentioned | "GC-rich template required 3% DMSO" |

### Extraction from Different Paper Sections
- **Methods**: Primary source. Extract step-by-step in order described.
- **Supplementary**: Often contains exact concentrations, cycle numbers, equipment models. Cross-reference with Methods.
- **Results**: Look for QC data — gel images, sequencing results, colony counts. Link to relevant steps.
- **Figure Legends**: Equipment photos, experimental setups, gel annotations.

### Equipment Detail Extraction
For each step, extract equipment as a **structured array**:
- **name**: Equipment type/category (e.g., "Thermal cycler", "Microplate reader", "Flow cytometer")
- **model**: Specific model name (e.g., "T100", "CLARIOstar Plus", "FACSAria III"). Look in Methods, Supplementary, and Figure legends.
- **manufacturer**: Maker/brand (e.g., "Bio-Rad", "BMG Labtech", "BD Biosciences"). Often stated alongside model name.

**Where to find equipment details:**
- Methods section: "...using a Bio-Rad T100 thermal cycler" → name=Thermal cycler, model=T100, manufacturer=Bio-Rad
- Supplementary Table: Equipment lists often include full manufacturer details
- Figure legends: Photos of equipment setups may include model information
- Acknowledgments: Sometimes mention specific equipment grants with model details

**Rules:**
- If model is mentioned but not manufacturer: record model, mark manufacturer as `[미기재]`
- If only equipment type is mentioned (e.g., "thermal cycler"): name=Thermal cycler, model=`[미기재]`, manufacturer=`[미기재]`
- If multiple equipment used in one step: add multiple objects to the array
- If no equipment used (e.g., manual pipetting only): use `[{"name": "[미기재]", "model": "[미기재]", "manufacturer": "[미기재]"}]`

### Software Detail Extraction
For each step, extract software tools as a **structured array**:
- **name**: Software/tool name (e.g., "SnapGene", "Geneious Prime", "BLAST", "Python")
- **version**: Version string (e.g., "7.0.3", "2024.0.1", "2.14.0+"). Look in Methods and Supplementary.
- **developer**: Developer, vendor, or organization (e.g., "Dotmatics", "Biomatters", "NCBI", "PSF")

**Where to find software details:**
- Methods section: "Sequences were analyzed using SnapGene v7.0 (Dotmatics)"
- Supplementary Methods: Detailed software versions and parameter settings
- Data availability: Analysis scripts and tool versions

**Rules:**
- If a step uses no software: use empty array `[]`
- If version is not mentioned: mark as `[미기재]`
- If developer is not mentioned: mark as `[미기재]`
- Include both commercial (SnapGene, Geneious) and open-source (BLAST, Bowtie2) tools
- Include programming languages/frameworks when used as tools (e.g., Python, R, MATLAB)

## Completeness Assessment

After extraction, rate completeness:

```json
"completeness": {
  "fulltext": true/false,       // Was full text accessible?
  "step_detail": "minimal|partial|detailed",
  "equipment_info": "none|partial|complete",  // Equipment name/model/manufacturer coverage
  "software_info": "none|partial|complete",   // Software name/version/developer coverage
  "qc_criteria": true/false,    // Were explicit QC criteria given?
  "supplementary": true/false   // Were supplementary methods available?
}
```

## Quality Checklist Per Case
- [ ] All steps from Methods section captured
- [ ] Supplementary methods cross-referenced
- [ ] Equipment recorded as structured array (name, model, manufacturer) or [미기재]
- [ ] Software recorded as structured array (name, version, developer) or empty []
- [ ] Specific reagent names and catalog numbers (where available)
- [ ] Temperature, time, volume conditions recorded
- [ ] QC steps identified and linked to results
- [ ] Flow diagram accurately reflects step sequence
- [ ] No interpretation or generalization added
- [ ] [미기재] used for ALL missing information
- [ ] **Workflow context captured**: all workflows in paper identified, upstream/downstream recorded
- [ ] **Boundary I/O defined**: what enters and exits this workflow clearly stated

## Common Extraction Pitfalls
1. **Over-interpretation**: Adding knowledge not in the paper
2. **Under-extraction**: Missing supplementary details
3. **Normalization**: Converting paper-specific terms to generic terms
4. **QC blindness**: Missing implicit QC steps (e.g., "the product was verified")
5. **Step merging**: Combining distinct steps that the paper describes separately
6. **Boundary blindness**: Failing to recognize where one workflow ends and another begins. A paper describing "gene cloning and expression" spans multiple workflows (Design → Assembly → Transformation → Expression → Purification) — each is a separate modular workflow
7. **Scope creep**: Including steps that belong to adjacent workflows. Only extract steps belonging to the target workflow; record other workflows in `paper_workflows` and boundary connections
