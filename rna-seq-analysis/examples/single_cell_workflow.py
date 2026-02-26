#!/usr/bin/env python3
"""End-to-end single-cell RNA-seq analysis workflow example.

This script demonstrates a complete scRNA-seq analysis pipeline using Scanpy,
from count matrix to clustering and differential expression.

Usage:
    python single_cell_workflow.py --input counts.h5ad --output results/
    python single_cell_workflow.py --input counts_matrix.csv --metadata metadata.csv --output results/
"""

import argparse
from pathlib import Path

import pandas as pd
import numpy as np
import anndata as ad
import scanpy as sc
import matplotlib.pyplot as plt

# Set scanpy settings
sc.settings.verbosity = 2
sc.settings.set_figure_params(dpi=100, frameon=False)


def load_data(input_path: str, metadata_path: str = None) -> ad.AnnData:
    """Load single-cell data into AnnData format."""
    print("=" * 60)
    print("STEP 1: Loading Data")
    print("=" * 60)

    if input_path.endswith(".h5ad"):
        adata = ad.read_h5ad(input_path)
    elif input_path.endswith(".csv"):
        counts = pd.read_csv(input_path, index_col=0)
        # Assume genes x cells format
        adata = ad.AnnData(X=counts.T.values,
                           obs=pd.DataFrame(index=counts.columns),
                           var=pd.DataFrame(index=counts.index))

        if metadata_path:
            metadata = pd.read_csv(metadata_path, index_col=0)
            adata.obs = adata.obs.join(metadata)
    else:
        raise ValueError(f"Unsupported file format: {input_path}")

    print(f"Loaded: {adata.n_obs} cells x {adata.n_vars} genes")

    return adata


