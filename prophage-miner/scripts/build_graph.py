"""JSON-based knowledge graph construction with entity merging and export.

Loads per-paper extractions, merges entities, builds edges with averaged
confidence, adds provenance, and exports to JSON, GraphML, and CSV.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import networkx as nx


def load_extractions(
    extractions_dir: Path,
    paper_status: dict | None = None,
) -> list[dict]:
    """Load all extraction JSONs, optionally filtering by paper_status."""
    extractions_dir = Path(extractions_dir)
    files = sorted(extractions_dir.glob("*_extraction.json"))
    results = []
    for f in files:
        data = json.loads(f.read_text())
        paper_id = data.get("paper_id", "")
        if paper_status and paper_id in paper_status:
            if paper_status[paper_id].get("status") == "rejected":
                continue
        results.append(data)
    print(f"[build_graph] Loaded {len(results)} extractions", file=sys.stderr)
    return results


def _entity_key(entity: dict) -> str:
    """Generate a unique key for entity merging."""
    label = entity.get("type", entity.get("label", ""))
    name = entity.get("name", "")
    if not name:
        props = entity.get("properties", {})
        name = props.get("name", props.get("species", props.get("locus", props.get("trigger", ""))))
    props = entity.get("properties", {})
    if label in ("Prophage", "Gene", "Protein") and "host_organism" in props:
        return f"{label}::{name}::{props['host_organism']}"
    return f"{label}::{name}"


def _make_node_id(label: str, name: str) -> str:
    safe = name.lower().replace(" ", "_").replace("-", "_")
    return f"{label.lower()}_{safe}"


def merge_entities(extractions: list[dict]) -> list[dict]:
    """Merge entities across papers by name+organism key."""
    merged: dict[str, dict] = {}

    for ext in extractions:
        paper_id = ext.get("paper_id", "")
        for entity in ext.get("entities", []):
            key = _entity_key(entity)
            if key in merged:
                merged[key]["merged_count"] += 1
                if paper_id not in merged[key]["source_papers"]:
                    merged[key]["source_papers"].append(paper_id)
                for k, v in entity.get("properties", {}).items():
                    if k not in merged[key]["properties"] and v:
                        merged[key]["properties"][k] = v
            else:
                label = entity.get("type", entity.get("label", ""))
                name = entity.get("name", "")
                if not name:
                    props = entity.get("properties", {})
                    name = props.get("name", props.get("species", props.get("locus", props.get("trigger", ""))))
                props = dict(entity.get("properties", {}))
                if name and "name" not in props:
                    props["name"] = name
                merged[key] = {
                    "id": _make_node_id(label, name),
                    "label": label,
                    "properties": props,
                    "source_papers": [paper_id],
                    "merged_count": 1,
                }

    nodes = list(merged.values())
    print(f"[build_graph] Merged into {len(nodes)} unique entities", file=sys.stderr)
    return nodes


def build_edges(extractions: list[dict], nodes: list[dict]) -> list[dict]:
    """Build edges from relationships, averaging confidence across papers."""
    # Build lookup from merged node key to node id
    node_lookup: dict[str, str] = {}
    for n in nodes:
        label = n["label"]
        name = n["properties"].get("name", "")
        key = f"{label}::{name}"
        node_lookup[key] = n["id"]
        if "host_organism" in n["properties"]:
            full_key = f"{label}::{name}::{n['properties']['host_organism']}"
            node_lookup[full_key] = n["id"]

    edge_map: dict[str, dict] = {}

    for ext in extractions:
        paper_id = ext.get("paper_id", "")
        entities = ext.get("entities", [])

        # Build paper-local ID (E001) -> entity key mapping
        local_id_to_key: dict[str, str] = {}
        for entity in entities:
            local_id = entity.get("id", "")
            local_id_to_key[local_id] = _entity_key(entity)

        for rel in ext.get("relationships", []):
            # Support both formats: local IDs (from_id/to_id as "E001")
            # and structured refs (from/to as {label, key})
            from_ref = rel.get("from")
            to_ref = rel.get("to")

            if from_ref and isinstance(from_ref, dict):
                from_key = f"{from_ref.get('label', '')}::{from_ref.get('key', '')}"
                to_key = f"{to_ref.get('label', '')}::{to_ref.get('key', '')}"
            else:
                # Local paper IDs (E001, E002) -> look up entity key
                raw_from = rel.get("from_id", "")
                raw_to = rel.get("to_id", "")
                from_key = local_id_to_key.get(raw_from, "")
                to_key = local_id_to_key.get(raw_to, "")

            from_id = node_lookup.get(from_key)
            to_id = node_lookup.get(to_key)
            if not from_id or not to_id:
                continue

            rel_type = rel.get("type", "")
            edge_key = f"{rel_type}::{from_id}::{to_id}"

            conf = rel.get("confidence", rel.get("properties", {}).get("confidence", 0.5))
            if edge_key in edge_map:
                edge_map[edge_key]["confidences"].append(conf)
                if paper_id not in edge_map[edge_key]["source_papers"]:
                    edge_map[edge_key]["source_papers"].append(paper_id)
                for k, v in rel.get("properties", {}).items():
                    if k not in ("confidence",) and k not in edge_map[edge_key]["properties"]:
                        edge_map[edge_key]["properties"][k] = v
            else:
                props = {k: v for k, v in rel.get("properties", {}).items() if k != "confidence"}
                edge_map[edge_key] = {
                    "id": f"edge_{rel_type.lower()}_{from_id}_{to_id}",
                    "type": rel_type,
                    "from_id": from_id,
                    "to_id": to_id,
                    "properties": props,
                    "confidences": [conf],
                    "source_papers": [paper_id],
                }

    edges = []
    for e in edge_map.values():
        confs = e.pop("confidences")
        e["avg_confidence"] = round(sum(confs) / len(confs), 4) if confs else 0.0
        edges.append(e)

    print(f"[build_graph] Built {len(edges)} edges", file=sys.stderr)
    return edges


def add_provenance(
    nodes: list[dict],
    edges: list[dict],
    extractions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Add Paper nodes and EXTRACTED_FROM edges for provenance tracking."""
    paper_ids = set()
    for ext in extractions:
        paper_ids.add(ext.get("paper_id", ""))

    for pid in paper_ids:
        paper_node = {
            "id": f"paper_{pid.lower()}",
            "label": "Paper",
            "properties": {"paper_id": pid},
            "source_papers": [pid],
            "merged_count": 1,
        }
        nodes.append(paper_node)

    existing_node_ids = {n["id"] for n in nodes}
    for node in list(nodes):
        if node["label"] == "Paper":
            continue
        for pid in node["source_papers"]:
            paper_node_id = f"paper_{pid.lower()}"
            if paper_node_id in existing_node_ids:
                ef_edge = {
                    "id": f"edge_extracted_from_{node['id']}_{paper_node_id}",
                    "type": "EXTRACTED_FROM",
                    "from_id": node["id"],
                    "to_id": paper_node_id,
                    "properties": {},
                    "avg_confidence": 1.0,
                    "source_papers": [pid],
                }
                edges.append(ef_edge)

    return nodes, edges


