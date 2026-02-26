#!/usr/bin/env python3
"""Run differential expression analysis using PyDESeq2.

Usage:
    python run_deseq2.py --input data.h5ad --design condition --contrast condition treatment control
    python run_deseq2.py --input data.h5ad --design "condition + batch" --contrast condition treatment control
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import anndata as ad
import numpy as np


def run_deseq2_analysis(
    adata: ad.AnnData,
    design_factors: str,
    contrast: tuple,
    min_counts: int = 10
) -> pd.DataFrame:
    """Run DESeq2 analysis and return results DataFrame."""
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats

    # Get count matrix (samples x genes)
    if "counts" in adata.layers:
        count_matrix = pd.DataFrame(
            adata.layers["counts"],
            index=adata.obs_names,
            columns=adata.var_names
        )
    else:
        count_matrix = pd.DataFrame(
            adata.X,
            index=adata.obs_names,
            columns=adata.var_names
        )

    # Ensure integer counts
    count_matrix = count_matrix.round().astype(int)

    # Filter low-count genes
    gene_counts = count_matrix.sum(axis=0)
    keep_genes = gene_counts >= min_counts
    count_matrix = count_matrix.loc[:, keep_genes]
    print(f"Keeping {keep_genes.sum()}/{len(keep_genes)} genes with >= {min_counts} counts")

    # Parse design factors
    design_list = [f.strip() for f in design_factors.replace("+", ",").split(",")]
    design_list = [f for f in design_list if f]  # Remove empty strings

    # Create DESeq dataset
    print(f"Creating DESeq2 dataset with design: {design_list}")
    dds = DeseqDataSet(
        counts=count_matrix,
        metadata=adata.obs,
        design_factors=design_list
    )

    # Run DESeq2
    print("Running DESeq2 pipeline...")
    dds.deseq2()

    # Extract results for contrast
    factor, level1, level2 = contrast
    print(f"Extracting results for contrast: {factor} ({level1} vs {level2})")

    stat_res = DeseqStats(dds, contrast=[factor, level1, level2])
    stat_res.summary()

    results_df = stat_res.results_df.copy()
    results_df = results_df.sort_values("padj")

    return results_df


def summarize_results(results_df: pd.DataFrame, padj_thresh: float = 0.05, lfc_thresh: float = 1.0):
    """Print summary of DE results."""
    sig = results_df[
        (results_df["padj"] < padj_thresh) &
        (abs(results_df["log2FoldChange"]) > lfc_thresh)
    ]

    up = sig[sig["log2FoldChange"] > 0]
    down = sig[sig["log2FoldChange"] < 0]

    print("\n" + "=" * 50)
    print("DIFFERENTIAL EXPRESSION SUMMARY")
    print("=" * 50)
    print(f"Thresholds: padj < {padj_thresh}, |log2FC| > {lfc_thresh}")
    print(f"Total genes tested: {len(results_df)}")
    print(f"Significant genes: {len(sig)}")
    print(f"  - Upregulated: {len(up)}")
    print(f"  - Downregulated: {len(down)}")
    print("=" * 50)

    if len(sig) > 0:
        print("\nTop 10 significant genes:")
        top10 = sig.head(10)[["log2FoldChange", "pvalue", "padj"]]
        print(top10.to_string())


def main():
    parser = argparse.ArgumentParser(
        description="Run differential expression analysis with PyDESeq2"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to AnnData file (.h5ad)"
    )
    parser.add_argument(
        "--design", "-d", required=True,
        help="Design formula (e.g., 'condition' or 'condition + batch')"
    )
    parser.add_argument(
        "--contrast", "-c", nargs=3, required=True,
        metavar=("FACTOR", "LEVEL1", "LEVEL2"),
        help="Contrast specification: factor level1 level2 (level1 vs level2)"
    )
    parser.add_argument(
        "--output", "-o", default="de_results.csv",
        help="Output path for results CSV (default: de_results.csv)"
    )
    parser.add_argument(
        "--min-counts", type=int, default=10,
        help="Minimum total counts to keep a gene (default: 10)"
    )
    parser.add_argument(
        "--padj-threshold", type=float, default=0.05,
        help="Adjusted p-value threshold (default: 0.05)"
    )
    parser.add_argument(
        "--lfc-threshold", type=float, default=1.0,
        help="Log2 fold change threshold (default: 1.0)"
    )

    args = parser.parse_args()

    # Check input file
    if not Path(args.input).exists():
        print(f"ERROR: Input file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    # Load data
    print(f"Loading data from {args.input}...")
    adata = ad.read_h5ad(args.input)
    print(f"  Shape: {adata.n_obs} samples x {adata.n_vars} genes")

    # Check contrast factor exists
    factor = args.contrast[0]
    if factor not in adata.obs.columns:
        print(f"ERROR: Factor '{factor}' not found in metadata", file=sys.stderr)
        print(f"Available columns: {list(adata.obs.columns)}", file=sys.stderr)
        sys.exit(1)

    # Check contrast levels exist
    levels = adata.obs[factor].unique()
    for level in args.contrast[1:]:
        if level not in levels:
            print(f"ERROR: Level '{level}' not found in factor '{factor}'", file=sys.stderr)
            print(f"Available levels: {list(levels)}", file=sys.stderr)
            sys.exit(1)

    # Run analysis
    results_df = run_deseq2_analysis(
        adata,
        design_factors=args.design,
        contrast=tuple(args.contrast),
        min_counts=args.min_counts
    )

    # Summarize
    summarize_results(results_df, args.padj_threshold, args.lfc_threshold)

    # Save results
    print(f"\nSaving results to {args.output}...")
    results_df.to_csv(args.output)

    # Save significant genes separately
    sig_output = args.output.replace(".csv", "_significant.csv")
    sig = results_df[
        (results_df["padj"] < args.padj_threshold) &
        (abs(results_df["log2FoldChange"]) > args.lfc_threshold)
    ]
    sig.to_csv(sig_output)
    print(f"Saved {len(sig)} significant genes to {sig_output}")

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