def quality_control(adata: ad.AnnData, output_dir: Path) -> ad.AnnData:
    """Perform single-cell specific QC and filtering."""
    print("\n" + "=" * 60)
    print("STEP 2: Quality Control")
    print("=" * 60)

    # Annotate mitochondrial genes
    adata.var["mt"] = adata.var_names.str.startswith(("MT-", "mt-"))
    # Annotate ribosomal genes
    adata.var["ribo"] = adata.var_names.str.startswith(("RPS", "RPL", "Rps", "Rpl"))

    # Calculate QC metrics
    sc.pp.calculate_qc_metrics(
        adata, qc_vars=["mt", "ribo"], inplace=True, percent_top=[20]
    )

    # Print QC summary
    print(f"Median genes per cell: {adata.obs['n_genes_by_counts'].median():.0f}")
    print(f"Median UMIs per cell: {adata.obs['total_counts'].median():.0f}")
    print(f"Median MT %: {adata.obs['pct_counts_mt'].median():.1f}%")

    # Generate QC violin plots
    sc.pl.violin(
        adata,
        ["n_genes_by_counts", "total_counts", "pct_counts_mt"],
        jitter=0.4,
        multi_panel=True,
        show=False
    )
    plt.savefig(output_dir / "qc_violin.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Filter cells
    n_cells_before = adata.n_obs

    # Remove cells with too few/many genes (potential empty droplets or doublets)
    sc.pp.filter_cells(adata, min_genes=200)
    sc.pp.filter_cells(adata, max_genes=5000)  # Adjust based on your data

    # Remove cells with high MT content (dying cells)
    adata = adata[adata.obs["pct_counts_mt"] < 20, :]

    # Remove genes expressed in too few cells
    sc.pp.filter_genes(adata, min_cells=3)

    print(f"\nAfter filtering: {adata.n_obs} cells ({n_cells_before - adata.n_obs} removed)")
    print(f"Genes retained: {adata.n_vars}")

    return adata


def normalize_and_hvg(adata: ad.AnnData) -> ad.AnnData:
    """Normalize, log-transform, and identify highly variable genes."""
    print("\n" + "=" * 60)
    print("STEP 3: Normalization and HVG Selection")
    print("=" * 60)

    # Store raw counts
    adata.layers["counts"] = adata.X.copy()

    # Normalize to 10,000 counts per cell
    sc.pp.normalize_total(adata, target_sum=1e4)

    # Log transform
    sc.pp.log1p(adata)

    # Store normalized data
    adata.raw = adata

    # Identify highly variable genes
    sc.pp.highly_variable_genes(
        adata,
        n_top_genes=2000,
        subset=False,
        flavor="seurat_v3",
        layer="counts"
    )

    n_hvg = adata.var["highly_variable"].sum()
    print(f"Highly variable genes: {n_hvg}")

    return adata


def dimensionality_reduction(adata: ad.AnnData, output_dir: Path) -> ad.AnnData:
    """Perform PCA and UMAP for visualization."""
    print("\n" + "=" * 60)
    print("STEP 4: Dimensionality Reduction")
    print("=" * 60)

    # Subset to HVGs for PCA
    adata_hvg = adata[:, adata.var["highly_variable"]].copy()

    # Scale data
    sc.pp.scale(adata_hvg, max_value=10)

    # PCA
    sc.tl.pca(adata_hvg, svd_solver="arpack", n_comps=50)

    # Copy PCA results back
    adata.obsm["X_pca"] = adata_hvg.obsm["X_pca"]
    adata.uns["pca"] = adata_hvg.uns["pca"]

    # Elbow plot
    sc.pl.pca_variance_ratio(adata, n_pcs=50, show=False)
    plt.savefig(output_dir / "pca_variance.png", dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Variance explained by top 20 PCs: {adata.uns['pca']['variance_ratio'][:20].sum():.1%}")

    # Compute neighbors
    sc.pp.neighbors(adata, n_neighbors=15, n_pcs=30)

    # UMAP
    sc.tl.umap(adata)

    print("UMAP embedding computed")

    return adata


def clustering(adata: ad.AnnData, output_dir: Path, resolution: float = 0.5) -> ad.AnnData:
    """Perform Leiden clustering."""
    print("\n" + "=" * 60)
    print("STEP 5: Clustering")
    print("=" * 60)

    # Leiden clustering
    sc.tl.leiden(adata, resolution=resolution)

    n_clusters = adata.obs["leiden"].nunique()
    print(f"Found {n_clusters} clusters at resolution {resolution}")

    # Cluster sizes
    cluster_counts = adata.obs["leiden"].value_counts().sort_index()
    print("\nCluster sizes:")
    for cluster, count in cluster_counts.items():
        print(f"  Cluster {cluster}: {count} cells ({count/adata.n_obs*100:.1f}%)")

    # UMAP colored by clusters
    sc.pl.umap(adata, color=["leiden"], show=False, legend_loc="on data")
    plt.savefig(output_dir / "umap_clusters.png", dpi=300, bbox_inches="tight")
    plt.close()

    return adata


def find_marker_genes(adata: ad.AnnData, output_dir: Path) -> pd.DataFrame:
    """Find differentially expressed marker genes for each cluster."""
    print("\n" + "=" * 60)
    print("STEP 6: Marker Gene Identification")
    print("=" * 60)

    # Wilcoxon rank-sum test
    sc.tl.rank_genes_groups(adata, groupby="leiden", method="wilcoxon")

    # Get results as DataFrame
    markers = sc.get.rank_genes_groups_df(adata, group=None)

    # Save all markers
    markers.to_csv(output_dir / "marker_genes.csv", index=False)

    # Print top markers per cluster
    print("\nTop 5 markers per cluster:")
    for cluster in adata.obs["leiden"].unique():
        cluster_markers = markers[markers["group"] == cluster].head(5)
        top_genes = cluster_markers["names"].tolist()
        print(f"  Cluster {cluster}: {', '.join(top_genes)}")

    # Generate heatmap of top markers
    sc.pl.rank_genes_groups_heatmap(
        adata,
        n_genes=5,
        show=False,
        show_gene_labels=True
    )
    plt.savefig(output_dir / "marker_heatmap.png", dpi=300, bbox_inches="tight")
    plt.close()

    # Dot plot
    top_markers = markers.groupby("group").head(3)["names"].tolist()
    sc.pl.dotplot(adata, var_names=top_markers[:30], groupby="leiden", show=False)
    plt.savefig(output_dir / "marker_dotplot.png", dpi=300, bbox_inches="tight")
    plt.close()

    return markers


def differential_expression_between_conditions(
    adata: ad.AnnData,
    condition_col: str,
    output_dir: Path
) -> pd.DataFrame:
    """Perform DE analysis between conditions within each cluster."""
    print("\n" + "=" * 60)
    print("STEP 7: Differential Expression Between Conditions")
    print("=" * 60)

    if condition_col not in adata.obs.columns:
        print(f"Condition column '{condition_col}' not found, skipping...")
        return None

    conditions = adata.obs[condition_col].unique()
    if len(conditions) != 2:
        print(f"Expected 2 conditions, found {len(conditions)}, skipping...")
        return None

    all_results = []

    for cluster in adata.obs["leiden"].unique():
        # Subset to cluster
        adata_cluster = adata[adata.obs["leiden"] == cluster].copy()

        # Run DE
        sc.tl.rank_genes_groups(
            adata_cluster,
            groupby=condition_col,
            method="wilcoxon"
        )

        # Get results
        de_results = sc.get.rank_genes_groups_df(adata_cluster, group=conditions[0])
        de_results["cluster"] = cluster

        all_results.append(de_results)

    # Combine results
    combined = pd.concat(all_results, ignore_index=True)
    combined.to_csv(output_dir / "de_between_conditions.csv", index=False)

    print(f"DE analysis complete for {len(adata.obs['leiden'].unique())} clusters")

    return combined


def main():
    parser = argparse.ArgumentParser(
        description="End-to-end single-cell RNA-seq analysis workflow"
    )
    parser.add_argument("--input", "-i", required=True,
                        help="Input file (h5ad or CSV)")
    parser.add_argument("--metadata", "-m",
                        help="Metadata CSV (if input is count matrix)")
    parser.add_argument("--output", "-o", default="sc_results",
                        help="Output directory")
    parser.add_argument("--condition",
                        help="Condition column for DE between groups")
    parser.add_argument("--resolution", type=float, default=0.5,
                        help="Clustering resolution (default: 0.5)")

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set figure output directory
    sc.settings.figdir = output_dir

    # Run pipeline
    adata = load_data(args.input, args.metadata)
    adata = quality_control(adata, output_dir)
    adata = normalize_and_hvg(adata)
    adata = dimensionality_reduction(adata, output_dir)
    adata = clustering(adata, output_dir, resolution=args.resolution)
    markers = find_marker_genes(adata, output_dir)

    if args.condition:
        differential_expression_between_conditions(adata, args.condition, output_dir)

    # Save processed data
    adata.write_h5ad(output_dir / "processed_data.h5ad")

    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")
    print("\nFiles created:")
    for f in sorted(output_dir.glob("*")):
        print(f"  - {f.name}")

    print("\nNext steps:")
    print("  1. Review UMAP and cluster assignments")
    print("  2. Annotate clusters based on marker genes")
    print("  3. Perform trajectory analysis if needed (use scanpy or scvelo)")


if __name__ == "__main__":
    main()
