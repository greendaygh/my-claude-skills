#!/usr/bin/env python3
from __future__ import annotations
"""CLI tool for querying a Neo4j literature knowledge graph.

Supports multiple query types including statistics, neighbor traversal,
shortest paths, centrality analysis, community detection, and custom Cypher.
"""

import argparse
import csv
import io
import json
import sys
from contextlib import contextmanager

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ServiceUnavailable, AuthError, ClientError
except ImportError:
    print(
        "Error: neo4j driver not installed. Install with: pip install neo4j",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

@contextmanager
def neo4j_session(uri, user, password):
    """Context manager that yields a Neo4j session and closes the driver."""
    driver = None
    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        driver.verify_connectivity()
        with driver.session() as session:
            yield session
    except ServiceUnavailable:
        print(
            f"Error: Could not connect to Neo4j at {uri}. "
            "Is the database running?",
            file=sys.stderr,
        )
        sys.exit(1)
    except AuthError:
        print(
            "Error: Authentication failed. Check your --user and --password.",
            file=sys.stderr,
        )
        sys.exit(1)
    finally:
        if driver is not None:
            driver.close()


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def _format_table(columns, rows):
    """Return a simple ASCII-aligned table string."""
    if not columns:
        return "(no columns)"
    if not rows:
        return _table_header(columns) + "\n(no rows)"

    # Convert every cell to str
    str_rows = [[str(v) for v in row] for row in rows]
    col_widths = [len(c) for c in columns]
    for row in str_rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells):
        parts = []
        for i, cell in enumerate(cells):
            w = col_widths[i] if i < len(col_widths) else len(cell)
            parts.append(cell.ljust(w))
        return "  ".join(parts)

    separator = "  ".join("-" * w for w in col_widths)
    lines = [fmt_row(columns), separator]
    for row in str_rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def _table_header(columns):
    widths = [len(c) for c in columns]
    header = "  ".join(c.ljust(w) for c, w in zip(columns, widths))
    sep = "  ".join("-" * w for w in widths)
    return f"{header}\n{sep}"


def format_output(columns, rows, fmt):
    """Format query results as table, json, or csv."""
    if fmt == "json":
        records = [dict(zip(columns, row)) for row in rows]
        return json.dumps(records, indent=2, default=str)
    elif fmt == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(columns)
        writer.writerows(rows)
        return buf.getvalue().rstrip("\n")
    else:
        return _format_table(columns, rows)


# ---------------------------------------------------------------------------
# Query implementations
# ---------------------------------------------------------------------------

def query_stats(session, limit):
    """Return overall graph statistics."""
    sections = []

    # -- Node counts per label --
    result = session.run(
        "CALL db.labels() YIELD label "
        "CALL { WITH label "
        "  CALL db.schema.nodeTypeProperties() YIELD nodeLabels "
        "  WITH nodeLabels WHERE label IN nodeLabels RETURN count(*) AS dummy "
        "} "
        "RETURN label, 0 AS count ORDER BY label"
    )
    # Use a simpler, more universally supported approach
    result = session.run(
        "MATCH (n) "
        "UNWIND labels(n) AS label "
        "RETURN label, count(*) AS count "
        "ORDER BY count DESC"
    )
    records = list(result)
    columns = ["Label", "Count"]
    rows = [[r["label"], r["count"]] for r in records]
    sections.append(("Node counts per label", columns, rows))

    # -- Relationship counts per type --
    result = session.run(
        "MATCH ()-[r]->() "
        "RETURN type(r) AS rel_type, count(*) AS count "
        "ORDER BY count DESC"
    )
    records = list(result)
    columns = ["Relationship Type", "Count"]
    rows = [[r["rel_type"], r["count"]] for r in records]
    sections.append(("Relationship counts per type", columns, rows))

    # -- Papers with / without full text --
    result = session.run(
        "OPTIONAL MATCH (p:Paper) "
        "WITH count(p) AS total "
        "OPTIONAL MATCH (pw:Paper) WHERE pw.full_text IS NOT NULL AND pw.full_text <> '' "
        "WITH total, count(pw) AS with_text "
        "RETURN total, with_text, total - with_text AS without_text"
    )
    rec = result.single()
    if rec:
        columns = ["Total Papers", "With Full Text", "Without Full Text"]
        rows = [[rec["total"], rec["with_text"], rec["without_text"]]]
    else:
        columns = ["Total Papers", "With Full Text", "Without Full Text"]
        rows = [[0, 0, 0]]
    sections.append(("Paper full-text coverage", columns, rows))

    # -- Average confidence scores --
    result = session.run(
        "MATCH ()-[r]->() "
        "WHERE r.confidence IS NOT NULL "
        "RETURN type(r) AS rel_type, "
        "       round(avg(r.confidence) * 1000) / 1000 AS avg_confidence, "
        "       count(*) AS sample_size "
        "ORDER BY avg_confidence DESC"
    )
    records = list(result)
    columns = ["Relationship Type", "Avg Confidence", "Sample Size"]
    rows = [[r["rel_type"], r["avg_confidence"], r["sample_size"]] for r in records]
    if rows:
        sections.append(("Average confidence scores", columns, rows))

    # -- Cycle 1 vs Cycle 2 entity counts --
    result = session.run(
        "MATCH (n) "
        "WHERE n.extraction_cycle IS NOT NULL "
        "UNWIND labels(n) AS label "
        "RETURN n.extraction_cycle AS cycle, label, count(*) AS count "
        "ORDER BY cycle, count DESC"
    )
    records = list(result)
    columns = ["Cycle", "Label", "Count"]
    rows = [[r["cycle"], r["label"], r["count"]] for r in records]
    if rows:
        sections.append(("Cycle 1 vs Cycle 2 entity counts", columns, rows))

    # -- Panel verified vs unverified --
    result = session.run(
        "MATCH (n) "
        "WITH CASE WHEN n.panel_verified = true THEN 'Verified' "
        "          WHEN n.panel_verified = false THEN 'Unverified' "
        "          ELSE 'Unknown' END AS status, "
        "     count(*) AS count "
        "RETURN status, count ORDER BY count DESC"
    )
    records = list(result)
    columns = ["Verification Status", "Count"]
    rows = [[r["status"], r["count"]] for r in records]
    if rows:
        sections.append(("Panel verified vs unverified", columns, rows))

    return sections


