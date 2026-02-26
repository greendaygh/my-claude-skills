#!/usr/bin/env python3
"""Normalize RNA-seq count data using various methods.

Usage:
    python normalize_counts.py --input data.h5ad --method tpm --gene-lengths lengths.csv
    python normalize_counts.py --input data.h5ad --method vst --output normalized.h5ad
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
import anndata as ad


def normalize_tpm(counts: np.ndarray, gene_lengths: np.ndarray) -> np.ndarray:
    """Normalize to Transcripts Per Million (TPM).

    TPM = (reads / gene_length) / sum(reads / gene_length) * 1e6
    """
    # Reads per kilobase
    rpk = counts / (gene_lengths / 1000)

    # Scale to million
    tpm = rpk / rpk.sum(axis=1, keepdims=True) * 1e6

    return tpm


def normalize_fpkm(counts: np.ndarray, gene_lengths: np.ndarray) -> np.ndarray:
    """Normalize to Fragments Per Kilobase Million (FPKM).

    FPKM = (reads * 1e9) / (gene_length * total_reads)
    """
    total_counts = counts.sum(axis=1, keepdims=True)
    fpkm = (counts * 1e9) / (gene_lengths * total_counts)

    return fpkm


def normalize_cpm(counts: np.ndarray) -> np.ndarray:
    """Normalize to Counts Per Million (CPM)."""
    total_counts = counts.sum(axis=1, keepdims=True)
    cpm = counts / total_counts * 1e6

    return cpm


def normalize_deseq2(counts: np.ndarray) -> np.ndarray:
    """DESeq2-style median-of-ratios normalization.

    Note: This implements the DESeq2 algorithm correctly by computing
    geometric means using only non-zero values, matching the original
    R implementation.
    """
    # Calculate geometric mean per gene using only non-zero values
    # (DESeq2 excludes zeros from geometric mean calculation)
    with np.errstate(divide='ignore'):
        log_counts = np.log(counts)
        log_counts[~np.isfinite(log_counts)] = np.nan

    # Geometric mean: exp(mean(log(x))) for non-zero values only
    geo_means = np.exp(np.nanmean(log_counts, axis=0))

    # Genes with all zeros get geo_mean of 0; exclude from ratio calculation
    valid_genes = geo_means > 0

    # Calculate size factors using median of ratios for valid genes
    ratios = counts[:, valid_genes] / geo_means[valid_genes]
    size_factors = np.median(ratios, axis=1)

    # Handle edge case where size factor is 0 or inf
    size_factors[size_factors == 0] = 1
    size_factors[~np.isfinite(size_factors)] = 1

    # Normalize
    normalized = counts / size_factors[:, np.newaxis]

    return normalized


def normalize_vst(adata: ad.AnnData) -> ad.AnnData:
    """Variance Stabilizing Transformation using PyDESeq2."""
    from pydeseq2.dds import DeseqDataSet

    # Prepare count matrix
    count_matrix = pd.DataFrame(
        adata.X if not hasattr(adata.X, "toarray") else adata.X.toarray(),
        index=adata.obs_names,
        columns=adata.var_names
    ).astype(int)

    # Create minimal metadata if not present
    if adata.obs.shape[1] == 0:
        adata.obs["sample"] = adata.obs_names

    # Create DESeq dataset
    dds = DeseqDataSet(
        counts=count_matrix,
        metadata=adata.obs,
        design_factors=list(adata.obs.columns)[0]
    )

    # Fit size factors
    dds.fit_size_factors()

    # VST transformation
    dds.vst_fit()
    vst_counts = dds.layers["vst_counts"]

    # Create new AnnData with VST values
    adata_vst = adata.copy()
    adata_vst.X = vst_counts
    adata_vst.layers["raw_counts"] = adata.X.copy()

    return adata_vst


def main():
    parser = argparse.ArgumentParser(
        description="Normalize RNA-seq count data"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to AnnData file (.h5ad) or count matrix (CSV)"
    )
    parser.add_argument(
        "--method", "-m", required=True,
        choices=["tpm", "fpkm", "cpm", "deseq2", "vst", "log1p"],
        help="Normalization method"
    )
    parser.add_argument(
        "--gene-lengths", "-l",
        help="Path to gene lengths file (required for TPM/FPKM)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output path (default: input_normalized.h5ad)"
    )
    parser.add_argument(
        "--log-transform", action="store_true",
        help="Apply log2(x+1) transformation after normalization"
    )

    args = parser.parse_args()

    # Set default output
    if args.output is None:
        input_path = Path(args.input)
        args.output = str(input_path.parent / f"{input_path.stem}_{args.method}.h5ad")

    # Load data
    print(f"Loading data from {args.input}...")
    if args.input.endswith(".h5ad"):
        adata = ad.read_h5ad(args.input)
    else:
        counts = pd.read_csv(args.input, index_col=0)
        adata = ad.AnnData(X=counts.T.values, obs=pd.DataFrame(index=counts.columns), var=pd.DataFrame(index=counts.index))

    print(f"  Shape: {adata.n_obs} samples x {adata.n_vars} genes")

    # Store raw counts
    adata.layers["raw_counts"] = adata.X.copy()

    # Get counts as numpy array
    if hasattr(adata.X, "toarray"):
        counts = adata.X.toarray()
    else:
        counts = adata.X.copy()

    # Load gene lengths if needed
    if args.method in ["tpm", "fpkm"]:
        if args.gene_lengths is None:
            print("ERROR: Gene lengths required for TPM/FPKM normalization", file=sys.stderr)
            sys.exit(1)

        lengths_df = pd.read_csv(args.gene_lengths, index_col=0)
        # Align gene lengths with AnnData genes
        common_genes = adata.var_names.intersection(lengths_df.index)
        if len(common_genes) < len(adata.var_names):
            print(f"WARNING: Only {len(common_genes)}/{adata.n_vars} genes have length information")

        adata = adata[:, common_genes]
        counts = counts[:, adata.var_names.isin(common_genes)]
        gene_lengths = lengths_df.loc[common_genes].values.flatten()

    # Normalize
    print(f"\nApplying {args.method} normalization...")

    if args.method == "tpm":
        normalized = normalize_tpm(counts, gene_lengths)
    elif args.method == "fpkm":
        normalized = normalize_fpkm(counts, gene_lengths)
    elif args.method == "cpm":
        normalized = normalize_cpm(counts)
    elif args.method == "deseq2":
        normalized = normalize_deseq2(counts)
    elif args.method == "vst":
        adata = normalize_vst(adata)
        normalized = adata.X
    elif args.method == "log1p":
        normalized = np.log1p(counts)

    # Apply log transform if requested (except for vst/log1p which are already transformed)
    if args.log_transform and args.method not in ["vst", "log1p"]:
        print("Applying log2(x+1) transformation...")
        normalized = np.log2(normalized + 1)

    # Update AnnData
    if args.method != "vst":
        adata.X = normalized

    # Print summary
    print(f"\nNormalization summary:")
    print(f"  Method: {args.method}")
    print(f"  Min value: {adata.X.min():.4f}")
    print(f"  Max value: {adata.X.max():.4f}")
    print(f"  Mean value: {adata.X.mean():.4f}")

    # Save
    print(f"\nSaving to {args.output}...")
    adata.write_h5ad(args.output)

    print("Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
