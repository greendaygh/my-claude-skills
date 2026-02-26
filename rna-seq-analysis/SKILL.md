---
name: rna-seq-analysis
description: This skill should be used when the user asks to "analyze RNA-seq data", "perform differential expression analysis", "analyze transcriptome data", "run gene expression workflow", or needs help with bulk RNA sequencing analysis. It provides a complete count-to-results pipeline using Python (pydeseq2, scanpy).
user_invocable: true
---

# RNA-seq Analysis

A comprehensive pipeline for analyzing RNA-seq data from count matrices to differential expression results. This skill focuses on the **counts-to-results** workflow, supporting both bulk and single-cell RNA-seq analysis using Python tools.

## When to Use This Skill

Use this skill when:
- Starting from a gene count matrix (not raw FASTQ files)
- Performing differential expression analysis between conditions
- Generating publication-ready visualizations (volcano plots, heatmaps, PCA)
- Analyzing data from GEO, collaborators, or processed pipelines

## Prerequisites

**Experimental requirements:**
- Minimum 3 biological replicates per condition (5+ recommended for robust detection)
- Raw integer counts (not normalized values)

**Note on sample size:** With fewer than 5 replicates per group, dispersion estimation becomes less reliable. Consider using `lfcShrink` for more stable fold-change estimates in low-replicate experiments.

**Install required packages:**

```bash
pip install pydeseq2==0.4.11 scanpy==1.10.0 anndata==0.10.0 pandas matplotlib seaborn gseapy
```

For reproducible environments, use the `requirements.txt` in this skill's directory.

## Core Workflow

### Step 1: Load and Validate Count Matrix

Load count data into AnnData format for standardized processing.

```python
import pandas as pd
import anndata as ad

# Load count matrix (genes x samples)
counts = pd.read_csv("counts.csv", index_col=0)

# Load sample metadata
metadata = pd.read_csv("metadata.csv", index_col=0)

# Create AnnData object
adata = ad.AnnData(X=counts.T, obs=metadata)

# Ensure unique gene names (duplicates cause indexing errors in downstream analysis)
adata.var_names_make_unique()

# Validate
assert adata.X.min() >= 0, "Counts must be non-negative integers"
assert all(adata.obs.index == counts.columns), "Sample IDs must match"
```

**Required inputs:**
- Count matrix: genes (rows) x samples (columns), raw integer counts
- Metadata: sample IDs matching count columns, condition/group labels

**Input validation:**
```python
import numpy as np

def validate_counts(counts, metadata):
    """Validate count matrix before analysis."""
    # Check for non-integer values
    if not np.issubdtype(counts.values.dtype, np.integer):
        print("WARNING: Counts contain non-integer values. Converting to int.")
        counts = counts.astype(int)

    # Check for negative values
    assert (counts.values >= 0).all(), "ERROR: Negative counts detected"

    # Check for NaN values
    assert not counts.isna().any().any(), "ERROR: NaN values in count matrix"

    # Check sample alignment
    assert set(counts.columns) == set(metadata.index), "ERROR: Sample IDs don't match"

    return counts
```

### Step 2: Quality Control and Filtering

Filter low-quality genes and assess sample quality.

```python
import scanpy as sc

# Basic QC metrics
sc.pp.calculate_qc_metrics(adata, inplace=True)

# Filter genes: require minimum counts across samples
sc.pp.filter_genes(adata, min_counts=10)

# Filter genes: require expression in minimum number of samples
sc.pp.filter_genes(adata, min_cells=3)

# Generate QC plots
sc.pl.highest_expr_genes(adata, n_top=20, save="_top_genes.png")
```

**QC thresholds (adjust based on experiment):**

| Metric | Typical Threshold | Action |
|--------|-------------------|--------|
| Gene count | > 10 total reads | Filter low-expressed genes |
| Sample library size | > 1M reads | Flag/remove low-depth samples |
| Detected genes | > 10,000 genes | Flag low-complexity samples |

### Step 3: Normalization and Batch Assessment

Normalize counts and check for batch effects.

```python
# Store raw counts for DE analysis
adata.layers["counts"] = adata.X.copy()

# Log-normalize for visualization
sc.pp.normalize_total(adata, target_sum=1e4)
sc.pp.log1p(adata)

# PCA for batch effect assessment (set random_state for reproducibility)
sc.tl.pca(adata, svd_solver='arpack', random_state=42)
sc.pl.pca(adata, color=['condition', 'batch'], save="_pca.png")
```

**Batch effect assessment:**
- Check if samples cluster by batch rather than condition in PCA
- If batch effects present, include batch as covariate in DE model

### Step 4: Differential Expression Analysis

**Important:** DESeq2 requires **raw integer counts**, not normalized data. The normalized values from Step 3 are for visualization only. Use `adata.layers["counts"]` for DE analysis.

Perform differential expression using pydeseq2.

```python
from pydeseq2.dds import DeseqDataSet
from pydeseq2.ds import DeseqStats

# Prepare count matrix (samples x genes)
count_matrix = pd.DataFrame(
    adata.layers["counts"],
    index=adata.obs_names,
    columns=adata.var_names
)

# Create DESeq2 dataset
dds = DeseqDataSet(
    counts=count_matrix,
    metadata=adata.obs,
    design_factors="condition"  # Add "+ batch" if batch correction needed
)

# Run DESeq2 pipeline
dds.deseq2()

# Extract results for specific contrast
stat_res = DeseqStats(dds, contrast=["condition", "treatment", "control"])
stat_res.summary()

# Get results table
results_df = stat_res.results_df
results_df = results_df.sort_values("padj")
```

