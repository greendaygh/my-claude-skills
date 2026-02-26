#!/usr/bin/env python3
"""Quality control and filtering for RNA-seq count matrices.

Usage:
    python qc_counts.py --input data.h5ad --output qc_data.h5ad
    python qc_counts.py --input data.h5ad --min-genes 200 --min-counts 500
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import anndata as ad
import scanpy as sc
import matplotlib.pyplot as plt


def calculate_qc_metrics(adata: ad.AnnData) -> ad.AnnData:
    """Calculate comprehensive QC metrics."""
    # Basic scanpy QC
    sc.pp.calculate_qc_metrics(adata, inplace=True, percent_top=[50, 100, 200])

    # Additional metrics
    adata.obs["log_total_counts"] = np.log10(adata.obs["total_counts"] + 1)
    adata.obs["log_n_genes"] = np.log10(adata.obs["n_genes_by_counts"] + 1)

    # Gene-level metrics
    adata.var["mean_counts"] = np.asarray(adata.X.mean(axis=0)).flatten()
    adata.var["pct_dropout"] = (adata.X == 0).mean(axis=0) * 100

    return adata


def generate_qc_plots(adata: ad.AnnData, output_dir: Path):
    """Generate QC diagnostic plots."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Distribution of counts per sample
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    axes[0].hist(adata.obs["total_counts"], bins=50, edgecolor="black")
    axes[0].set_xlabel("Total counts")
    axes[0].set_ylabel("Number of samples")
    axes[0].set_title("Library Size Distribution")

    axes[1].hist(adata.obs["n_genes_by_counts"], bins=50, edgecolor="black")
    axes[1].set_xlabel("Number of genes detected")
    axes[1].set_ylabel("Number of samples")
    axes[1].set_title("Gene Detection Distribution")

    axes[2].scatter(adata.obs["total_counts"], adata.obs["n_genes_by_counts"], alpha=0.5)
    axes[2].set_xlabel("Total counts")
    axes[2].set_ylabel("Genes detected")
    axes[2].set_title("Counts vs Genes")

    plt.tight_layout()
    plt.savefig(output_dir / "sample_qc.png", dpi=300)
    plt.close()

    # Gene-level QC
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    axes[0].hist(np.log10(adata.var["mean_counts"] + 1), bins=50, edgecolor="black")
    axes[0].set_xlabel("log10(mean counts + 1)")
    axes[0].set_ylabel("Number of genes")
    axes[0].set_title("Gene Expression Distribution")

    axes[1].hist(adata.var["pct_dropout"], bins=50, edgecolor="black")
    axes[1].set_xlabel("Dropout percentage")
    axes[1].set_ylabel("Number of genes")
    axes[1].set_title("Gene Dropout Distribution")

    plt.tight_layout()
    plt.savefig(output_dir / "gene_qc.png", dpi=300)
    plt.close()

    print(f"QC plots saved to {output_dir}/")


def filter_data(
    adata: ad.AnnData,
    min_genes: int = 200,
    min_counts: int = 500,
    min_cells: int = 3,
    max_genes: int = None
) -> ad.AnnData:
    """Filter samples and genes based on QC thresholds."""
    n_samples_before = adata.n_obs
    n_genes_before = adata.n_vars

    # Filter samples
    sc.pp.filter_cells(adata, min_genes=min_genes)
    sc.pp.filter_cells(adata, min_counts=min_counts)

    if max_genes:
        adata = adata[adata.obs["n_genes_by_counts"] < max_genes, :]

    # Filter genes
    sc.pp.filter_genes(adata, min_cells=min_cells)

    print(f"\nFiltering summary:")
    print(f"  Samples: {n_samples_before} -> {adata.n_obs} ({n_samples_before - adata.n_obs} removed)")
    print(f"  Genes: {n_genes_before} -> {adata.n_vars} ({n_genes_before - adata.n_vars} removed)")

    return adata


def detect_outliers(adata: ad.AnnData, n_std: float = 3.0) -> pd.Series:
    """Detect outlier samples based on QC metrics."""
    outliers = pd.Series(False, index=adata.obs_names)

    for metric in ["total_counts", "n_genes_by_counts"]:
        if metric in adata.obs.columns:
            values = adata.obs[metric]
            mean_val = values.mean()
            std_val = values.std()

            is_outlier = (values < mean_val - n_std * std_val) | (values > mean_val + n_std * std_val)
            outliers = outliers | is_outlier

    return outliers


def main():
    parser = argparse.ArgumentParser(
        description="Quality control for RNA-seq count matrices"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to AnnData file (.h5ad)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path for filtered AnnData (default: input_qc.h5ad)"
    )
    parser.add_argument(
        "--plots-dir", "-p", default="qc_plots",
        help="Output directory for QC plots (default: qc_plots)"
    )
    parser.add_argument(
        "--min-genes", type=int, default=200,
        help="Minimum genes detected per sample (default: 200)"
    )
    parser.add_argument(
        "--min-counts", type=int, default=500,
        help="Minimum total counts per sample (default: 500)"
    )
    parser.add_argument(
        "--min-cells", type=int, default=3,
        help="Minimum samples expressing each gene (default: 3)"
    )
    parser.add_argument(
        "--max-genes", type=int,
        help="Maximum genes detected (for doublet filtering in single-cell)"
    )
    parser.add_argument(
        "--outlier-std", type=float, default=3.0,
        help="Number of std deviations for outlier detection (default: 3.0)"
    )
    parser.add_argument(
        "--no-filter", action="store_true",
        help="Only calculate metrics, don't filter"
    )

    args = parser.parse_args()

    # Set default output path
    if args.output is None:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_qc.h5ad")

    # Load data
    print(f"Loading data from {args.input}...")
    adata = ad.read_h5ad(args.input)
    print(f"  Shape: {adata.n_obs} samples x {adata.n_vars} genes")

    # Calculate QC metrics
    print("\nCalculating QC metrics...")
    adata = calculate_qc_metrics(adata)

    # Print summary statistics
    print("\nQC Summary:")
    print(f"  Total counts: {adata.obs['total_counts'].median():.0f} (median)")
    print(f"  Genes detected: {adata.obs['n_genes_by_counts'].median():.0f} (median)")

    # Detect outliers
    outliers = detect_outliers(adata, n_std=args.outlier_std)
    n_outliers = outliers.sum()
    print(f"  Potential outliers: {n_outliers} samples (>{args.outlier_std} std)")

    adata.obs["is_outlier"] = outliers

    # Generate QC plots
    print("\nGenerating QC plots...")
    generate_qc_plots(adata, Path(args.plots_dir))

    # Filter if requested
    if not args.no_filter:
        print("\nFiltering data...")
        adata = filter_data(
            adata,
            min_genes=args.min_genes,
            min_counts=args.min_counts,
            min_cells=args.min_cells,
            max_genes=args.max_genes
        )

    # Save
    print(f"\nSaving to {args.output}...")
    adata.write_h5ad(args.output)

    # Export QC metrics
    qc_metrics_path = Path(args.output).parent / "qc_metrics.csv"
    adata.obs.to_csv(qc_metrics_path)
    print(f"QC metrics saved to {qc_metrics_path}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
