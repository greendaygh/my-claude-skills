"""Extraction result validation, saving, and summary utilities.

This script does NOT perform automatic extraction. Extraction is done by
subagents reading full text and applying the schema. This module validates
and persists those results and generates summary statistics.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def validate_extraction_data(data: dict, schema: dict) -> list[str]:
    """Validate extraction data against the prophage schema.

    Returns list of error messages (empty = valid).
    """
    errors = []

    if "paper_id" not in data:
        errors.append("Missing required field: paper_id")
        return errors

    valid_entity_labels = {et["label"] for et in schema.get("entity_types", [])}
    valid_rel_types = {rt["type"] for rt in schema.get("relationship_types", [])}

    for i, entity in enumerate(data.get("entities", [])):
        label = entity.get("label", "")
        if label not in valid_entity_labels:
            errors.append(f"Entity [{i}]: unknown entity type '{label}'")

    for i, rel in enumerate(data.get("relationships", [])):
        rel_type = rel.get("type", "")
        if rel_type not in valid_rel_types:
            errors.append(f"Relationship [{i}]: unknown type '{rel_type}'")

        props = rel.get("properties", {})
        conf = props.get("confidence")
        if conf is not None and (conf < 0 or conf > 1):
            errors.append(f"Relationship [{i}]: confidence {conf} out of range [0, 1]")

    return errors


def save_extraction(paper_id: str, data: dict, output_dir: Path) -> Path:
    """Save extraction result as per-paper JSON file."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{paper_id}_extraction.json"
    data["paper_id"] = paper_id
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(
        f"[extract_prophage] Saved {paper_id}: "
        f"{len(data.get('entities', []))} entities, "
        f"{len(data.get('relationships', []))} relationships",
        file=sys.stderr,
    )
    return path


def generate_summary(extractions_dir: Path) -> dict:
    """Generate summary statistics from all extraction files in a directory."""
    extractions_dir = Path(extractions_dir)
    files = sorted(extractions_dir.glob("*_extraction.json"))

    total_entities = 0
    total_relationships = 0
    entity_type_counts: Counter = Counter()
    rel_type_counts: Counter = Counter()

    for f in files:
        data = json.loads(f.read_text())
        entities = data.get("entities", [])
        rels = data.get("relationships", [])
        total_entities += len(entities)
        total_relationships += len(rels)
        for e in entities:
            entity_type_counts[e.get("label", "unknown")] += 1
        for r in rels:
            rel_type_counts[r.get("type", "unknown")] += 1

    summary = {
        "total_papers": len(files),
        "total_entities": total_entities,
        "total_relationships": total_relationships,
        "entity_type_counts": dict(entity_type_counts),
        "relationship_type_counts": dict(rel_type_counts),
    }
    print(
        f"[extract_prophage] Summary: {len(files)} papers, "
        f"{total_entities} entities, {total_relationships} relationships",
        file=sys.stderr,
    )
    return summary


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extraction utilities for prophage-miner")
    sub = parser.add_subparsers(dest="command")

    save_p = sub.add_parser("save", help="Save extraction result")
    save_p.add_argument("--paper-id", required=True)
    save_p.add_argument("--output", type=Path, required=True)
    save_p.add_argument("--input", type=Path, help="JSON file to save (default: stdin)")

    summary_p = sub.add_parser("summary", help="Generate extraction summary")
    summary_p.add_argument("--dir", type=Path, required=True)

    validate_p = sub.add_parser("validate", help="Validate extraction against schema")
    validate_p.add_argument("--input", type=Path, required=True)
    validate_p.add_argument("--schema", type=Path, required=True)

    args = parser.parse_args()

    if args.command == "save":
        if args.input:
            data = json.loads(args.input.read_text())
        else:
            data = json.loads(sys.stdin.read())
        save_extraction(args.paper_id, data, args.output)

    elif args.command == "summary":
        s = generate_summary(args.dir)
        print(json.dumps(s, indent=2))

    elif args.command == "validate":
        data = json.loads(args.input.read_text())
        schema = json.loads(args.schema.read_text())
        errors = validate_extraction_data(data, schema)
        if errors:
            for e in errors:
                print(f"  ERROR: {e}", file=sys.stderr)
            sys.exit(1)
        else:
            print("[extract_prophage] Validation passed", file=sys.stderr)


if __name__ == "__main__":
    main()
