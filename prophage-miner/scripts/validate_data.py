"""Pydantic v2 models and validation functions for prophage-miner data.

Validates paper_list.json, per-paper extraction JSONs, and graph nodes/edges
against strict schemas with referential integrity checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Paper models
# ---------------------------------------------------------------------------

class PaperEntry(BaseModel):
    paper_id: str = Field(pattern=r"^P\d{3,}$")
    pmid: str
    pmcid: Optional[str] = None
    doi: Optional[str] = None
    title: str = Field(min_length=10)
    authors: str
    year: int = Field(ge=2015, le=2030)
    journal: str
    abstract: Optional[str] = None
    has_full_text: bool = False
    extraction_status: str = Field(default="pending", pattern=r"^(pending|extracted|failed|rejected)$")


class PaperList(BaseModel):
    search_date: str
    query: str
    total_pubmed_hits: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    papers: list[PaperEntry]


# ---------------------------------------------------------------------------
# Extraction models
# ---------------------------------------------------------------------------

class EntityRef(BaseModel):
    label: str
    key: str


class ExtractedEntity(BaseModel):
    label: str
    properties: dict[str, Any]


class ExtractedRelationship(BaseModel):
    type: str
    from_ref: EntityRef = Field(alias="from")
    to_ref: EntityRef = Field(alias="to")
    properties: dict[str, Any]

    model_config = {"populate_by_name": True}

    @field_validator("properties")
    @classmethod
    def must_have_valid_confidence(cls, v: dict) -> dict:
        if "confidence" not in v:
            raise ValueError("properties must contain 'confidence'")
        conf = v["confidence"]
        if not (0 <= conf <= 1):
            raise ValueError(f"confidence must be 0-1, got {conf}")
        return v


class PaperExtraction(BaseModel):
    paper_id: str = Field(pattern=r"^P\d{3,}$")
    paper_doi: Optional[str] = None
    entities: list[ExtractedEntity]
    relationships: list[ExtractedRelationship]
    unschemaed: list[dict] = []


# ---------------------------------------------------------------------------
# Graph models
# ---------------------------------------------------------------------------

class GraphNode(BaseModel):
    id: str
    label: str
    properties: dict[str, Any]
    source_papers: list[str]
    merged_count: int = Field(ge=1)


class GraphEdge(BaseModel):
    id: str
    type: str
    from_id: str
    to_id: str
    properties: dict[str, Any]
    avg_confidence: float = Field(ge=0, le=1)
    source_papers: list[str]


class GraphData(BaseModel):
    generated: str
    total_nodes: int = Field(ge=0)
    total_edges: int = Field(ge=0)
    nodes: list[GraphNode]
    edges: list[GraphEdge]

    @model_validator(mode="after")
    def edges_reference_existing_nodes(self):
        node_ids = {n.id for n in self.nodes}
        for e in self.edges:
            if e.from_id not in node_ids:
                raise ValueError(f"Edge {e.id} references unknown from_id '{e.from_id}'")
            if e.to_id not in node_ids:
                raise ValueError(f"Edge {e.id} references unknown to_id '{e.to_id}'")
        return self


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_papers(path: Path) -> dict:
    """Validate paper_list.json and return a result dict."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        PaperList(**data)
        return {"valid": True, "error_count": 0, "errors": []}
    except Exception as exc:
        errors = _parse_errors(exc)
        return {"valid": False, "error_count": len(errors), "errors": errors}


def validate_extraction(path: Path) -> dict:
    """Validate a per-paper extraction JSON."""
    path = Path(path)
    try:
        data = json.loads(path.read_text())
        PaperExtraction(**data)
        return {"valid": True, "error_count": 0, "errors": []}
    except Exception as exc:
        errors = _parse_errors(exc)
        return {"valid": False, "error_count": len(errors), "errors": errors}


def validate_graph(graph_dir: Path) -> dict:
    """Validate nodes.json + edges.json with referential integrity."""
    graph_dir = Path(graph_dir)
    try:
        nodes = json.loads((graph_dir / "nodes.json").read_text())
        edges = json.loads((graph_dir / "edges.json").read_text())
        meta_path = graph_dir / "graph_meta.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
        else:
            meta = {
                "generated": "",
                "total_nodes": len(nodes),
                "total_edges": len(edges),
            }
        graph_data = {
            "generated": meta.get("generated", ""),
            "total_nodes": meta.get("total_nodes", len(nodes)),
            "total_edges": meta.get("total_edges", len(edges)),
            "nodes": nodes,
            "edges": edges,
        }
        GraphData(**graph_data)
        return {"valid": True, "error_count": 0, "errors": []}
    except Exception as exc:
        errors = _parse_errors(exc)
        return {"valid": False, "error_count": len(errors), "errors": errors}


def _parse_errors(exc: Exception) -> list[str]:
    """Extract error messages from an exception."""
    if hasattr(exc, "errors"):
        return [str(e) for e in exc.errors()]
    return [str(exc)]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate prophage-miner data files")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--papers", type=Path, help="Path to paper_list.json")
    group.add_argument("--extraction", type=Path, help="Path to extraction JSON")
    group.add_argument("--graph", type=Path, help="Path to graph directory")

    args = parser.parse_args()

    if args.papers:
        result = validate_papers(args.papers)
    elif args.extraction:
        result = validate_extraction(args.extraction)
    else:
        result = validate_graph(args.graph)

    status = "PASS" if result["valid"] else "FAIL"
    print(f"[validate_data] {status} - {result['error_count']} error(s)")
    for err in result.get("errors", []):
        print(f"  - {err}")

    sys.exit(0 if result["valid"] else 1)


if __name__ == "__main__":
    main()
