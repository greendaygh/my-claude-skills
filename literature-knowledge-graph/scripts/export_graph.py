#!/usr/bin/env python3
from __future__ import annotations
"""Export a Neo4j literature knowledge graph to various formats.

Supported export formats:
  - graphml    : GraphML XML (compatible with Gephi, Cytoscape, yEd)
  - json       : JSON nodes/edges (compatible with D3.js, vis.js)
  - csv        : Two CSV files (nodes + edges)
  - networkx   : Python pickle of a NetworkX MultiDiGraph
  - cytoscape  : Cytoscape.js JSON format (.cyjs)

Usage examples:
  python export_graph.py --password secret --format json --output graph.json
  python export_graph.py --password secret --format csv --output export.csv \\
      --node-types Gene,Disease --min-confidence 0.8
  python export_graph.py --password secret --format graphml --output graph.graphml \\
      --include-provenance
"""

import argparse
import csv
import json
import os
import pickle
import sys
from pathlib import Path

import networkx as nx
from neo4j import GraphDatabase


# ---------------------------------------------------------------------------
# Neo4j helpers
# ---------------------------------------------------------------------------

def _build_node_query(node_types: list[str] | None, include_provenance: bool) -> str:
    """Return a Cypher query that fetches the desired nodes."""
    if node_types:
        labels_clause = " OR ".join(f"n:{label}" for label in node_types)
        if include_provenance and "Paper" not in node_types:
            labels_clause += " OR n:Paper"
        return f"MATCH (n) WHERE {labels_clause} RETURN n"
    if not include_provenance:
        return "MATCH (n) WHERE NOT n:Paper RETURN n"
    return "MATCH (n) RETURN n"


def _build_rel_query(
    node_types: list[str] | None,
    rel_types: list[str] | None,
    include_provenance: bool,
) -> str:
    """Return a Cypher query that fetches the desired relationships."""
    rel_type_clause = ""
    if rel_types:
        allowed = list(rel_types)
        if include_provenance and "EXTRACTED_FROM" not in allowed:
            allowed.append("EXTRACTED_FROM")
        rel_type_clause = ":" + "|".join(allowed)
    elif not include_provenance:
        rel_type_clause = ""  # we filter later

    where_parts: list[str] = []

    if node_types:
        src_labels = " OR ".join(f"a:{l}" for l in node_types)
        tgt_labels = " OR ".join(f"b:{l}" for l in node_types)
        if include_provenance:
            if "Paper" not in node_types:
                src_labels += " OR a:Paper"
                tgt_labels += " OR b:Paper"
        where_parts.append(f"({src_labels})")
        where_parts.append(f"({tgt_labels})")

    if not include_provenance:
        where_parts.append("NOT type(r) = 'EXTRACTED_FROM'")
        where_parts.append("NOT a:Paper")
        where_parts.append("NOT b:Paper")

    where_clause = ""
    if where_parts:
        where_clause = "WHERE " + " AND ".join(where_parts)

    return f"MATCH (a)-[r{rel_type_clause}]->(b) {where_clause} RETURN a, r, b"


def _node_id(node) -> str:
    """Stable string id for a Neo4j node."""
    return str(node.element_id)


def _node_labels(node) -> list[str]:
    """Return sorted list of labels for a Neo4j node."""
    return sorted(node.labels)


