---
name: mutation-kinetics-miner
description: This skill should be used when the user asks to "extract mutation-kinetics from papers", "analyze protein mutations and substrate relationships", "enzyme mutation literature mining", "논문에서 변이-동역학 관계 추출", "단백질 변이와 기질 관계 분석", or needs systematic extraction of mutation-property-mechanism relationships from scientific literature for protein engineering decisions.
user_invocable: true
---

# Mutation-Kinetics Miner

A comprehensive literature mining skill for extracting mutation-property-mechanism relationships from protein engineering publications. This skill systematically collects and structures data on how specific amino acid changes affect enzyme kinetics, stability, and specificity, along with mechanistic explanations.

## When to Use This Skill

Use this skill when:
- Investigating how specific mutations affect enzyme catalytic properties
- Designing protein engineering experiments based on literature evidence
- Systematically reviewing mutation effects for a target enzyme
- Understanding mechanistic explanations for observed property changes
- Building a knowledge base of mutation-function relationships

## Input

Provide the target protein using one of these formats:

```
/mutation-kinetics-miner Lipase B
/mutation-kinetics-miner P06278
/mutation-kinetics-miner EC 3.1.1.3
```

**Accepted input formats:**
- Protein name: "Lipase B", "Cytochrome P450", "TEM-1 beta-lactamase"
- UniProt ID: "P06278", "Q9Y6K9"
- EC number: "EC 3.1.1.3", "3.4.21.4"

**Note:** For ambiguous protein names, provide UniProt ID for precise identification.

## Core Workflow (4 Phases)

### Phase 1: Target Protein Identification

Establish comprehensive protein context before literature search.

**Step 1.1: Retrieve Protein Information**

Invoke `scientific-skills:uniprot-database` to retrieve:
- Canonical sequence and length
- Active site residues and binding sites
- Known natural variants and disease mutations
- Protein family classification

**Step 1.2: Obtain Baseline Kinetics**

Invoke `scientific-skills:brenda-database` to collect:
- Wild-type Km, kcat, kcat/Km values
- Substrate specificity profile
- Optimal pH and temperature
- Known inhibitors and activators

**Step 1.3: Structural Context**

Invoke `scientific-skills:alphafold-database` or `scientific-skills:pdb-database`:
- Retrieve available structure (experimental or predicted)
- Identify active site geometry
- Map catalytic residues in 3D space

**Output: Protein Profile**

```markdown
## Protein Profile: [Name]

| Property | Value | Source |
|----------|-------|--------|
| UniProt ID | P12345 | UniProt |
| EC Number | 3.1.1.3 | BRENDA |
| Length | 534 aa | UniProt |
| Active Site | Ser105, His224, Asp187 | UniProt |
| Wild-type Km | 0.45 mM (p-NPB) | BRENDA |
| Wild-type kcat | 120 s⁻¹ | BRENDA |
| Optimal pH | 7.5 | BRENDA |
| Structure | 1TCA (2.3 Å) | PDB |
```

### Phase 2: Literature Search & Collection

Systematically search multiple sources for mutation studies.

**Step 2.1: PubMed Primary Search**

Invoke `scientific-skills:pubmed-database` with structured query:

```
"[protein name]" AND (mutation OR mutant OR "site-directed mutagenesis" OR
"directed evolution" OR "rational design") AND (kinetic* OR Km OR kcat OR
"catalytic efficiency" OR "substrate specificity" OR thermostabil*)
```

Retrieve:
- PMID, DOI
- Title, authors, journal, year
- Abstract text

**Step 2.2: Preprint Search**

Invoke `scientific-skills:biorxiv-database` for recent unpublished work:
- Same query structure as PubMed
- Flag as preprint in output

**Step 2.3: Citation Expansion**

Invoke `scientific-skills:openalex-database` to:
- Find citing papers (forward references)
- Find cited papers (backward references)
- Identify review articles summarizing mutation data

