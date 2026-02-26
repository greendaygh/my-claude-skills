#!/usr/bin/env python3
"""Gene set enrichment and pathway analysis for RNA-seq results.

Usage:
    python pathway_analysis.py --genes sig_genes.csv --database GO_Biological_Process_2021
    python pathway_analysis.py --genes de_results.csv --method gsea --database KEGG_2021_Human
"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np


def run_enrichr(gene_list: list, gene_sets: str, output_dir: Path) -> pd.DataFrame:
    """Run over-representation analysis using Enrichr."""
    import gseapy as gp

    print(f"Running Enrichr analysis with {len(gene_list)} genes...")
    print(f"Gene set database: {gene_sets}")

    enr = gp.enrichr(
        gene_list=gene_list,
        gene_sets=gene_sets,
        organism="Human",
        outdir=str(output_dir),
        cutoff=0.05
    )

    results = enr.results
    results = results.sort_values("Adjusted P-value")

    return results


def run_gsea(
    ranked_genes: pd.DataFrame,
    gene_sets: str,
    output_dir: Path,
    min_size: int = 15,
    max_size: int = 500
) -> pd.DataFrame:
    """Run Gene Set Enrichment Analysis on ranked gene list."""
    import gseapy as gp

    print(f"Running GSEA with {len(ranked_genes)} ranked genes...")
    print(f"Gene set database: {gene_sets}")

    # Prepare ranked list
    if "log2FoldChange" in ranked_genes.columns and "pvalue" in ranked_genes.columns:
        # Create ranking metric: sign(log2FC) * -log10(pvalue)
        ranked_genes["rank_metric"] = (
            np.sign(ranked_genes["log2FoldChange"]) *
            -np.log10(ranked_genes["pvalue"].clip(1e-300))
        )
        rnk = ranked_genes["rank_metric"].sort_values(ascending=False)
    else:
        # Assume first column is the ranking metric
        rnk = ranked_genes.iloc[:, 0].sort_values(ascending=False)

    pre_res = gp.prerank(
        rnk=rnk,
        gene_sets=gene_sets,
        min_size=min_size,
        max_size=max_size,
        permutation_num=1000,
        outdir=str(output_dir),
        seed=42,
        verbose=True
    )

    results = pre_res.res2d
    results = results.sort_values("FDR q-val")

    return results


def plot_enrichment_dotplot(results: pd.DataFrame, output_path: str, top_n: int = 20):
    """Generate dot plot for enrichment results."""
    import matplotlib.pyplot as plt

    df = results.head(top_n).copy()

    if "Adjusted P-value" in df.columns:
        pval_col = "Adjusted P-value"
        size_col = "Odds Ratio" if "Odds Ratio" in df.columns else "Combined Score"
    else:
        pval_col = "FDR q-val"
        size_col = "NES"

    df["-log10(pval)"] = -np.log10(df[pval_col].clip(1e-50))

    fig, ax = plt.subplots(figsize=(10, 8))

    scatter = ax.scatter(
        df["-log10(pval)"],
        range(len(df)),
        s=abs(df[size_col]) * 50,
        c=df[size_col],
        cmap="RdBu_r",
        alpha=0.7
    )

    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["Term"].str[:50])  # Truncate long names
    ax.set_xlabel("-log10(adjusted p-value)")
    ax.set_title("Pathway Enrichment")

    plt.colorbar(scatter, label=size_col)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close()

    print(f"Saved dot plot to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Gene set enrichment and pathway analysis"
    )
    parser.add_argument(
        "--genes", "-g", required=True,
        help="Path to gene list CSV (gene names in first column or index)"
    )
    parser.add_argument(
        "--database", "-d", default="GO_Biological_Process_2021",
        help="Gene set database (default: GO_Biological_Process_2021)"
    )
    parser.add_argument(
        "--method", "-m", choices=["enrichr", "gsea"], default="enrichr",
        help="Analysis method (default: enrichr for ORA)"
    )
    parser.add_argument(
        "--output", "-o", default="pathway_results",
        help="Output directory (default: pathway_results)"
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Number of top pathways to plot (default: 20)"
    )
    parser.add_argument(
        "--organism", default="Human",
        help="Organism for gene set database (default: Human)"
    )

    args = parser.parse_args()

    # Create output directory
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load gene data
    print(f"Loading genes from {args.genes}...")
    gene_df = pd.read_csv(args.genes, index_col=0)

    if args.method == "enrichr":
        # Get gene list (use index if it contains gene names)
        if gene_df.index.dtype == "object":
            gene_list = gene_df.index.tolist()
        else:
            gene_list = gene_df.iloc[:, 0].tolist()

        print(f"Loaded {len(gene_list)} genes")

        # Run Enrichr
        results = run_enrichr(gene_list, args.database, output_dir)

    else:  # gsea
        # Need ranked list with log2FC and pvalue
        if "log2FoldChange" not in gene_df.columns:
            print("ERROR: GSEA requires log2FoldChange column", file=sys.stderr)
            sys.exit(1)

        results = run_gsea(gene_df, args.database, output_dir)

    # Save results
    results_path = output_dir / "enrichment_results.csv"
    results.to_csv(results_path)
    print(f"\nResults saved to {results_path}")

    # Print summary
    print(f"\nTop 10 enriched terms:")
    if "Adjusted P-value" in results.columns:
        top_terms = results.head(10)[["Term", "Adjusted P-value", "Genes"]]
    else:
        top_terms = results.head(10)[["Term", "FDR q-val", "NES"]]
    print(top_terms.to_string())

    # Generate plot
    if len(results) > 0:
        plot_path = output_dir / "enrichment_dotplot.png"
        plot_enrichment_dotplot(results, str(plot_path), args.top_n)

    print("\nDone!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
