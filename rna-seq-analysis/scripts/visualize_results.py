#!/usr/bin/env python3
"""Generate publication-ready visualizations for RNA-seq results.

Usage:
    python visualize_results.py --results de_results.csv --output figures/
    python visualize_results.py --results de_results.csv --adata data.h5ad --output figures/
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns


def volcano_plot(
    results: pd.DataFrame,
    padj_thresh: float = 0.05,
    lfc_thresh: float = 1.0,
    output_path: str = "volcano_plot.png"
):
    """Generate volcano plot from DE results."""
    df = results.copy()
    df["-log10(padj)"] = -np.log10(df["padj"].fillna(1))

    # Classify genes
    df["category"] = "Not significant"
    df.loc[
        (df["padj"] < padj_thresh) & (df["log2FoldChange"] > lfc_thresh),
        "category"
    ] = "Up"
    df.loc[
        (df["padj"] < padj_thresh) & (df["log2FoldChange"] < -lfc_thresh),
        "category"
    ] = "Down"

    # Colors
    colors = {"Not significant": "#999999", "Up": "#e74c3c", "Down": "#3498db"}

    # Plot
    fig, ax = plt.subplots(figsize=(10, 8))

    for category, color in colors.items():
        subset = df[df["category"] == category]
        ax.scatter(
            subset["log2FoldChange"],
            subset["-log10(padj)"],
            c=color,
            label=f"{category} ({len(subset)})",
            alpha=0.6,
            s=20
        )

    # Threshold lines
    ax.axhline(-np.log10(padj_thresh), linestyle="--", color="gray", alpha=0.5)
    ax.axvline(-lfc_thresh, linestyle="--", color="gray", alpha=0.5)
    ax.axvline(lfc_thresh, linestyle="--", color="gray", alpha=0.5)

    # Labels
    ax.set_xlabel("log2 Fold Change", fontsize=12)
    ax.set_ylabel("-log10(adjusted p-value)", fontsize=12)
    ax.set_title("Volcano Plot", fontsize=14)
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved volcano plot to {output_path}")


def ma_plot(
    results: pd.DataFrame,
    padj_thresh: float = 0.05,
    output_path: str = "ma_plot.png"
):
    """Generate MA plot from DE results."""
    df = results.copy()

    # MA plot uses baseMean (average expression) vs log2FC
    if "baseMean" not in df.columns:
        print("WARNING: baseMean not found, skipping MA plot")
        return

    df["significant"] = df["padj"] < padj_thresh

    fig, ax = plt.subplots(figsize=(10, 8))

    # Non-significant
    nonsig = df[~df["significant"]]
    ax.scatter(
        np.log10(nonsig["baseMean"] + 1),
        nonsig["log2FoldChange"],
        c="#999999",
        alpha=0.3,
        s=10,
        label=f"Not significant ({len(nonsig)})"
    )

    # Significant
    sig = df[df["significant"]]
    ax.scatter(
        np.log10(sig["baseMean"] + 1),
        sig["log2FoldChange"],
        c="#e74c3c",
        alpha=0.6,
        s=20,
        label=f"Significant ({len(sig)})"
    )

    ax.axhline(0, linestyle="-", color="black", alpha=0.3)
    ax.set_xlabel("log10(mean expression + 1)", fontsize=12)
    ax.set_ylabel("log2 Fold Change", fontsize=12)
    ax.set_title("MA Plot", fontsize=14)
    ax.legend(loc="upper right")

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved MA plot to {output_path}")


def pvalue_histogram(
    results: pd.DataFrame,
    output_path: str = "pvalue_hist.png"
):
    """Generate p-value histogram for QC."""
    fig, ax = plt.subplots(figsize=(8, 6))

    ax.hist(results["pvalue"].dropna(), bins=50, edgecolor="black", alpha=0.7)
    ax.set_xlabel("p-value", fontsize=12)
    ax.set_ylabel("Frequency", fontsize=12)
    ax.set_title("P-value Distribution", fontsize=14)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved p-value histogram to {output_path}")


def top_genes_barplot(
    results: pd.DataFrame,
    n_genes: int = 20,
    output_path: str = "top_genes.png"
):
    """Generate bar plot of top DE genes."""
    df = results.copy()
    df = df.dropna(subset=["padj", "log2FoldChange"])
    df = df.sort_values("padj").head(n_genes)

    fig, ax = plt.subplots(figsize=(10, 8))

    colors = ["#e74c3c" if x > 0 else "#3498db" for x in df["log2FoldChange"]]

    ax.barh(range(len(df)), df["log2FoldChange"], color=colors, alpha=0.8)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df.index)
    ax.set_xlabel("log2 Fold Change", fontsize=12)
    ax.set_title(f"Top {n_genes} Differentially Expressed Genes", fontsize=14)
    ax.axvline(0, color="black", linewidth=0.5)

    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved top genes plot to {output_path}")


def heatmap(
    adata,
    results: pd.DataFrame,
    n_genes: int = 50,
    groupby: str = "condition",
    output_path: str = "heatmap.png"
):
    """Generate heatmap of top DE genes."""
    import scanpy as sc

    # Get top genes
    top_genes = results.dropna(subset=["padj"]).sort_values("padj").head(n_genes).index.tolist()
    top_genes = [g for g in top_genes if g in adata.var_names]

    if len(top_genes) == 0:
        print("WARNING: No top genes found in AnnData, skipping heatmap")
        return

    # Create heatmap
    sc.pl.heatmap(
        adata,
        var_names=top_genes,
        groupby=groupby,
        show=False,
        save=False
    )
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()
    print(f"Saved heatmap to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate visualizations for RNA-seq DE results"
    )
    parser.add_argument(
        "--results", "-r", required=True,
        help="Path to DE results CSV file"
    )
    parser.add_argument(
        "--adata", "-a",
        help="Path to AnnData file (optional, for heatmap)"
    )
    parser.add_argument(
        "--output", "-o", default="figures",
        help="Output directory for figures (default: figures)"
    )
    parser.add_argument(
        "--padj-threshold", type=float, default=0.05,
        help="Adjusted p-value threshold (default: 0.05)"
    )
    parser.add_argument(
        "--lfc-threshold", type=float, default=1.0,
        help="Log2 fold change threshold (default: 1.0)"
    )
    parser.add_argument(
        "--groupby", default="condition",
        help="Column for heatmap grouping (default: condition)"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load results
    print(f"Loading results from {args.results}...")
    results = pd.read_csv(args.results, index_col=0)
    print(f"  Loaded {len(results)} genes")

    # Generate plots
    print("\nGenerating visualizations...")

    volcano_plot(
        results,
        padj_thresh=args.padj_threshold,
        lfc_thresh=args.lfc_threshold,
        output_path=str(output_dir / "volcano_plot.png")
    )

    ma_plot(
        results,
        padj_thresh=args.padj_threshold,
        output_path=str(output_dir / "ma_plot.png")
    )

    pvalue_histogram(
        results,
        output_path=str(output_dir / "pvalue_hist.png")
    )

    top_genes_barplot(
        results,
        output_path=str(output_dir / "top_genes.png")
    )

    # Heatmap (requires AnnData)
    if args.adata:
        import anndata as ad
        print(f"\nLoading AnnData from {args.adata}...")
        adata = ad.read_h5ad(args.adata)
        heatmap(
            adata,
            results,
            groupby=args.groupby,
            output_path=str(output_dir / "heatmap.png")
        )

    print(f"\nAll figures saved to {output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