**Stopping Criteria (to prevent scope explosion):**
- Maximum 2 citation generations (papers citing papers)
- Maximum 50 additional papers from citation expansion
- Stop when <10% of new papers contain relevant mutations
- Prioritize: reviews > high-citation papers > recent papers

**Step 2.4: Deduplication**

Before proceeding to Phase 3, deduplicate the paper collection:
1. Remove exact duplicates by DOI/PMID
2. Merge entries from different databases (same paper, different metadata)
3. Flag potential duplicates (same authors, same year, similar titles)
4. Record final count: unique papers / total retrieved

**Filtering Criteria:**

| Criterion | Include | Exclude |
|-----------|---------|---------|
| Publication type | Original research, Reviews | Protocols only |
| Data type | Quantitative kinetics | Qualitative only |
| Mutation type | Point mutations, small insertions | Chimeras, full domain swaps |
| Organism | All | None |

**Output: Curated Paper List**

```markdown
## Literature Collection: [N] papers

| PMID | Year | Title | Mutations | Data Types |
|------|------|-------|-----------|------------|
| 12345678 | 2023 | Engineering thermostable... | 15 | Km, kcat, Tm |
| 23456789 | 2022 | Substrate specificity of... | 8 | Km, specificity |
```

### Phase 3: Relationship & Mechanism Extraction

Extract structured data from each paper.

**Extraction Method:**
- Use `scripts/extract_mutations.py` for automated mutation notation parsing from text
- Manual curation required for mechanism interpretations and context validation
- Use Phase 1 structure (cached) for position mapping—do not re-retrieve

**Limited Access Protocol (for paywalled papers):**

When full-text is unavailable:
1. Extract mutation notations and fold-changes from abstract
2. Flag as "abstract-only" in output with reduced confidence
3. Add to priority list for full-text retrieval
4. Do not extract mechanism details (require full-text Methods/Results)

**Step 3.1: Mutation Notation Extraction**

Identify all mutation notations:
- Standard format: D121N, A234S, W167F
- Multiple mutations: D121N/A234S (double mutant)
- Insertions/deletions: ΔLoop, +Gly insert

**Position Numbering Caution:**

Position numbers often differ between sources. Always verify:

| Source | Numbering Basis | Common Offset |
|--------|-----------------|---------------|
| UniProt | Full precursor (includes signal peptide) | +20-30 residues |
| PDB | Mature protein (signal cleaved) | Reference |
| Literature | Varies by paper | Check Methods section |

**Verification protocol:**
1. Align paper sequence to UniProt canonical
2. Confirm position matches expected residue type
3. If mismatch, recalculate using sequence alignment
4. Flag uncertain positions with "[position unverified]"

**Step 3.2: Substrate Identification**

Extract substrate information:
- Substrate name and structure (if SMILES provided)
- Natural vs synthetic substrates
- Substrate analogues used in assays

**Step 3.3: Kinetic Parameter Extraction**

Extract quantitative values WITH assay conditions (critical for comparability):

| Parameter | Format | Example |
|-----------|--------|---------|
| Km | Value ± SD, units | 2.3 ± 0.2 mM |
| kcat | Value ± SD, units | 450 ± 30 s⁻¹ |
| kcat/Km | Value, units | 1.95 × 10⁵ M⁻¹s⁻¹ |
| Fold change | Relative to WT | 2.1× increase |

**Assay Conditions (Mandatory):**

| Condition | Example | Why Critical |
|-----------|---------|--------------|
| pH | 7.5 | Km varies 2-10× across pH range |
| Temperature | 25°C, 37°C | kcat doubles per ~10°C |
| Buffer | 50 mM Tris-HCl | Ionic strength affects binding |
| Substrate conc. | 0.1-10 mM | Determines Km accuracy |

**Note:** Values measured under different conditions cannot be directly compared. Flag conflicting values with condition context.

**Step 3.4: Mechanism Explanation Extraction**

Capture mechanistic insights:

| Category | Extract |
|----------|---------|
| Structural changes | H-bond disruption, loop movement, cavity size |
| Binding effects | Substrate positioning, transition state stabilization |
| Catalytic effects | Proton transfer, nucleophile activation, pKa shifts |
| Dynamics | Flexibility changes, conformational sampling |

**Step 3.5: Additional Property Extraction**

| Property | Values to Extract |
|----------|-------------------|
| Thermal stability | Tm, T50, half-life at temperature |
| pH stability | Optimal pH, pH range, residual activity |
| Solubility | Expression level, aggregation tendency |
| Substrate specificity | Activity ratios across substrates |

### Phase 4: Synthesis & Output

Generate structured output formats. Include extraction metadata for reproducibility.

**Extraction Metadata (Include in all outputs):**
```markdown
---
Extraction Date: YYYY-MM-DD
Skill Version: mutation-kinetics-miner v1.1
Target Protein: [Name] (UniProt: [ID])
Papers Analyzed: [N] unique / [M] total retrieved
Query: "[search terms used]"
---
```

**Output Format 1: Kinetics Change Table (Required)**

```markdown
## Kinetic Parameter Changes

| Mutation | Position | Substrate | Km (mM) | kcat (s⁻¹) | kcat/Km | Fold Change | Conf. | PMID |
|----------|----------|-----------|---------|------------|---------|-------------|-------|------|
| D121N | Active site | Glucose | 2.3 | 450 | 1.96×10⁵ | -2.1× | High | 12345678 |
| A234S | Surface | Glucose | 0.42 | 130 | 3.10×10⁵ | +1.5× | Med | 12345678 |
| W167F | Substrate pocket | Maltose | 5.1 | 890 | 1.74×10⁵ | +3.2× | Low | 23456789 |

**Confidence levels:**
- **High**: ≥3 independent sources, consistent values, similar assay conditions
- **Med**: 1-2 peer-reviewed sources, complete assay conditions reported
- **Low**: Single source, preprint, abstract-only, or conflicting values
```

**Output Format 2: Mechanism Analysis (Required)**

```markdown
## D121N Mutation Analysis

### Structural Changes
- Asp121 carboxyl group → Asn121 amide group
- H-bond network weakened (distance: 2.8Å → 3.5Å)
- Active site polarity reduced

### Substrate Binding Effects
- Glucose binding affinity decreased 2.1× (Km: 1.1 → 2.3 mM)
- Transition state stabilization impaired
- Binding entropy penalty increased

### Catalytic Mechanism Changes
- Proton relay pathway altered
- General base catalysis efficiency reduced
- kcat decreased (890 → 450 s⁻¹)

### Other Property Changes
- Thermal stability: Tm unchanged (72°C)
- pH optimum: shifted 7.0 → 7.5
- Solubility: improved 1.5×

### Source
- PMID: 12345678 (Kim et al., 2023)
- DOI: 10.1016/j.jmb.2023.xxx
```

**Output Format 3: Property Summary Table (Optional)**

```markdown
## Property Change Summary

| Mutation | Tm (°C) | pH Opt | Solubility | Specificity | Mechanism Summary |
|----------|---------|--------|------------|-------------|-------------------|
| D121N | 72 (=) | 7.0→7.5 | +1.5× | Maintained | H-bond weakening → Km increase |
| A234S | 68→75 | 7.0 (=) | +2.0× | Broadened | Surface hydrophilicity → stability |
| W167F | 72 (=) | 7.0 (=) | = | Shifted to maltose | Pocket volume → new substrate fit |
```

**Output Format 4: Engineering Recommendations (Optional)**

```markdown
## Engineering Insights

### Beneficial Mutations
| Mutation | Benefit | Trade-off | Combinable |
|----------|---------|-----------|------------|
| A234S | +7°C Tm | Slight Km increase | Yes (surface) |
| T45V | +2× kcat | None observed | Yes |

### Positions to Avoid
| Position | Reason | Evidence |
|----------|--------|----------|
| Asp121 | Essential for catalysis | All mutations reduce kcat >10× |
| His224 | Catalytic triad | Mutations abolish activity |

### Suggested Combinations
Based on structural analysis and literature:
1. A234S + T45V: Stability + activity (no structural conflict)
2. W167F for substrate switching (incompatible with WT specificity)
```

