#!/usr/bin/env python3
"""Initialize a Neo4j database schema from a JSON schema definition file.

This script reads a JSON schema describing entity types, relationship types,
and provenance metadata, then creates the corresponding uniqueness constraints,
indexes, and provenance structures in a Neo4j database.

Usage:
    python setup_neo4j.py --password secret --schema schema.json
    python setup_neo4j.py --uri bolt://remote:7687 --user admin --password secret --schema schema.json --reset
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import ClientError, ServiceUnavailable, AuthError
except ImportError:
    print(
        "Error: the 'neo4j' Python driver is not installed.\n"
        "Install it with:  pip install neo4j",
        file=sys.stderr,
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Schema helpers
# ---------------------------------------------------------------------------

def load_schema(path: str | Path) -> dict[str, Any]:
    """Load and validate the JSON schema file."""
    schema_path = Path(path)
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)

    # Minimal structural validation
    required_keys = {"entity_types", "relationship_types", "provenance"}
    missing = required_keys - set(schema.keys())
    if missing:
        raise ValueError(f"Schema JSON is missing required top-level keys: {missing}")

    for i, et in enumerate(schema["entity_types"]):
        if "label" not in et or "primary_key" not in et:
            raise ValueError(
                f"entity_types[{i}] must contain at least 'label' and 'primary_key'"
            )

    provenance = schema["provenance"]
    for key in ("paper_label", "paper_properties", "extraction_rel", "extraction_properties"):
        if key not in provenance:
            raise ValueError(f"provenance section is missing required key: '{key}'")

    return schema


# ---------------------------------------------------------------------------
# Neo4j operations
# ---------------------------------------------------------------------------

def drop_all_constraints_and_indexes(session) -> list[str]:
    """Drop every user-created constraint and index.  Returns a log of actions."""
    actions: list[str] = []

    # Drop constraints first (each constraint implies an index).
    result = session.run("SHOW CONSTRAINTS YIELD name RETURN name")
    for record in result:
        name = record["name"]
        session.run(f"DROP CONSTRAINT {name} IF EXISTS")
        actions.append(f"Dropped constraint: {name}")

    # Drop remaining indexes.
    result = session.run("SHOW INDEXES YIELD name, type RETURN name, type")
    for record in result:
        # Skip the built-in lookup indexes that cannot be dropped.
        if record["type"] == "LOOKUP":
            continue
        name = record["name"]
        session.run(f"DROP INDEX {name} IF EXISTS")
        actions.append(f"Dropped index: {name}")

    return actions


def create_uniqueness_constraint(session, label: str, property_name: str) -> str:
    """Create a uniqueness constraint on label(property_name).

    Returns a human-readable description of what was created.
    """
    constraint_name = f"uniq_{label.lower()}_{property_name.lower()}"
    query = (
        f"CREATE CONSTRAINT {constraint_name} IF NOT EXISTS "
        f"FOR (n:{label}) REQUIRE n.{property_name} IS UNIQUE"
    )
    session.run(query)
    return f"Uniqueness constraint: :{label}({property_name})  [{constraint_name}]"


def create_index(session, label: str, property_name: str) -> str:
    """Create a single-property index on label(property_name).

    Returns a human-readable description of what was created.
    """
    index_name = f"idx_{label.lower()}_{property_name.lower()}"
    query = (
        f"CREATE INDEX {index_name} IF NOT EXISTS "
        f"FOR (n:{label}) ON (n.{property_name})"
    )
    session.run(query)
    return f"Index: :{label}({property_name})  [{index_name}]"


def create_rel_index(session, rel_type: str, property_name: str) -> str:
    """Create an index on a relationship property.

    Returns a human-readable description of what was created.
    """
    index_name = f"relidx_{rel_type.lower()}_{property_name.lower()}"
    query = (
        f"CREATE INDEX {index_name} IF NOT EXISTS "
        f"FOR ()-[r:{rel_type}]-() ON (r.{property_name})"
    )
    session.run(query)
    return f"Relationship index: [:{rel_type}]({property_name})  [{index_name}]"


def apply_schema(session, schema: dict[str, Any], reset: bool = False) -> list[str]:
    """Apply the full schema to the database.  Returns a log of all actions."""
    actions: list[str] = []

    # ------------------------------------------------------------------
    # 1. Optional reset
    # ------------------------------------------------------------------
    if reset:
        drop_actions = drop_all_constraints_and_indexes(session)
        actions.extend(drop_actions)
        if drop_actions:
            actions.append("")  # visual separator in the summary

    # ------------------------------------------------------------------
    # 2. Entity types -- uniqueness constraints + property indexes
    # ------------------------------------------------------------------
    for et in schema["entity_types"]:
        label = et["label"]
        pk = et["primary_key"]

        actions.append(create_uniqueness_constraint(session, label, pk))

        # Index every additional property listed (the PK already gets an
        # implicit index from its uniqueness constraint).
        for prop in et.get("properties", []):
            if prop != pk:
                actions.append(create_index(session, label, prop))

    # ------------------------------------------------------------------
    # 3. Relationship types -- indexes on relationship properties
    # ------------------------------------------------------------------
    for rt in schema["relationship_types"]:
        rel_type = rt["type"]
        for prop in rt.get("properties", []):
            actions.append(create_rel_index(session, rel_type, prop))

    # ------------------------------------------------------------------
    # 4. Provenance -- Paper node + EXTRACTED_FROM relationship
    # ------------------------------------------------------------------
    prov = schema["provenance"]
    paper_label = prov["paper_label"]
    paper_props = prov["paper_properties"]

    # The first two well-known identifiers get uniqueness constraints.
    identifier_props = [p for p in ("doi", "pmid") if p in paper_props]
    for prop in identifier_props:
        actions.append(create_uniqueness_constraint(session, paper_label, prop))

    # Index all remaining paper properties for fast look-ups.
    for prop in paper_props:
        if prop not in identifier_props:
            actions.append(create_index(session, paper_label, prop))

    # Indexes on the extraction relationship.
    extraction_rel = prov["extraction_rel"]
    for prop in prov.get("extraction_properties", []):
        actions.append(create_rel_index(session, extraction_rel, prop))

    return actions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Initialize a Neo4j database schema from a JSON definition.",
    )
    parser.add_argument(
        "--uri",
        default="bolt://localhost:7687",
        help="Neo4j Bolt URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--user",
        default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--password",
        required=True,
        help="Neo4j password (required)",
    )
    parser.add_argument(
        "--schema",
        required=True,
        help="Path to the JSON schema file",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        default=False,
        help="Drop all existing constraints and indexes before applying the schema",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # --- Load schema ---
    try:
        schema = load_schema(args.schema)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"Schema error: {exc}", file=sys.stderr)
        return 1

    project = schema.get("project", "<unnamed>")
    version = schema.get("version", "<unversioned>")
    print(f"Schema: project={project}  version={version}")
    print(f"Connecting to {args.uri} as {args.user} ...")

    # --- Connect to Neo4j ---
    driver = None
    try:
        driver = GraphDatabase.driver(args.uri, auth=(args.user, args.password))
        driver.verify_connectivity()
    except ServiceUnavailable:
        print(
            f"Error: could not connect to Neo4j at {args.uri}. "
            "Is the database running?",
            file=sys.stderr,
        )
        return 1
    except AuthError:
        print(
            "Error: authentication failed. Check --user and --password.",
            file=sys.stderr,
        )
        return 1

    # --- Apply schema ---
    try:
        with driver.session() as session:
            actions = apply_schema(session, schema, reset=args.reset)
    except ClientError as exc:
        print(f"Neo4j client error: {exc}", file=sys.stderr)
        return 1
    finally:
        if driver is not None:
            driver.close()

    # --- Summary ---
    print()
    print("=" * 60)
    print("  Schema setup summary")
    print("=" * 60)
    for action in actions:
        print(f"  {action}")
    print("=" * 60)

    counts = {
        "constraints": sum(1 for a in actions if "constraint" in a.lower() and "Dropped" not in a),
        "indexes": sum(1 for a in actions if a.startswith("Index:") or a.startswith("Relationship index:")),
        "dropped": sum(1 for a in actions if "Dropped" in a),
    }
    print(
        f"  Totals: {counts['constraints']} constraint(s), "
        f"{counts['indexes']} index(es) created"
        + (f", {counts['dropped']} item(s) dropped" if counts["dropped"] else "")
    )
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