def query_neighbors(session, node_name, node_label, depth, limit):
    """Find all neighbors of a node up to *depth* hops, sorted by confidence."""
    if not node_name:
        print("Error: --node is required for the 'neighbors' query.", file=sys.stderr)
        sys.exit(1)

    label_filter = f":{node_label}" if node_label else ""

    cypher = (
        f"MATCH (start{label_filter} {{name: $name}}) "
        f"CALL apoc.path.subgraphAll(start, {{maxLevel: $depth}}) "
        f"YIELD nodes, relationships "
        f"UNWIND relationships AS r "
        f"WITH startNode(r) AS src, r, endNode(r) AS tgt "
        f"RETURN labels(src)[0] AS src_label, src.name AS source, "
        f"       type(r) AS relationship, "
        f"       labels(tgt)[0] AS tgt_label, tgt.name AS target, "
        f"       r.confidence AS confidence "
        f"ORDER BY r.confidence DESC "
        f"LIMIT $limit"
    )

    # Fallback if APOC is not installed
    fallback = (
        f"MATCH path = (start{label_filter} {{name: $name}})"
        f"-[*1..{depth}]-(neighbor) "
        f"UNWIND relationships(path) AS r "
        f"WITH DISTINCT r, startNode(r) AS src, endNode(r) AS tgt "
        f"RETURN labels(src)[0] AS src_label, src.name AS source, "
        f"       type(r) AS relationship, "
        f"       labels(tgt)[0] AS tgt_label, tgt.name AS target, "
        f"       r.confidence AS confidence "
        f"ORDER BY r.confidence DESC "
        f"LIMIT $limit"
    )

    params = {"name": node_name, "depth": depth, "limit": limit}
    try:
        result = session.run(cypher, params)
        records = list(result)
    except ClientError:
        # APOC not available – use variable-length path fallback
        result = session.run(fallback, params)
        records = list(result)

    columns = [
        "Source Label", "Source", "Relationship",
        "Target Label", "Target", "Confidence",
    ]
    rows = [
        [
            r["src_label"], r["source"], r["relationship"],
            r["tgt_label"], r["target"],
            r["confidence"] if r["confidence"] is not None else "",
        ]
        for r in records
    ]
    return [("Neighbors", columns, rows)]


