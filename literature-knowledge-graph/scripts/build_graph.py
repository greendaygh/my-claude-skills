#!/usr/bin/env python3
from __future__ import annotations
"""
build_graph.py - Load extracted entities and relationships into Neo4j.

Reads extraction results (entities, relationships) and paper metadata from JSON
files, validates them against a schema, and batch-loads everything into Neo4j
using UNWIND operations for efficiency.

Usage:
    python build_graph.py \
        --password secret \
        --extractions extractions.json \
        --papers papers.json \
        --schema schema.json \
        --cycle 1
"""

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import (
    AuthError,
    ClientError,
    Neo4jError,
    ServiceUnavailable,
    TransientError,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def load_schema(path: str) -> dict:
    """Load and return the schema JSON, extracting entity types, their
    primary keys, and valid relationship types."""
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    entity_types: dict[str, dict] = {}
    relationship_types: set[str] = set()

    # Support two common schema layouts:
    #   1. {"entity_types": [...], "relationship_types": [...]}
    #   2. {"nodes": {...}, "relationships": {...}}
    if "entity_types" in raw:
        for et in raw["entity_types"]:
            label = et.get("label") or et.get("name") or et.get("type")
            primary_key = et.get("primary_key", "name")
            entity_types[label] = {
                "primary_key": primary_key,
                "properties": et.get("properties", {}),
            }
    elif "nodes" in raw:
        for label, spec in raw["nodes"].items():
            primary_key = spec.get("primary_key", "name")
            entity_types[label] = {
                "primary_key": primary_key,
                "properties": spec.get("properties", {}),
            }

    if "relationship_types" in raw:
        for rt in raw["relationship_types"]:
            if isinstance(rt, str):
                relationship_types.add(rt)
            elif isinstance(rt, dict):
                rtype = rt.get("type") or rt.get("name") or rt.get("label")
                if rtype:
                    relationship_types.add(rtype)
    elif "relationships" in raw:
        for rtype in raw["relationships"]:
            if isinstance(rtype, str):
                relationship_types.add(rtype)
            elif isinstance(rtype, dict):
                t = rtype.get("type") or rtype.get("name") or rtype.get("label")
                if t:
                    relationship_types.add(t)
            else:
                relationship_types.add(str(rtype))

    return {
        "entity_types": entity_types,
        "relationship_types": relationship_types,
        "raw": raw,
    }


def validate_entity(entity: dict, schema: dict) -> bool:
    """Return True if the entity label is present in the schema."""
    label = entity.get("label")
    if label not in schema["entity_types"]:
        logger.warning("Entity label '%s' not found in schema -- skipping", label)
        return False
    return True


def validate_relationship(rel: dict, schema: dict) -> bool:
    """Return True if the relationship type is present in the schema."""
    rtype = rel.get("type")
    if schema["relationship_types"] and rtype not in schema["relationship_types"]:
        logger.warning("Relationship type '%s' not found in schema -- skipping", rtype)
        return False
    return True


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------

def load_json(path: str) -> Any:
    """Load a JSON file, returning the parsed object."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build_paper_records(papers_path: str | None, extractions: list[dict]) -> list[dict]:
    """Build a deduplicated list of paper records from the papers metadata file
    and the extraction results.  Each record is keyed by DOI (preferred) or
    PMID."""
    seen: dict[str, dict] = {}

    # 1. Load from papers metadata file if provided.
    if papers_path:
        papers_data = load_json(papers_path)
        if isinstance(papers_data, list):
            paper_list = papers_data
        elif isinstance(papers_data, dict):
            paper_list = papers_data.get("papers", papers_data.get("results", []))
        else:
            paper_list = []

        for p in paper_list:
            key = p.get("doi") or p.get("pmid")
            if key:
                seen[key] = {
                    "doi": p.get("doi"),
                    "pmid": p.get("pmid"),
                    "pmcid": p.get("pmcid"),
                    "title": p.get("title"),
                    "authors": p.get("authors", []),
                    "year": p.get("year"),
                    "journal": p.get("journal"),
                    "abstract": p.get("abstract"),
                    "full_text_available": p.get("full_text_available", False),
                }

    # 2. Ensure every paper referenced in extractions has a record.
    for ext in extractions:
        doi = ext.get("paper_doi")
        if doi and doi not in seen:
            seen[doi] = {
                "doi": doi,
                "pmid": None,
                "pmcid": None,
                "title": None,
                "authors": [],
                "year": None,
                "journal": None,
                "abstract": None,
                "full_text_available": False,
            }

    return list(seen.values())


# ---------------------------------------------------------------------------
# Neo4j batch operations
# ---------------------------------------------------------------------------

def create_paper_nodes(tx, batch: list[dict]) -> int:
    """MERGE Paper nodes using DOI (preferred) or PMID as the merge key."""
    # Separate into doi-keyed and pmid-keyed batches.
    doi_batch = [p for p in batch if p.get("doi")]
    pmid_batch = [p for p in batch if not p.get("doi") and p.get("pmid")]

    created = 0

    if doi_batch:
        result = tx.run(
            """
            UNWIND $batch AS row
            MERGE (p:Paper {doi: row.doi})
            SET p.pmid           = row.pmid,
                p.pmcid          = row.pmcid,
                p.title          = row.title,
                p.authors        = row.authors,
                p.year           = row.year,
                p.journal        = row.journal,
                p.abstract       = row.abstract,
                p.full_text_available = row.full_text_available
            RETURN count(p) AS cnt
            """,
            batch=doi_batch,
        )
        created += result.single()["cnt"]

    if pmid_batch:
        result = tx.run(
            """
            UNWIND $batch AS row
            MERGE (p:Paper {pmid: row.pmid})
            SET p.pmcid          = row.pmcid,
                p.title          = row.title,
                p.authors        = row.authors,
                p.year           = row.year,
                p.journal        = row.journal,
                p.abstract       = row.abstract,
                p.full_text_available = row.full_text_available
            RETURN count(p) AS cnt
            """,
            batch=pmid_batch,
        )
        created += result.single()["cnt"]

    return created


def create_entity_nodes(tx, label: str, primary_key: str, batch: list[dict]) -> int:
    """MERGE entity nodes of a given label using their primary key.

    Uses APOC-free dynamic property setting via SET n += row.properties.
    The MERGE itself requires a fixed label and key, so we build the query
    string with the label/key interpolated (they come from the trusted
    schema, not user input).
    """
    query = (
        f"UNWIND $batch AS row "
        f"MERGE (n:`{label}` {{{primary_key}: row.key}}) "
        f"SET n += row.properties "
        f"RETURN count(n) AS cnt"
    )
    result = tx.run(query, batch=batch)
    return result.single()["cnt"]


def create_relationships(tx, rel_type: str, batch: list[dict]) -> int:
    """Create relationships of a given type between already-existing nodes.

    Each row in *batch* must contain:
        from_label, from_key_field, from_key,
        to_label, to_key_field, to_key,
        properties   (dict of relationship properties)

    Because Cypher requires literal relationship types, we interpolate
    rel_type into the query (it is validated against the schema).
    """
    # Group by (from_label, from_key_field, to_label, to_key_field) to
    # build efficient queries.
    groups: dict[tuple, list[dict]] = {}
    for row in batch:
        gkey = (row["from_label"], row["from_key_field"],
                row["to_label"], row["to_key_field"])
        groups.setdefault(gkey, []).append(row)

    total = 0
    for (fl, fkf, tl, tkf), rows in groups.items():
        query = (
            f"UNWIND $batch AS row "
            f"MATCH (a:`{fl}` {{{fkf}: row.from_key}}) "
            f"MATCH (b:`{tl}` {{{tkf}: row.to_key}}) "
            f"MERGE (a)-[r:`{rel_type}`]->(b) "
            f"SET r += row.properties "
            f"RETURN count(r) AS cnt"
        )
        result = tx.run(query, batch=rows)
        total += result.single()["cnt"]

    return total


def create_extracted_from_links(tx, batch: list[dict]) -> int:
    """Create :EXTRACTED_FROM relationships linking entity/relationship nodes
    back to their source Paper node.

    Each row must contain:
        node_label, node_key_field, node_key,
        paper_doi (or paper_pmid),
        provenance  (dict with metadata fields)
    """
    doi_rows = [r for r in batch if r.get("paper_doi")]
    pmid_rows = [r for r in batch if not r.get("paper_doi") and r.get("paper_pmid")]

    total = 0

    # Group by (node_label, node_key_field) for efficiency.
    def _run_groups(rows: list[dict], paper_field: str) -> int:
        groups: dict[tuple, list[dict]] = {}
        for row in rows:
            gkey = (row["node_label"], row["node_key_field"])
            groups.setdefault(gkey, []).append(row)

        count = 0
        for (nl, nkf), group_rows in groups.items():
            query = (
                f"UNWIND $batch AS row "
                f"MATCH (n:`{nl}` {{{nkf}: row.node_key}}) "
                f"MATCH (p:Paper {{{paper_field}: row.paper_ref}}) "
                f"MERGE (n)-[r:EXTRACTED_FROM]->(p) "
                f"SET r += row.provenance "
                f"RETURN count(r) AS cnt"
            )
            result = tx.run(query, batch=[
                {**r, "paper_ref": r.get("paper_doi") or r.get("paper_pmid")}
                for r in group_rows
            ])
            count += result.single()["cnt"]
        return count

    if doi_rows:
        total += _run_groups(doi_rows, "doi")
    if pmid_rows:
        total += _run_groups(pmid_rows, "pmid")

    return total


# ---------------------------------------------------------------------------
# Ensure indexes/constraints exist for merge performance
# ---------------------------------------------------------------------------

def ensure_constraints(session, entity_types: dict[str, dict]) -> None:
    """Create uniqueness constraints for Paper and each entity type to speed
    up MERGE operations.  Constraints are created idempotently (IF NOT EXISTS)."""
    constraint_queries = [
        "CREATE CONSTRAINT paper_doi_unique IF NOT EXISTS FOR (p:Paper) REQUIRE p.doi IS UNIQUE",
        "CREATE CONSTRAINT paper_pmid_unique IF NOT EXISTS FOR (p:Paper) REQUIRE p.pmid IS UNIQUE",
    ]
    for label, spec in entity_types.items():
        pk = spec["primary_key"]
        safe_label = label.replace(" ", "_")
        cname = f"{safe_label.lower()}_{pk}_unique"
        constraint_queries.append(
            f"CREATE CONSTRAINT {cname} IF NOT EXISTS FOR (n:`{label}`) REQUIRE n.`{pk}` IS UNIQUE"
        )

    for q in constraint_queries:
        try:
            session.run(q)
            logger.debug("Constraint ensured: %s", q.split("FOR")[0].strip())
        except ClientError as exc:
            # Some Neo4j editions don't support certain constraint syntax.
            logger.debug("Constraint skipped (%s): %s", exc.code, q)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


def process_extractions(
    driver,
    extractions: list[dict],
    schema: dict,
    papers_path: str | None,
    batch_size: int,
    cycle: int,
) -> dict:
    """Process all extractions and load into Neo4j.  Returns a statistics dict."""
    stats = {
        "papers_created": 0,
        "entities_created": {},
        "relationships_created": {},
        "extracted_from_links": 0,
    }

    extraction_date = datetime.now(timezone.utc).isoformat()
    entity_types = schema["entity_types"]

    # Normalize: support single-extraction object or list.
    if isinstance(extractions, dict):
        extractions = [extractions]

    # ------------------------------------------------------------------
    # 1. Create Paper nodes
    # ------------------------------------------------------------------
    paper_records = build_paper_records(papers_path, extractions)
    logger.info("Merging %d Paper node(s)...", len(paper_records))

    with driver.session() as session:
        ensure_constraints(session, entity_types)

    with driver.session() as session:
        for batch in chunks(paper_records, batch_size):
            count = session.execute_write(create_paper_nodes, batch)
            stats["papers_created"] += count

    logger.info("Paper nodes created/updated: %d", stats["papers_created"])

    # ------------------------------------------------------------------
    # 2. Create entity nodes (grouped by label)
    # ------------------------------------------------------------------
    entity_rows_by_label: dict[str, list[dict]] = {}
    extracted_from_rows: list[dict] = []

    for ext in extractions:
        paper_doi = ext.get("paper_doi")
        paper_pmid = ext.get("paper_pmid")
        panel_verified = ext.get("panel_verified", False)
        panel_confidence = ext.get("panel_confidence")
        extraction_cycle_val = ext.get("extraction_cycle", cycle)
        schema_version = ext.get("schema_version")

        provenance = {
            "extraction_date": extraction_date,
            "extraction_cycle": extraction_cycle_val,
        }
        if panel_verified is not None:
            provenance["panel_verified"] = panel_verified
        if panel_confidence is not None:
            provenance["panel_confidence"] = panel_confidence
        if schema_version:
            provenance["schema_version"] = schema_version

        for ent in ext.get("entities", []):
            if not validate_entity(ent, schema):
                continue

            label = ent["label"]
            props = dict(ent.get("properties", {}))
            pk = entity_types[label]["primary_key"]
            key_value = props.get(pk)
            if key_value is None:
                logger.warning(
                    "Entity of type '%s' missing primary key '%s' -- skipping",
                    label, pk,
                )
                continue

            row = {"key": key_value, "properties": props}
            entity_rows_by_label.setdefault(label, []).append(row)

            # Prepare EXTRACTED_FROM link.
            extracted_from_rows.append({
                "node_label": label,
                "node_key_field": pk,
                "node_key": key_value,
                "paper_doi": paper_doi,
                "paper_pmid": paper_pmid,
                "provenance": provenance,
            })

    with driver.session() as session:
        for label, rows in entity_rows_by_label.items():
            pk = entity_types[label]["primary_key"]
            label_count = 0
            for batch in chunks(rows, batch_size):
                count = session.execute_write(create_entity_nodes, label, pk, batch)
                label_count += count
            stats["entities_created"][label] = label_count
            logger.info("  %s nodes created/updated: %d", label, label_count)

    # ------------------------------------------------------------------
    # 3. Create relationships
    # ------------------------------------------------------------------
    rel_rows_by_type: dict[str, list[dict]] = {}

    for ext in extractions:
        paper_doi = ext.get("paper_doi")
        paper_pmid = ext.get("paper_pmid")
        panel_verified = ext.get("panel_verified", False)
        panel_confidence = ext.get("panel_confidence")
        extraction_cycle_val = ext.get("extraction_cycle", cycle)
        schema_version = ext.get("schema_version")

        for rel in ext.get("relationships", []):
            if not validate_relationship(rel, schema):
                continue

            rtype = rel["type"]
            from_info = rel["from"]
            to_info = rel["to"]

            from_label = from_info["label"]
            to_label = to_info["label"]

            # Determine primary key fields.
            if from_label not in entity_types:
                logger.warning("Relationship from-label '%s' not in schema -- skipping", from_label)
                continue
            if to_label not in entity_types:
                logger.warning("Relationship to-label '%s' not in schema -- skipping", to_label)
                continue

            from_pk = entity_types[from_label]["primary_key"]
            to_pk = entity_types[to_label]["primary_key"]

            props = dict(rel.get("properties", {}))
            # Add provenance to relationship properties.
            props["extraction_date"] = extraction_date
            props["extraction_cycle"] = extraction_cycle_val
            if panel_verified is not None:
                props["panel_verified"] = panel_verified
            if panel_confidence is not None:
                props["panel_confidence"] = panel_confidence
            if schema_version:
                props["schema_version"] = schema_version

            row = {
                "from_label": from_label,
                "from_key_field": from_pk,
                "from_key": from_info["key"],
                "to_label": to_label,
                "to_key_field": to_pk,
                "to_key": to_info["key"],
                "properties": props,
            }
            rel_rows_by_type.setdefault(rtype, []).append(row)

            # EXTRACTED_FROM links for both endpoints of the relationship.
            provenance = {
                "extraction_date": extraction_date,
                "extraction_cycle": extraction_cycle_val,
            }
            if panel_verified is not None:
                provenance["panel_verified"] = panel_verified
            if panel_confidence is not None:
                provenance["panel_confidence"] = panel_confidence
            if schema_version:
                provenance["schema_version"] = schema_version

            for endpoint_info, endpoint_label in [
                (from_info, from_label),
                (to_info, to_label),
            ]:
                endpoint_pk = entity_types[endpoint_label]["primary_key"]
                extracted_from_rows.append({
                    "node_label": endpoint_label,
                    "node_key_field": endpoint_pk,
                    "node_key": endpoint_info["key"],
                    "paper_doi": paper_doi,
                    "paper_pmid": paper_pmid,
                    "provenance": provenance,
                })

    with driver.session() as session:
        for rtype, rows in rel_rows_by_type.items():
            type_count = 0
            for batch in chunks(rows, batch_size):
                count = session.execute_write(create_relationships, rtype, batch)
                type_count += count
            stats["relationships_created"][rtype] = type_count
            logger.info("  %s relationships created/updated: %d", rtype, type_count)

    # ------------------------------------------------------------------
    # 4. Create :EXTRACTED_FROM provenance links
    # ------------------------------------------------------------------
    logger.info("Creating EXTRACTED_FROM provenance links...")

    # Deduplicate by (node_label, node_key, paper_doi/pmid).
    deduped: dict[tuple, dict] = {}
    for row in extracted_from_rows:
        dedup_key = (
            row["node_label"],
            row["node_key"],
            row.get("paper_doi") or row.get("paper_pmid"),
        )
        deduped[dedup_key] = row
    extracted_from_rows = list(deduped.values())

    with driver.session() as session:
        for batch in chunks(extracted_from_rows, batch_size):
            count = session.execute_write(create_extracted_from_links, batch)
            stats["extracted_from_links"] += count

    logger.info("EXTRACTED_FROM links created: %d", stats["extracted_from_links"])

    return stats


def print_statistics(stats: dict) -> None:
    """Pretty-print the loading statistics."""
    print("\n" + "=" * 60)
    print("  Knowledge Graph Build Statistics")
    print("=" * 60)
    print(f"  Paper nodes created/updated:      {stats['papers_created']}")
    print()
    print("  Entity nodes created per type:")
    if stats["entities_created"]:
        for label, count in sorted(stats["entities_created"].items()):
            print(f"    {label:30s}  {count}")
    else:
        print("    (none)")
    print()
    print("  Relationships created per type:")
    if stats["relationships_created"]:
        for rtype, count in sorted(stats["relationships_created"].items()):
            print(f"    {rtype:30s}  {count}")
    else:
        print("    (none)")
    print()
    print(f"  EXTRACTED_FROM provenance links:   {stats['extracted_from_links']}")
    print("=" * 60 + "\n")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load extracted entities and relationships into Neo4j.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python build_graph.py \\
      --password mypassword \\
      --extractions extractions.json \\
      --papers papers.json \\
      --schema schema.json \\
      --cycle 1
        """,
    )
    parser.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help="Neo4j URI (default: bolt://localhost:7687)",
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
        "--extractions",
        required=True,
        help="Path to JSON file with extraction results",
    )
    parser.add_argument(
        "--papers",
        default=None,
        help="Path to JSON file with paper metadata (from search_literature.py)",
    )
    parser.add_argument(
        "--schema",
        required=True,
        help="Path to schema JSON (to validate entity/relationship types)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for UNWIND operations (default: 500)",
    )
    parser.add_argument(
        "--cycle",
        type=int,
        choices=[1, 2],
        default=1,
        help="Extraction cycle number (1 or 2, for metadata)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Validate file paths early.
    extractions_path = Path(args.extractions)
    schema_path = Path(args.schema)

    if not extractions_path.is_file():
        logger.error("Extractions file not found: %s", extractions_path)
        return 1
    if not schema_path.is_file():
        logger.error("Schema file not found: %s", schema_path)
        return 1
    if args.papers and not Path(args.papers).is_file():
        logger.error("Papers file not found: %s", args.papers)
        return 1

    # Load input data.
    try:
        extractions = load_json(str(extractions_path))
        schema = load_schema(str(schema_path))
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse JSON: %s", exc)
        return 1
    except Exception as exc:
        logger.error("Failed to load input files: %s", exc)
        return 1

    logger.info("Schema loaded: %d entity types, %d relationship types",
                len(schema["entity_types"]),
                len(schema["relationship_types"]))

    # Connect to Neo4j.
    driver = None
    try:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        driver.verify_connectivity()
        logger.info("Connected to Neo4j at %s", args.uri)
    except AuthError:
        logger.error("Authentication failed for Neo4j at %s", args.uri)
        return 1
    except ServiceUnavailable:
        logger.error("Neo4j service unavailable at %s", args.uri)
        return 1
    except Exception as exc:
        logger.error("Failed to connect to Neo4j: %s", exc)
        return 1

    try:
        stats = process_extractions(
            driver=driver,
            extractions=extractions,
            schema=schema,
            papers_path=args.papers,
            batch_size=args.batch_size,
            cycle=args.cycle,
        )
        print_statistics(stats)
    except TransientError as exc:
        logger.error("Transient Neo4j error (retry may help): %s", exc)
        return 1
    except ClientError as exc:
        logger.error("Neo4j client error: %s", exc)
        return 1
    except Neo4jError as exc:
        logger.error("Neo4j error: %s", exc)
        return 1
    except Exception as exc:
        logger.error("Unexpected error during graph build: %s", exc, exc_info=True)
        return 1
    finally:
        if driver:
            driver.close()
            logger.info("Neo4j connection closed.")

    logger.info("Graph build complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