def _safe_prop(value):
    """Convert a property value so it is safe for all serialisation targets."""
    if isinstance(value, (list, tuple)):
        return [_safe_prop(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_prop(v) for k, v in value.items()}
    return value


# ---------------------------------------------------------------------------
# Fetch data from Neo4j and build a NetworkX graph
# ---------------------------------------------------------------------------

def fetch_graph(
    uri: str,
    user: str,
    password: str,
    node_types: list[str] | None,
    rel_types: list[str] | None,
    include_provenance: bool,
    min_confidence: float,
) -> nx.MultiDiGraph:
    """Connect to Neo4j, fetch nodes/rels, and return a NetworkX MultiDiGraph."""

    driver = GraphDatabase.driver(uri, auth=(user, password))
    G = nx.MultiDiGraph()

    try:
        with driver.session() as session:
            # -- Nodes -------------------------------------------------------
            node_query = _build_node_query(node_types, include_provenance)
            result = session.run(node_query)
            for record in result:
                node = record["n"]
                nid = _node_id(node)
                props = {k: _safe_prop(v) for k, v in dict(node).items()}

                # Apply confidence filter on nodes
                confidence = props.get("confidence")
                if confidence is not None and float(confidence) < min_confidence:
                    continue

                labels = _node_labels(node)
                primary_label = labels[0] if labels else "Unknown"
                props["_labels"] = "|".join(labels)
                props["label"] = primary_label
                G.add_node(nid, **props)

            # -- Relationships -----------------------------------------------
            rel_query = _build_rel_query(node_types, rel_types, include_provenance)
            result = session.run(rel_query)
            for record in result:
                rel = record["r"]
                src = _node_id(record["a"])
                tgt = _node_id(record["b"])
                rel_type = rel.type
                props = {k: _safe_prop(v) for k, v in dict(rel).items()}

                # Apply confidence filter on relationships
                confidence = props.get("confidence")
                if confidence is not None and float(confidence) < min_confidence:
                    continue

                # Apply rel-types filter (catch-all for non-provenance filtering)
                if rel_types and rel_type not in rel_types:
                    if not (include_provenance and rel_type == "EXTRACTED_FROM"):
                        continue

                # Only add edge if both endpoints exist in the graph
                if src in G and tgt in G:
                    props["type"] = rel_type
                    G.add_edge(src, tgt, key=rel_type, **props)
    finally:
        driver.close()

    return G


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_graphml(G: nx.MultiDiGraph, output: str) -> str:
    """Export graph to GraphML XML format."""
    # NetworkX write_graphml requires all attribute values to be simple types.
    # Convert any lists/dicts to JSON strings for compatibility.
    H = G.copy()
    for _, data in H.nodes(data=True):
        for k, v in list(data.items()):
            if isinstance(v, (list, dict)):
                data[k] = json.dumps(v)
            elif v is None:
                data[k] = ""
    for _, _, data in H.edges(data=True):
        for k, v in list(data.items()):
            if isinstance(v, (list, dict)):
                data[k] = json.dumps(v)
            elif v is None:
                data[k] = ""
    nx.write_graphml(H, output)
    return output


def export_json(G: nx.MultiDiGraph, output: str) -> str:
    """Export graph to JSON {nodes, edges} format."""
    nodes = []
    for nid, data in G.nodes(data=True):
        node_entry = {
            "id": nid,
            "label": data.get("label", "Unknown"),
            "properties": {k: v for k, v in data.items() if k != "label"},
        }
        nodes.append(node_entry)

    edges = []
    for src, tgt, data in G.edges(data=True):
        edge_entry = {
            "source": src,
            "target": tgt,
            "type": data.get("type", "RELATED_TO"),
            "properties": {k: v for k, v in data.items() if k != "type"},
        }
        edges.append(edge_entry)

    payload = {"nodes": nodes, "edges": edges}
    with open(output, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, default=str)
    return output


def export_csv(G: nx.MultiDiGraph, output: str) -> tuple[str, str]:
    """Export graph to two CSV files: *_nodes.csv and *_edges.csv."""
    base, ext = os.path.splitext(output)
    nodes_path = f"{base}_nodes.csv"
    edges_path = f"{base}_edges.csv"

    # Collect all node property keys
    node_prop_keys: set[str] = set()
    for _, data in G.nodes(data=True):
        node_prop_keys.update(data.keys())
    node_prop_keys.discard("label")
    node_prop_keys.discard("name")
    sorted_node_keys = sorted(node_prop_keys)

    with open(nodes_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        header = ["id", "label", "name"] + sorted_node_keys
        writer.writerow(header)
        for nid, data in G.nodes(data=True):
            row = [
                nid,
                data.get("label", ""),
                data.get("name", ""),
            ]
            for k in sorted_node_keys:
                val = data.get(k, "")
                if isinstance(val, (list, dict)):
                    val = json.dumps(val)
                row.append(val)
            writer.writerow(row)

    # Collect all edge property keys
    edge_prop_keys: set[str] = set()
    for _, _, data in G.edges(data=True):
        edge_prop_keys.update(data.keys())
    edge_prop_keys.discard("type")
    sorted_edge_keys = sorted(edge_prop_keys)

    with open(edges_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        header = ["source", "target", "type"] + sorted_edge_keys
        writer.writerow(header)
        for src, tgt, data in G.edges(data=True):
            row = [
                src,
                tgt,
                data.get("type", ""),
            ]
            for k in sorted_edge_keys:
                val = data.get(k, "")
                if isinstance(val, (list, dict)):
                    val = json.dumps(val)
                row.append(val)
            writer.writerow(row)

    return nodes_path, edges_path


def export_networkx(G: nx.MultiDiGraph, output: str) -> str:
    """Export graph as a pickled NetworkX MultiDiGraph (.gpickle)."""
    with open(output, "wb") as fh:
        pickle.dump(G, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return output


def export_cytoscape(G: nx.MultiDiGraph, output: str) -> str:
    """Export graph to Cytoscape.js JSON format (.cyjs)."""
    elements: dict[str, list] = {"nodes": [], "edges": []}

    for nid, data in G.nodes(data=True):
        node_data = {"id": nid}
        node_data["name"] = data.get("name", nid)
        node_data["label"] = data.get("label", "Unknown")
        for k, v in data.items():
            if k not in node_data:
                if isinstance(v, (list, dict)):
                    node_data[k] = json.dumps(v)
                else:
                    node_data[k] = v
        elements["nodes"].append({"data": node_data})

    edge_id = 0
    for src, tgt, data in G.edges(data=True):
        edge_data = {
            "id": f"e{edge_id}",
            "source": src,
            "target": tgt,
            "interaction": data.get("type", "RELATED_TO"),
        }
        for k, v in data.items():
            if k == "type":
                continue
            if k not in edge_data:
                if isinstance(v, (list, dict)):
                    edge_data[k] = json.dumps(v)
                else:
                    edge_data[k] = v
        elements["edges"].append({"data": edge_data})
        edge_id += 1

    cyjs = {
        "format_version": "1.0",
        "generated_by": "export_graph.py",
        "target_cytoscapejs_version": "~3.0",
        "data": {"name": "Literature Knowledge Graph"},
        "elements": elements,
    }

    with open(output, "w", encoding="utf-8") as fh:
        json.dump(cyjs, fh, indent=2, ensure_ascii=False, default=str)
    return output


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary(G: nx.MultiDiGraph, paths: list[str]) -> None:
    """Print a human-readable export summary."""
    node_count = G.number_of_nodes()
    edge_count = G.number_of_edges()

    # Collect label distribution
    label_counts: dict[str, int] = {}
    for _, data in G.nodes(data=True):
        lbl = data.get("label", "Unknown")
        label_counts[lbl] = label_counts.get(lbl, 0) + 1

    # Collect relationship type distribution
    rel_counts: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        rt = data.get("type", "UNKNOWN")
        rel_counts[rt] = rel_counts.get(rt, 0) + 1

    print("\n=== Export Summary ===")
    print(f"Nodes: {node_count}")
    for lbl in sorted(label_counts):
        print(f"  {lbl}: {label_counts[lbl]}")
    print(f"Edges: {edge_count}")
    for rt in sorted(rel_counts):
        print(f"  {rt}: {rel_counts[rt]}")

    total_size = 0
    for p in paths:
        size = os.path.getsize(p)
        total_size += size
        print(f"File: {p} ({_human_size(size)})")
    if len(paths) > 1:
        print(f"Total size: {_human_size(total_size)}")
    print("=====================\n")


def _human_size(nbytes: int) -> str:
    """Return a human-readable file size string."""
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} TB"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a Neo4j literature knowledge graph to various formats.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help="Neo4j connection URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--user",
        default="neo4j",
        help="Neo4j user (default: neo4j)",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Neo4j password",
    )
    parser.add_argument(
        "--format",
        required=False,
        choices=["graphml", "json", "csv", "networkx", "cytoscape"],
        default="json",
        help="Export format (default: json)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output file path",
    )
    parser.add_argument(
        "--node-types",
        default=None,
        help="Comma-separated node labels to include (default: all)",
    )
    parser.add_argument(
        "--rel-types",
        default=None,
        help="Comma-separated relationship types to include (default: all)",
    )
    parser.add_argument(
        "--include-provenance",
        action="store_true",
        default=False,
        help="Include Paper nodes and EXTRACTED_FROM relationships (default: false)",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.0,
        help="Minimum confidence threshold for inclusion (default: 0.0)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    node_types = [t.strip() for t in args.node_types.split(",")] if args.node_types else None
    rel_types = [t.strip() for t in args.rel_types.split(",")] if args.rel_types else None

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    # Step 1-3: Query Neo4j, apply filters, build NetworkX graph
    print(f"Connecting to Neo4j at {args.uri} ...")
    G = fetch_graph(
        uri=args.uri,
        user=args.user,
        password=args.password,
        node_types=node_types,
        rel_types=rel_types,
        include_provenance=args.include_provenance,
        min_confidence=args.min_confidence,
    )
    print(f"Fetched {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # Step 4: Export to requested format
    fmt = args.format
    written_paths: list[str] = []

    if fmt == "graphml":
        path = export_graphml(G, output_path)
        written_paths.append(path)
    elif fmt == "json":
        path = export_json(G, output_path)
        written_paths.append(path)
    elif fmt == "csv":
        nodes_path, edges_path = export_csv(G, output_path)
        written_paths.extend([nodes_path, edges_path])
    elif fmt == "networkx":
        path = export_networkx(G, output_path)
        written_paths.append(path)
    elif fmt == "cytoscape":
        path = export_cytoscape(G, output_path)
        written_paths.append(path)
    else:
        print(f"Error: unsupported format '{fmt}'", file=sys.stderr)
        sys.exit(1)

    # Step 5: Print summary
    print_summary(G, written_paths)


if __name__ == "__main__":
    main()