def query_paths(session, node_spec, node_label, limit):
    """Find shortest paths between two comma-separated node names."""
    if not node_spec or "," not in node_spec:
        print(
            "Error: --node must be 'NodeA,NodeB' for the 'paths' query.",
            file=sys.stderr,
        )
        sys.exit(1)

    parts = [n.strip() for n in node_spec.split(",", 1)]
    node_a, node_b = parts[0], parts[1]

    label_filter = f":{node_label}" if node_label else ""

    cypher = (
        f"MATCH (a{label_filter} {{name: $nodeA}}), "
        f"      (b{label_filter} {{name: $nodeB}}), "
        f"      path = shortestPath((a)-[*..15]-(b)) "
        f"RETURN path LIMIT $limit"
    )

    result = session.run(cypher, {"nodeA": node_a, "nodeB": node_b, "limit": limit})
    records = list(result)

    columns = ["Step", "Source", "Relationship", "Direction", "Target"]
    rows = []
    for rec in records:
        path = rec["path"]
        nodes = list(path.nodes)
        rels = list(path.relationships)
        for i, rel in enumerate(rels):
            src_node = nodes[i]
            tgt_node = nodes[i + 1]
            src_name = src_node.get("name", str(src_node.id))
            tgt_name = tgt_node.get("name", str(tgt_node.id))
            # Determine direction relative to the path traversal
            if rel.start_node.element_id == src_node.element_id:
                direction = "->"
            else:
                direction = "<-"
            rows.append([i + 1, src_name, rel.type, direction, tgt_name])

    title = f"Shortest path(s): {node_a} <-> {node_b}"
    return [(title, columns, rows)]


def query_central(session, limit):
    """Find most central nodes by degree centrality, grouped by label."""
    cypher = (
        "MATCH (n) "
        "WITH n, labels(n)[0] AS label, size([(n)-[]-() | 1]) AS degree "
        "ORDER BY degree DESC "
        "WITH label, collect({name: n.name, degree: degree})[0..$limit] AS top "
        "UNWIND top AS entry "
        "RETURN label AS Label, entry.name AS Name, entry.degree AS Degree "
        "ORDER BY label, Degree DESC"
    )
    result = session.run(cypher, {"limit": limit})
    records = list(result)

    columns = ["Label", "Name", "Degree"]
    rows = [[r["Label"], r["Name"], r["Degree"]] for r in records]
    return [("Most central nodes (degree centrality)", columns, rows)]


def query_communities(session, limit):
    """Detect communities using GDS Louvain or fall back to NetworkX."""
    sections = []

    # Try Neo4j GDS first
    gds_available = _try_gds_communities(session, limit, sections)
    if not gds_available:
        _networkx_communities(session, limit, sections)

    return sections


def _try_gds_communities(session, limit, sections):
    """Attempt community detection via Neo4j Graph Data Science Louvain."""
    try:
        # Check if GDS is available
        session.run("RETURN gds.version() AS v").single()
    except (ClientError, Exception):
        return False

    graph_name = "__query_graph_tmp"

    try:
        # Drop previous projection if it exists
        try:
            session.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:
            pass

        # Project all nodes and relationships
        session.run(
            "CALL gds.graph.project($name, '*', '*')",
            {"name": graph_name},
        )

        # Run Louvain
        result = session.run(
            "CALL gds.louvain.stream($name) "
            "YIELD nodeId, communityId "
            "WITH communityId, collect(gds.util.asNode(nodeId).name) AS members, "
            "     count(*) AS size "
            "ORDER BY size DESC "
            "LIMIT $limit "
            "RETURN communityId, size, members[0..10] AS top_members",
            {"name": graph_name, "limit": limit},
        )
        records = list(result)

        columns = ["Community ID", "Size", "Top Members"]
        rows = [
            [r["communityId"], r["size"], ", ".join(str(m) for m in r["top_members"])]
            for r in records
        ]
        sections.append(("Communities (GDS Louvain)", columns, rows))

        # Clean up
        try:
            session.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:
            pass

        return True
    except (ClientError, Exception):
        # Clean up on failure
        try:
            session.run(f"CALL gds.graph.drop('{graph_name}', false)")
        except Exception:
            pass
        return False


