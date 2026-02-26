#!/usr/bin/env python3
"""End-to-end bulk RNA-seq analysis workflow example.

This script demonstrates a complete analysis pipeline from count matrix
to differential expression results and visualizations.

Usage:
    python bulk_workflow.py --counts counts.csv --metadata metadata.csv --output results/
"""

import argparse
from pathlib import Path

import pandas as pd
import numpy as np
import anndata as ad
import scanpy as sc
import matplotlib.pyplot as plt


def load_and_validate_data(counts_path: str, metadata_path: str) -> ad.AnnData:
    """Load count matrix and metadata, create AnnData object."""
    print("=" * 60)
    print("STEP 1: Loading and Validating Data")
    print("=" * 60)

    # Load count matrix (genes x samples)
    counts = pd.read_csv(counts_path, index_col=0)
    print(f"Count matrix shape: {counts.shape}")

    # Load metadata
    metadata = pd.read_csv(metadata_path, index_col=0)
    print(f"Metadata samples: {len(metadata)}")
    print(f"Metadata columns: {list(metadata.columns)}")

    # Align samples
    common_samples = counts.columns.intersection(metadata.index)
    print(f"Common samples: {len(common_samples)}")

    counts = counts[common_samples]
    metadata = metadata.loc[common_samples]

    # Create AnnData (samples x genes)
    adata = ad.AnnData(
        X=counts.T.values,
        obs=metadata,
        var=pd.DataFrame(index=counts.index)
    )

    # Validate
    assert adata.X.min() >= 0, "Counts contain negative values!"
    print(f"\nCreated AnnData: {adata.n_obs} samples x {adata.n_vars} genes")

    return adata


def quality_control(adata: ad.AnnData, output_dir: Path) -> ad.AnnData:
    """Perform quality control and filtering."""
    print("\n" + "=" * 60)
    print("STEP 2: Quality Control")
    print("=" * 60)

    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(adata, inplace=True)

    # Print QC summary
    print(f"Total counts per sample: {adata.obs['total_counts'].median():.0f} (median)")
    print(f"Genes detected per sample: {adata.obs['n_genes_by_counts'].median():.0f} (median)")

    # Store raw counts
    adata.layers["counts"] = adata.X.copy()

    # Filter genes
    n_genes_before = adata.n_vars
    sc.pp.filter_genes(adata, min_counts=10)
    sc.pp.filter_genes(adata, min_cells=3)
    print(f"Genes after filtering: {adata.n_vars} (removed {n_genes_before - adata.n_vars})")

    # Generate QC plots
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    axes[0].hist(adata.obs["total_counts"], bins=30, edgecolor="black")
    axes[0].set_xlabel("Total counts")
    axes[0].set_title("Library Size Distribution")

    axes[1].hist(adata.obs["n_genes_by_counts"], bins=30, edgecolor="black")
    axes[1].set_xlabel("Number of genes")
    axes[1].set_title("Gene Detection Distribution")

    axes[2].scatter(adata.obs["total_counts"], adata.obs["n_genes_by_counts"], alpha=0.5)
    axes[2].set_xlabel("Total counts")
    axes[2].set_ylabel("Genes detected")
    axes[2].set_title("Counts vs Genes")

    plt.tight_layout()
    plt.savefig(output_dir / "qc_plots.png", dpi=300)
    plt.close()

    return adata


def normalize_and_transform(adata: ad.AnnData, output_dir: Path) -> ad.AnnData:
    """Normalize counts and perform PCA for batch assessment."""
    print("\n" + "=" * 60)
    print("STEP 3: Normalization and Batch Assessment")
    print("=" * 60)

    # Log-normalize for visualization
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Identify highly variable genes
    sc.pp.highly_variable_genes(adata, n_top_genes=2000)
    print(f"Highly variable genes: {adata.var['highly_variable'].sum()}")

    # PCA
    sc.tl.pca(adata, svd_solver='arpack', n_comps=50)

    # Plot PCA colored by available metadata
    color_cols = [col for col in adata.obs.columns if adata.obs[col].dtype == 'object'][:3]
    if color_cols:
        sc.pl.pca(adata, color=color_cols, show=False, save=False)
        plt.savefig(output_dir / "pca_plot.png", dpi=300, bbox_inches="tight")
        plt.close()
        print(f"PCA plot saved, colored by: {color_cols}")

    # Check variance explained
    var_explained = adata.uns['pca']['variance_ratio'][:10]
    print(f"Variance explained by top 10 PCs: {var_explained.sum():.1%}")

    return adata