**Significance thresholds (defaults):**

| Parameter | Default | Description |
|-----------|---------|-------------|
| padj | < 0.05 | FDR-adjusted p-value |
| log2FoldChange | abs > 1 | 2-fold change minimum |

### Step 5: Visualization

Generate publication-ready figures.

```python
import matplotlib.pyplot as plt
import numpy as np

# Volcano plot
def volcano_plot(results, padj_thresh=0.05, lfc_thresh=1):
    results['-log10(padj)'] = -np.log10(results['padj'])

    # Classify genes
    results['significant'] = (
        (results['padj'] < padj_thresh) &
        (abs(results['log2FoldChange']) > lfc_thresh)
    )

    plt.figure(figsize=(10, 8))
    plt.scatter(
        results['log2FoldChange'],
        results['-log10(padj)'],
        c=results['significant'].map({True: 'red', False: 'grey'}),
        alpha=0.5
    )
    plt.xlabel('log2 Fold Change')
    plt.ylabel('-log10(adjusted p-value)')
    plt.axhline(-np.log10(padj_thresh), linestyle='--', color='blue')
    plt.axvline(-lfc_thresh, linestyle='--', color='blue')
    plt.axvline(lfc_thresh, linestyle='--', color='blue')
    plt.savefig('volcano_plot.png', dpi=300, bbox_inches='tight')

volcano_plot(results_df)

# Heatmap of top DE genes
top_genes = results_df.head(50).index.tolist()
sc.pl.heatmap(adata, var_names=top_genes, groupby='condition', save="_top50_heatmap.png")
```

### Step 6: Export Results

Save analysis outputs for downstream use.

```python
# Save significant genes
sig_genes = results_df[
    (results_df['padj'] < 0.05) &
    (abs(results_df['log2FoldChange']) > 1)
]
sig_genes.to_csv("significant_genes.csv")

# Save full results
results_df.to_csv("full_de_results.csv")

# Save normalized counts for downstream analysis
adata.write_h5ad("processed_data.h5ad")

print(f"Found {len(sig_genes)} significant DE genes")
print(f"  - Upregulated: {(sig_genes['log2FoldChange'] > 0).sum()}")
print(f"  - Downregulated: {(sig_genes['log2FoldChange'] < 0).sum()}")
```

## Decision Tree: Bulk vs Single-Cell

| Question | Bulk RNA-seq | Single-Cell RNA-seq |
|----------|--------------|---------------------|
| UMI counts? | No | Yes |
| Cells per sample | Millions (pooled) | Individual cells |
| Normalization | DESeq2 median-of-ratios | scran/scanpy |
| DE tool | pydeseq2 | scanpy rank_genes_groups |
| Sparsity | Low | High (many zeros) |

For single-cell analysis, use `scientific-skills:scanpy` for specialized workflows.

## Batch Effect Correction

If batch effects detected in PCA:

```python
# Option 1: Include batch in design formula
dds = DeseqDataSet(
    counts=count_matrix,
    metadata=adata.obs,
    design_factors=["batch", "condition"]
)

# Option 2: Use ComBat-seq (recommended for strong batch effects)
# Install: pip install combat-seq
from combat.pycombat import pycombat
corrected_counts = pycombat(count_matrix.T, adata.obs['batch']).T
```

## Quality Metrics Reference

| Metric | Acceptable Range | Concern If |
|--------|------------------|------------|
| Mapping rate | > 70% | < 50% |
| Assigned reads | > 60% | < 40% |
| Duplication rate | < 60% | > 80% |
| Detected genes | > 10,000 | < 8,000 |
| rRNA contamination | < 5% | > 10% |

## Scripts Reference

All scripts are located in the `scripts/` subdirectory of this skill (`~/.claude/skills/rna-seq-analysis/scripts/`).

| Script | Purpose | Usage |
|--------|---------|-------|
| `scripts/load_counts.py` | Load count matrices | `python load_counts.py --input counts.csv --metadata meta.csv` |
| `scripts/run_deseq2.py` | Differential expression | `python run_deseq2.py --input data.h5ad --contrast condition treatment control` |
| `scripts/visualize_results.py` | Generate plots | `python visualize_results.py --input results.csv --output figures/` |
| `scripts/qc_counts.py` | Quality control | `python qc_counts.py --input data.h5ad` |
| `scripts/pathway_analysis.py` | Gene set enrichment | `python pathway_analysis.py --genes sig_genes.csv --database MSigDB` |

## Scientific Skills Integration

This skill integrates with:
- `scientific-skills:pydeseq2` - Detailed DESeq2 statistical methods
- `scientific-skills:scanpy` - Single-cell RNA-seq analysis
- `scientific-skills:scientific-visualization` - Advanced plotting

## Validation Checklist

Before finalizing analysis:

- [ ] Sample metadata matches count matrix columns
- [ ] PCA shows samples cluster by condition (not batch)
- [ ] Dispersion estimates follow expected curve
- [ ] MA plot shows no systematic bias
- [ ] Significant genes include expected markers (if known)
- [ ] Pathway enrichment shows biologically coherent terms

## Troubleshooting

| Issue | Possible Cause | Solution |
|-------|----------------|----------|
| No significant genes | Low statistical power | Increase replicates, relax thresholds |
| All genes significant | Batch effect or contamination | Check PCA, add batch correction |
| High dispersion | Technical variability | Filter low-count genes more stringently |
| Outlier samples | Library prep issues | Remove or flag in metadata |
