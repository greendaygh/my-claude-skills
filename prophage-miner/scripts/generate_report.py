"""Analysis report and catalog generation for prophage-miner.

Reads graph nodes/edges and produces:
- prophage_catalog.json: discovered prophages with hosts, genes
- host_range_matrix.json: host-prophage distribution
- gene_inventory.json: gene/protein inventory by category
- research_report.md: markdown summary report
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def build_prophage_catalog(nodes: list[dict], edges: list[dict]) -> dict:
    """Build prophage catalog from graph nodes and edges."""
    prophages = [n for n in nodes if n["label"] == "Prophage"]
    encodes_map: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        if e["type"] == "ENCODES":
            gene_node = next((n for n in nodes if n["id"] == e["to_id"]), None)
            if gene_node:
                encodes_map[e["from_id"]].append(gene_node["properties"].get("name", ""))

    catalog_entries = []
    for p in prophages:
        entry = {
            "name": p["properties"].get("name", ""),
            "host_organism": p["properties"].get("host_organism", ""),
            "genome_size_kb": p["properties"].get("genome_size_kb"),
            "completeness": p["properties"].get("completeness", ""),
            "source_papers": p["source_papers"],
            "encoded_genes": encodes_map.get(p["id"], []),
        }
        catalog_entries.append(entry)

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_prophages": len(catalog_entries),
        "prophages": catalog_entries,
    }


def _get_host_name(node: dict) -> str:
    """Get host display name from properties (species or name fallback)."""
    props = node.get("properties", {})
    return props.get("species", "") or props.get("name", "")


def build_host_range_matrix(nodes: list[dict], edges: list[dict]) -> dict:
    """Build host-prophage distribution matrix."""
    hosts = [n for n in nodes if n["label"] == "Host"]
    prophages = [n for n in nodes if n["label"] == "Prophage"]

    host_names = sorted({_get_host_name(h) for h in hosts} - {""})
    prophage_names = sorted({p["properties"].get("name", "") for p in prophages} - {""})

    matrix: dict[str, dict[str, bool]] = {h: {p: False for p in prophage_names} for h in host_names}

    integrates = [e for e in edges if e["type"] in ("INTEGRATES_INTO", "INFECTS")]
    for edge in integrates:
        from_node = next((n for n in nodes if n["id"] == edge["from_id"]), None)
        to_node = next((n for n in nodes if n["id"] == edge["to_id"]), None)
        if not from_node or not to_node:
            continue
        # Determine which node is Prophage and which is Host
        if from_node["label"] == "Prophage" and to_node["label"] == "Host":
            pname = from_node["properties"].get("name", "")
            hname = _get_host_name(to_node)
        elif from_node["label"] == "Host" and to_node["label"] == "Prophage":
            hname = _get_host_name(from_node)
            pname = to_node["properties"].get("name", "")
        else:
            continue
        if hname in matrix and pname in matrix.get(hname, {}):
            matrix[hname][pname] = True

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "hosts": host_names,
        "prophages": prophage_names,
        "matrix": matrix,
    }


def build_gene_inventory(nodes: list[dict]) -> dict:
    """Build gene inventory categorized by function."""
    genes = [n for n in nodes if n["label"] == "Gene"]

    by_category: dict[str, list[dict]] = defaultdict(list)
    for g in genes:
        cat = g["properties"].get("category", "unknown")
        by_category[cat].append({
            "name": g["properties"].get("name", ""),
            "function": g["properties"].get("function", ""),
            "source_papers": g["source_papers"],
            "merged_count": g["merged_count"],
        })

    return {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_genes": len(genes),
        "by_category": dict(by_category),
    }


def generate_markdown_report(
    catalog: dict,
    matrix: dict,
    inventory: dict,
) -> str:
    """Generate markdown research report."""
    lines = [
        "# Prophage Research Report",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Summary",
        "",
        f"- **Total prophages identified**: {catalog['total_prophages']}",
        f"- **Total host species**: {len(matrix['hosts'])}",
        f"- **Total genes cataloged**: {inventory['total_genes']}",
        "",
        "## Prophage Catalog",
        "",
        "| Prophage | Host | Size (kb) | Completeness | Genes | Papers |",
        "|----------|------|-----------|-------------|-------|--------|",
    ]

    for p in catalog["prophages"]:
        genes_str = ", ".join(p["encoded_genes"][:5])
        if len(p["encoded_genes"]) > 5:
            genes_str += "..."
        papers_str = ", ".join(p["source_papers"])
        lines.append(
            f"| {p['name']} | {p['host_organism']} | "
            f"{p.get('genome_size_kb', 'N/A')} | {p['completeness']} | "
            f"{genes_str} | {papers_str} |"
        )

    lines.extend(["", "## Host Range", ""])
    if matrix["matrix"]:
        header = "| Host | " + " | ".join(matrix["prophages"]) + " |"
        separator = "|------|" + "|".join(["---"] * len(matrix["prophages"])) + "|"
        lines.append(header)
        lines.append(separator)
        for host in matrix["hosts"]:
            row = f"| {host} |"
            for phage in matrix["prophages"]:
                row += " + |" if matrix["matrix"][host][phage] else " - |"
            lines.append(row)

    lines.extend(["", "## Gene Inventory", ""])
    for cat, genes in inventory["by_category"].items():
        lines.append(f"### {cat.capitalize()} ({len(genes)} genes)")
        lines.append("")
        for g in genes:
            lines.append(f"- **{g['name']}**: {g.get('function', 'N/A')} (papers: {', '.join(g['source_papers'])})")
        lines.append("")

    return "\n".join(lines)


def generate_reports(graph_dir: Path, output_dir: Path):
    """Full report generation pipeline."""
    graph_dir = Path(graph_dir)
    output_dir = Path(output_dir)

    nodes = json.loads((graph_dir / "nodes.json").read_text())
    edges = json.loads((graph_dir / "edges.json").read_text())

    catalog = build_prophage_catalog(nodes, edges)
    matrix = build_host_range_matrix(nodes, edges)
    inventory = build_gene_inventory(nodes)

    analysis_dir = output_dir / "04_analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    (analysis_dir / "prophage_catalog.json").write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
    (analysis_dir / "host_range_matrix.json").write_text(json.dumps(matrix, indent=2, ensure_ascii=False))
    (analysis_dir / "gene_inventory.json").write_text(json.dumps(inventory, indent=2, ensure_ascii=False))

    report_md = generate_markdown_report(catalog, matrix, inventory)
    reports_dir = output_dir / "05_reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "research_report.md").write_text(report_md)

    print(
        f"[generate_report] Reports saved: "
        f"{catalog['total_prophages']} prophages, "
        f"{len(matrix['hosts'])} hosts, "
        f"{inventory['total_genes']} genes",
        file=sys.stderr,
    )


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate prophage analysis reports")
    parser.add_argument("--input", type=Path, required=True, help="Graph directory")
    parser.add_argument("--output", type=Path, required=True, help="Output directory (~/dev/phage)")
    args = parser.parse_args()

    generate_reports(args.input, args.output)


if __name__ == "__main__":
    main()