def differential_expression(
    adata: ad.AnnData,
    condition_col: str,
    treatment: str,
    control: str,
    output_dir: Path
) -> pd.DataFrame:
    """Perform differential expression analysis using PyDESeq2."""
    print("\n" + "=" * 60)
    print("STEP 4: Differential Expression Analysis")
    print("=" * 60)

    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    # Prepare count matrix from raw counts
    count_matrix = pd.DataFrame(
        adata.layers["counts"],
        index=adata.obs_names,
        columns=adata.var_names
    ).astype(int)

    print(f"Running DESeq2: {treatment} vs {control}")
    print(f"  Treatment samples: {(adata.obs[condition_col] == treatment).sum()}")
    print(f"  Control samples: {(adata.obs[condition_col] == control).sum()}")

    # Create DESeq2 dataset
    dds = DeseqDataSet(
        counts=count_matrix,
        metadata=adata.obs,
        design_factors=condition_col
    )

    # Run DESeq2
    dds.deseq2()

    # Extract results
    stat_res = DeseqStats(dds, contrast=[condition_col, treatment, control])
    stat_res.summary()

    results = stat_res.results_df.sort_values("padj")

    # Summary
    sig_up = ((results["padj"] < 0.05) & (results["log2FoldChange"] > 1)).sum()
    sig_down = ((results["padj"] < 0.05) & (results["log2FoldChange"] < -1)).sum()

    print(f"\nSignificant genes (padj < 0.05, |log2FC| > 1):")
    print(f"  Upregulated: {sig_up}")
    print(f"  Downregulated: {sig_down}")

    # Save results
    results.to_csv(output_dir / "de_results.csv")
    print(f"\nResults saved to {output_dir / 'de_results.csv'}")

    return results


def visualize_results(
    results: pd.DataFrame,
    adata: ad.AnnData,
    condition_col: str,
    output_dir: Path
):
    """Generate publication-ready visualizations."""
    print("\n" + "=" * 60)
    print("STEP 5: Visualization")
    print("=" * 60)

    # Volcano plot
    fig, ax = plt.subplots(figsize=(10, 8))

    results["-log10(padj)"] = -np.log10(results["padj"].fillna(1))

    # Classify genes
    sig_up = (results["padj"] < 0.05) & (results["log2FoldChange"] > 1)
    sig_down = (results["padj"] < 0.05) & (results["log2FoldChange"] < -1)
    not_sig = ~(sig_up | sig_down)

    ax.scatter(results.loc[not_sig, "log2FoldChange"],
               results.loc[not_sig, "-log10(padj)"],
               c="#999999", alpha=0.5, s=10, label="Not significant")
    ax.scatter(results.loc[sig_up, "log2FoldChange"],
               results.loc[sig_up, "-log10(padj)"],
               c="#e74c3c", alpha=0.7, s=20, label=f"Up ({sig_up.sum()})")
    ax.scatter(results.loc[sig_down, "log2FoldChange"],
               results.loc[sig_down, "-log10(padj)"],
               c="#3498db", alpha=0.7, s=20, label=f"Down ({sig_down.sum()})")

    ax.axhline(-np.log10(0.05), linestyle="--", color="gray", alpha=0.5)
    ax.axvline(-1, linestyle="--", color="gray", alpha=0.5)
    ax.axvline(1, linestyle="--", color="gray", alpha=0.5)

    ax.set_xlabel("log2 Fold Change", fontsize=12)
    ax.set_ylabel("-log10(adjusted p-value)", fontsize=12)
    ax.set_title("Volcano Plot", fontsize=14)
    ax.legend()

    plt.tight_layout()
    plt.savefig(output_dir / "volcano_plot.png", dpi=300)
    plt.close()
    print("Saved volcano_plot.png")

    # Heatmap of top genes
    top_genes = results.dropna(subset=["padj"]).head(30).index.tolist()
    top_genes = [g for g in top_genes if g in adata.var_names]

    if len(top_genes) > 0:
        sc.pl.heatmap(
            adata, var_names=top_genes, groupby=condition_col,
            show=False, save=False
        )
        plt.savefig(output_dir / "top_genes_heatmap.png", dpi=300, bbox_inches="tight")
        plt.close()
        print("Saved top_genes_heatmap.png")


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end bulk RNA-seq analysis workflow"
    )
    parser.add_argument("--counts", "-c", required=True, help="Count matrix CSV")
    parser.add_argument("--metadata", "-m", required=True, help="Sample metadata CSV")
    parser.add_argument("--condition", default="condition", help="Condition column name")
    parser.add_argument("--treatment", "-t", required=True, help="Treatment group name")
    parser.add_argument("--control", "-r", required=True, help="Control group name")
    parser.add_argument("--output", "-o", default="results", help="Output directory")

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Run pipeline
    adata = load_and_validate_data(args.counts, args.metadata)
    adata = quality_control(adata, output_dir)
    adata = normalize_and_transform(adata, output_dir)
    results = differential_expression(
        adata, args.condition, args.treatment, args.control, output_dir
    )
    visualize_results(results, adata, args.condition, output_dir)

    # Save processed data
    adata.write_h5ad(output_dir / "processed_data.h5ad")

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print("Files created:")
    for f in output_dir.glob("*"):
        print(f"  - {f.name}")


if __name__ == "__main__":
    main()
