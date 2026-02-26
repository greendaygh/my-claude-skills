#!/usr/bin/env python3
"""Load and validate RNA-seq count matrices into AnnData format.

Usage:
    python load_counts.py --input counts.csv --metadata metadata.csv --output data.h5ad
    python load_counts.py --input counts.tsv --metadata metadata.csv --format tsv
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import anndata as ad


def load_count_matrix(input_path: str, file_format: str = "csv") -> pd.DataFrame:
    """Load count matrix from file."""
    sep = "\t" if file_format == "tsv" else ","
    counts = pd.read_csv(input_path, index_col=0, sep=sep)
    return counts


def validate_counts(counts: pd.DataFrame) -> list:
    """Validate count matrix and return list of issues."""
    issues = []

    # Check for negative values
    if (counts.values < 0).any():
        issues.append("ERROR: Count matrix contains negative values")

    # Check for non-integer values (warning only)
    if not (counts.values == counts.values.astype(int)).all():
        issues.append("WARNING: Count matrix contains non-integer values (will be rounded)")

    # Check for empty rows/columns
    if (counts.sum(axis=1) == 0).any():
        n_empty = (counts.sum(axis=1) == 0).sum()
        issues.append(f"WARNING: {n_empty} genes have zero counts across all samples")

    if (counts.sum(axis=0) == 0).any():
        n_empty = (counts.sum(axis=0) == 0).sum()
        issues.append(f"ERROR: {n_empty} samples have zero total counts")

    return issues


def create_anndata(counts: pd.DataFrame, metadata: pd.DataFrame) -> ad.AnnData:
    """Create AnnData object from counts and metadata."""
    # Ensure counts are genes x samples, transpose if needed
    if len(counts.index) < len(counts.columns):
        print("Note: Transposing count matrix (assuming genes should be rows)")
        counts = counts.T

    # Align samples between counts and metadata
    common_samples = counts.columns.intersection(metadata.index)
    if len(common_samples) == 0:
        raise ValueError("No matching sample IDs between counts and metadata")

    if len(common_samples) < len(counts.columns):
        print(f"WARNING: Only {len(common_samples)}/{len(counts.columns)} samples have metadata")

    counts = counts[common_samples]
    metadata = metadata.loc[common_samples]

    # Create AnnData (samples x genes)
    adata = ad.AnnData(
        X=counts.T.values,
        obs=metadata,
        var=pd.DataFrame(index=counts.index)
    )
    adata.var_names_make_unique()

    return adata


def main():
    parser = argparse.ArgumentParser(
        description="Load and validate RNA-seq count matrices"
    )
    parser.add_argument(
        "--input", "-i", required=True,
        help="Path to count matrix file (CSV or TSV)"
    )
    parser.add_argument(
        "--metadata", "-m", required=True,
        help="Path to sample metadata file (CSV)"
    )
    parser.add_argument(
        "--output", "-o", default="data.h5ad",
        help="Output path for AnnData file (default: data.h5ad)"
    )
    parser.add_argument(
        "--format", "-f", choices=["csv", "tsv"], default="csv",
        help="Input file format (default: csv)"
    )

    args = parser.parse_args()

    # Check input files exist
    if not Path(args.input).exists():
        print(f"ERROR: Count matrix not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if not Path(args.metadata).exists():
        print(f"ERROR: Metadata file not found: {args.metadata}", file=sys.stderr)
        sys.exit(1)

    # Load data
    print(f"Loading count matrix from {args.input}...")
    counts = load_count_matrix(args.input, args.format)
    print(f"  Shape: {counts.shape[0]} genes x {counts.shape[1]} samples")

    print(f"Loading metadata from {args.metadata}...")
    metadata = pd.read_csv(args.metadata, index_col=0)
    print(f"  Samples: {len(metadata)}")
    print(f"  Columns: {list(metadata.columns)}")

    # Validate
    print("\nValidating count matrix...")
    issues = validate_counts(counts)
    for issue in issues:
        print(f"  {issue}")

    if any("ERROR" in issue for issue in issues):
        print("\nValidation failed with errors.", file=sys.stderr)
        sys.exit(1)

    # Create AnnData
    print("\nCreating AnnData object...")
    adata = create_anndata(counts, metadata)
    print(f"  Final shape: {adata.n_obs} samples x {adata.n_vars} genes")

    # Save
    print(f"\nSaving to {args.output}...")
    adata.write_h5ad(args.output)
    print("Done!")

    return 0


if __name__ == "__main__":
    sys.exit(main())