def build_graph(
    extractions_dir: Path,
    graph_dir: Path,
    paper_status: dict | None = None,
) -> dict:
    """Full graph build pipeline: load -> merge -> edges -> provenance -> save."""
    extractions_dir = Path(extractions_dir)
    graph_dir = Path(graph_dir)
    graph_dir.mkdir(parents=True, exist_ok=True)

    extractions = load_extractions(extractions_dir, paper_status=paper_status)
    nodes = merge_entities(extractions)
    edges = build_edges(extractions, nodes)
    nodes, edges = add_provenance(nodes, edges, extractions)

    (graph_dir / "nodes.json").write_text(json.dumps(nodes, indent=2, ensure_ascii=False))
    (graph_dir / "edges.json").write_text(json.dumps(edges, indent=2, ensure_ascii=False))

    meta = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "total_nodes": len(nodes),
        "total_edges": len(edges),
    }
    (graph_dir / "graph_meta.json").write_text(json.dumps(meta, indent=2))

    exports_dir = graph_dir / "exports"
    exports_dir.mkdir(exist_ok=True)
    export_graphml(nodes, edges, exports_dir / "graph.graphml")
    export_csv(nodes, edges, exports_dir)

    print(
        f"[build_graph] Graph saved: {len(nodes)} nodes, {len(edges)} edges",
        file=sys.stderr,
    )
    return meta


def export_graphml(nodes: list[dict], edges: list[dict], path: Path):
    """Export graph to GraphML format using networkx."""
    G = nx.DiGraph()
    for n in nodes:
        G.add_node(n["id"], label=n["label"], merged_count=n["merged_count"])
    for e in edges:
        G.add_edge(
            e["from_id"],
            e["to_id"],
            type=e["type"],
            avg_confidence=e["avg_confidence"],
        )
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(G, str(path))
    print(f"[build_graph] Exported GraphML: {path}", file=sys.stderr)


def export_csv(nodes: list[dict], edges: list[dict], exports_dir: Path):
    """Export nodes.csv and edges.csv."""
    exports_dir = Path(exports_dir)
    exports_dir.mkdir(parents=True, exist_ok=True)

    with open(exports_dir / "nodes.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "label", "merged_count", "source_papers"])
        for n in nodes:
            writer.writerow([n["id"], n["label"], n["merged_count"], ";".join(n["source_papers"])])

    with open(exports_dir / "edges.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "type", "from_id", "to_id", "avg_confidence", "source_papers"])
        for e in edges:
            writer.writerow([e["id"], e["type"], e["from_id"], e["to_id"], e["avg_confidence"], ";".join(e["source_papers"])])

    print(f"[build_graph] Exported CSV to {exports_dir}", file=sys.stderr)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Build prophage knowledge graph")
    parser.add_argument("--input", type=Path, required=True, help="Extractions directory")
    parser.add_argument("--output", type=Path, required=True, help="Graph output directory")
    parser.add_argument("--registry", type=Path, help="run_registry.json for rejection filter")
    args = parser.parse_args()

    paper_status = None
    if args.registry and args.registry.exists():
        reg = json.loads(args.registry.read_text())
        paper_status = reg.get("paper_status")

    build_graph(args.input, args.output, paper_status=paper_status)


if __name__ == "__main__":
    main()