**Output Format 5: Machine-Readable Export (Optional)**

For downstream computational analysis, export as CSV/TSV:

```csv
mutation,position,position_type,substrate,km_mM,kcat_s-1,kcat_km,fold_change,confidence,ph,temp_C,buffer,pmid,doi,notes
D121N,121,active_site,glucose,2.3,450,1.96e5,-2.1,high,7.5,25,50mM_Tris,12345678,10.1016/xxx,
A234S,234,surface,glucose,0.42,130,3.10e5,1.5,med,7.5,25,50mM_Tris,12345678,10.1016/xxx,
W167F,167,substrate_pocket,maltose,5.1,890,1.74e5,3.2,low,7.0,37,50mM_phosphate,23456789,,abstract_only
```

**CSV Schema:**
- All numeric fields use standard units (mM, s⁻¹, M⁻¹s⁻¹)
- Empty fields = not reported
- `notes` field for flags: `abstract_only`, `preprint`, `position_unverified`

## Scientific Skills Integration

| Phase | Skill | Purpose |
|-------|-------|---------|
| 1 | `scientific-skills:uniprot-database` | Protein sequence and annotations |
| 1 | `scientific-skills:brenda-database` | Baseline kinetic parameters |
| 1 | `scientific-skills:alphafold-database` | Predicted structure context |
| 2 | `scientific-skills:pubmed-database` | Primary literature search |
| 2 | `scientific-skills:biorxiv-database` | Preprint search |
| 2 | `scientific-skills:openalex-database` | Citation network analysis |
| 3 | `scientific-skills:pdb-database` | 3D structure mapping |
| 3 | `scientific-skills:esm` | Mutation effect prediction (see below) |

**When to use ESM prediction:**
- Mutation not found in literature → predict effect computationally
- Validate extracted effects → cross-check with ESM scores
- Combinatorial mutants → predict effects of untested combinations
- Novel positions → assess conservation and predicted impact

## Validation Checklist

Before finalizing output:

- [ ] Protein profile includes active site and WT kinetics
- [ ] Literature search covers PubMed + preprints
- [ ] All mutation notations follow standard format (X###Y)
- [ ] Kinetic values include units and error bars where available
- [ ] Mechanism explanations cite specific structural features
- [ ] Source citations (PMID/DOI) provided for all data

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| No literature found | Protein too novel | Search by protein family, homologs |
| Conflicting values | Different assay conditions | See "Handling Conflicting Data" below |
| Missing WT values | Not reported in papers | Use BRENDA reference values |
| Unclear mechanisms | Paper lacks structural analysis | Flag as "mechanism unknown" |

### Handling Conflicting Data

When multiple sources report different kinetic values for the same mutation:

1. **Record all values with conditions:**
   ```
   D121N Km: 2.3 mM (pH 7.5, 25°C) [PMID:123]
   D121N Km: 3.1 mM (pH 8.0, 37°C) [PMID:456]
   ```

2. **Prioritization order:**
   - Peer-reviewed > preprint
   - Larger sample size (n>3) > smaller
   - More recent publication > older
   - Consistent methodology > mixed

3. **Report as range when conditions differ:**
   ```
   D121N Km: 2.3-3.1 mM (depends on pH/temp)
   ```

4. **Flag high-confidence vs uncertain:**
   - High confidence: ≥3 independent reports, similar conditions
   - Uncertain: single report or conflicting values

## Additional Resources

### Reference Files

- **`references/search-queries.md`** - Pre-built PubMed query templates
- **`references/mutation-patterns.md`** - Common mutation notation formats

### Scripts

- **`scripts/extract_mutations.py`** - Parse mutation notations from text