def _networkx_communities(session, limit, sections):
    """Fallback community detection via NetworkX + python-louvain."""
    try:
        import networkx as nx
    except ImportError:
        sections.append((
            "Community detection",
            ["Error"],
            [["NetworkX not installed. Install with: pip install networkx"]],
        ))
        return

    try:
        from community import community_louvain
    except ImportError:
        try:
            from networkx.algorithms.community import greedy_modularity_communities
            use_greedy = True
        except ImportError:
            sections.append((
                "Community detection",
                ["Error"],
                [[
                    "Neither python-louvain nor networkx >= 2.x community "
                    "algorithms available. Install with: pip install python-louvain"
                ]],
            ))
            return
    else:
        use_greedy = False

    # Export graph from Neo4j
    nodes_result = session.run(
        "MATCH (n) RETURN id(n) AS id, n.name AS name, labels(n)[0] AS label"
    )
    node_records = list(nodes_result)

    rels_result = session.run(
        "MATCH (a)-[r]->(b) RETURN id(a) AS src, id(b) AS tgt, type(r) AS rel"
    )
    rel_records = list(rels_result)

    G = nx.Graph()
    id_to_name = {}
    for nr in node_records:
        nid = nr["id"]
        name = nr["name"] if nr["name"] else str(nid)
        id_to_name[nid] = name
        G.add_node(nid, name=name, label=nr["label"])

    for rr in rel_records:
        G.add_edge(rr["src"], rr["tgt"], rel=rr["rel"])

    if G.number_of_nodes() == 0:
        sections.append((
            "Community detection",
            ["Info"],
            [["Graph is empty -- no communities to detect."]],
        ))
        return

    # Detect communities
    if use_greedy:
        communities_gen = greedy_modularity_communities(G)
        partition = {}
        for idx, comm in enumerate(communities_gen):
            for node in comm:
                partition[node] = idx
    else:
        partition = community_louvain.best_partition(G)

    # Aggregate
    from collections import defaultdict
    comm_members = defaultdict(list)
    for node_id, comm_id in partition.items():
        comm_members[comm_id].append(id_to_name.get(node_id, str(node_id)))

    sorted_comms = sorted(comm_members.items(), key=lambda x: -len(x[1]))[:limit]

    columns = ["Community ID", "Size", "Top Members"]
    rows = [
        [cid, len(members), ", ".join(members[:10])]
        for cid, members in sorted_comms
    ]
    sections.append(("Communities (NetworkX fallback)", columns, rows))


def query_custom(session, cypher, limit):
    """Execute an arbitrary Cypher query."""
    if not cypher:
        print(
            "Error: --cypher is required for the 'custom' query type.",
            file=sys.stderr,
        )
        sys.exit(1)

    result = session.run(cypher)
    records = list(result)

    if not records:
        return [("Custom query results", ["(no results)"], [])]

    columns = list(records[0].keys())
    rows = [
        [_serialize_value(r[col]) for col in columns]
        for r in records[:limit]
    ]
    return [("Custom query results", columns, rows)]


def _serialize_value(val):
    """Convert Neo4j value to a display-friendly string."""
    if val is None:
        return ""
    if isinstance(val, (list, dict)):
        return json.dumps(val, default=str)
    return val


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

QUERY_TYPES = {
    "stats": "Graph statistics overview",
    "neighbors": "Find neighbors of a node (requires --node)",
    "paths": "Shortest paths between two nodes (--node 'A,B')",
    "central": "Most central nodes by degree",
    "communities": "Community detection (GDS or NetworkX fallback)",
    "custom": "Run arbitrary Cypher (requires --cypher)",
}


def build_parser():
    parser = argparse.ArgumentParser(
        description="Query a Neo4j literature knowledge graph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Query types:\n" + "\n".join(
            f"  {k:14s} {v}" for k, v in QUERY_TYPES.items()
        ),
    )
    parser.add_argument(
        "--uri", default="bolt://localhost:7687",
        help="Neo4j bolt URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--user", default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--password", required=True,
        help="Neo4j password",
    )
    parser.add_argument(
        "--query", required=True,
        choices=list(QUERY_TYPES.keys()),
        help="Type of query to execute",
    )
    parser.add_argument(
        "--node", default=None,
        help="Node name (for neighbors/paths queries). "
             "For paths use 'NodeA,NodeB'.",
    )
    parser.add_argument(
        "--node-label", default=None,
        help="Node label / type filter (e.g. Gene, Disease)",
    )
    parser.add_argument(
        "--depth", type=int, default=2,
        help="Traversal depth for neighbor queries (default: 2)",
    )
    parser.add_argument(
        "--limit", type=int, default=25,
        help="Maximum number of results (default: 25)",
    )
    parser.add_argument(
        "--cypher", default=None,
        help="Custom Cypher query string (for --query custom)",
    )
    parser.add_argument(
        "--output-format", default="table",
        choices=["table", "json", "csv"],
        help="Output format (default: table)",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "stats": lambda s: query_stats(s, args.limit),
        "neighbors": lambda s: query_neighbors(
            s, args.node, args.node_label, args.depth, args.limit,
        ),
        "paths": lambda s: query_paths(
            s, args.node, args.node_label, args.limit,
        ),
        "central": lambda s: query_central(s, args.limit),
        "communities": lambda s: query_communities(s, args.limit),
        "custom": lambda s: query_custom(s, args.cypher, args.limit),
    }

    with neo4j_session(args.uri, args.user, args.password) as session:
        sections = dispatch[args.query](session)

    for title, columns, rows in sections:
        if args.output_format == "table":
            print(f"\n=== {title} ===\n")
        print(format_output(columns, rows, args.output_format))
        if args.output_format == "table":
            print()


if __name__ == "__main__":
    main()
