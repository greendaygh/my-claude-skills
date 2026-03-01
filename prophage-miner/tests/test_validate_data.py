"""Tests for validate_data.py - Pydantic v2 models and validation functions."""

import json
import copy
from pathlib import Path

import pytest

from scripts.validate_data import (
    PaperEntry,
    PaperList,
    ExtractedEntity,
    ExtractedRelationship,
    PaperExtraction,
    GraphNode,
    GraphEdge,
    GraphData,
    validate_papers,
    validate_extraction,
    validate_graph,
)


# --- PaperEntry / PaperList tests ---

class TestPaperEntry:
    def test_valid_paper_entry(self, sample_paper_list):
        entry = PaperEntry(**sample_paper_list["papers"][0])
        assert entry.paper_id == "P001"
        assert entry.pmid == "39876543"

    def test_invalid_paper_id_pattern(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["paper_id"] = "INVALID"
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_paper_id_numeric_suffix(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["paper_id"] = "P0001"
        entry = PaperEntry(**data)
        assert entry.paper_id == "P0001"

    def test_missing_required_field(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        del data["title"]
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_title_too_short(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["title"] = "Short"
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_year_out_of_range_low(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["year"] = 2010
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_year_out_of_range_high(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["year"] = 2035
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_invalid_extraction_status(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["extraction_status"] = "unknown_status"
        with pytest.raises(Exception):
            PaperEntry(**data)

    def test_optional_fields_none(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list["papers"][0])
        data["doi"] = None
        data["abstract"] = None
        data["pmcid"] = None
        entry = PaperEntry(**data)
        assert entry.doi is None

    def test_default_extraction_status(self):
        entry = PaperEntry(
            paper_id="P100",
            pmid="12345",
            title="A valid title for testing purposes",
            authors="Author A",
            year=2024,
            journal="Test Journal",
        )
        assert entry.extraction_status == "pending"
        assert entry.has_full_text is False


class TestPaperList:
    def test_valid_paper_list(self, sample_paper_list):
        pl = PaperList(**sample_paper_list)
        assert len(pl.papers) == 2

    def test_empty_papers_list(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list)
        data["papers"] = []
        data["selected_count"] = 0
        pl = PaperList(**data)
        assert len(pl.papers) == 0

    def test_negative_total_hits(self, sample_paper_list):
        data = copy.deepcopy(sample_paper_list)
        data["total_pubmed_hits"] = -1
        with pytest.raises(Exception):
            PaperList(**data)


# --- PaperExtraction tests ---

class TestPaperExtraction:
    def test_valid_extraction(self, sample_extraction, schema_data):
        ext = PaperExtraction(**sample_extraction)
        assert ext.paper_id == "P001"
        assert len(ext.entities) == 4
        assert len(ext.relationships) == 2

    def test_extraction_unknown_entity_type(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["entities"].append({
            "label": "UnknownType",
            "properties": {"name": "test"},
        })
        ext = PaperExtraction(**data)
        assert ext.entities[-1].label == "UnknownType"

    def test_extraction_confidence_out_of_range(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["relationships"][0]["properties"]["confidence"] = 1.5
        with pytest.raises(Exception):
            PaperExtraction(**data)

    def test_extraction_negative_confidence(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["relationships"][0]["properties"]["confidence"] = -0.1
        with pytest.raises(Exception):
            PaperExtraction(**data)

    def test_extraction_missing_confidence(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        del data["relationships"][0]["properties"]["confidence"]
        with pytest.raises(Exception):
            PaperExtraction(**data)

    def test_extraction_empty_entities(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["entities"] = []
        data["relationships"] = []
        ext = PaperExtraction(**data)
        assert len(ext.entities) == 0

    def test_extraction_invalid_paper_id(self, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["paper_id"] = "INVALID"
        with pytest.raises(Exception):
            PaperExtraction(**data)


# --- GraphData tests ---

class TestGraphData:
    def test_valid_graph(self, sample_graph_data):
        gd = GraphData(**sample_graph_data)
        assert gd.total_nodes == 3
        assert gd.total_edges == 2

    def test_graph_orphan_edge(self, sample_graph_data):
        data = copy.deepcopy(sample_graph_data)
        data["edges"][0]["from_id"] = "nonexistent_node"
        with pytest.raises(Exception):
            GraphData(**data)

    def test_graph_orphan_edge_to(self, sample_graph_data):
        data = copy.deepcopy(sample_graph_data)
        data["edges"][0]["to_id"] = "nonexistent_node"
        with pytest.raises(Exception):
            GraphData(**data)

    def test_graph_empty(self):
        gd = GraphData(
            generated="2026-02-28T12:00:00Z",
            total_nodes=0,
            total_edges=0,
            nodes=[],
            edges=[],
        )
        assert gd.total_nodes == 0

    def test_graph_node_merged_count_minimum(self, sample_graph_data):
        data = copy.deepcopy(sample_graph_data)
        data["nodes"][0]["merged_count"] = 0
        with pytest.raises(Exception):
            GraphData(**data)

    def test_graph_edge_confidence_range(self, sample_graph_data):
        data = copy.deepcopy(sample_graph_data)
        data["edges"][0]["avg_confidence"] = 1.5
        with pytest.raises(Exception):
            GraphData(**data)


# --- CLI/function validation tests ---

class TestValidateFunctions:
    def test_validate_papers_valid(self, tmp_phage_dir, sample_paper_list):
        path = tmp_phage_dir / "01_papers" / "paper_list.json"
        path.write_text(json.dumps(sample_paper_list))
        result = validate_papers(path)
        assert result["valid"] is True
        assert result["error_count"] == 0

    def test_validate_papers_invalid(self, tmp_phage_dir, sample_paper_list):
        data = copy.deepcopy(sample_paper_list)
        data["papers"][0]["paper_id"] = "INVALID"
        path = tmp_phage_dir / "01_papers" / "paper_list.json"
        path.write_text(json.dumps(data))
        result = validate_papers(path)
        assert result["valid"] is False
        assert result["error_count"] > 0

    def test_validate_extraction_valid(self, tmp_phage_dir, sample_extraction):
        path = tmp_phage_dir / "02_extractions" / "per_paper" / "P001_extraction.json"
        path.write_text(json.dumps(sample_extraction))
        result = validate_extraction(path)
        assert result["valid"] is True

    def test_validate_extraction_invalid(self, tmp_phage_dir, sample_extraction):
        data = copy.deepcopy(sample_extraction)
        data["relationships"][0]["properties"]["confidence"] = 2.0
        path = tmp_phage_dir / "02_extractions" / "per_paper" / "P001_extraction.json"
        path.write_text(json.dumps(data))
        result = validate_extraction(path)
        assert result["valid"] is False

    def test_validate_graph_valid(self, tmp_phage_dir, sample_graph_data):
        nodes_path = tmp_phage_dir / "03_graph" / "nodes.json"
        edges_path = tmp_phage_dir / "03_graph" / "edges.json"
        nodes_path.write_text(json.dumps(sample_graph_data["nodes"]))
        edges_path.write_text(json.dumps(sample_graph_data["edges"]))
        meta = {
            "generated": sample_graph_data["generated"],
            "total_nodes": sample_graph_data["total_nodes"],
            "total_edges": sample_graph_data["total_edges"],
        }
        meta_path = tmp_phage_dir / "03_graph" / "graph_meta.json"
        meta_path.write_text(json.dumps(meta))
        result = validate_graph(tmp_phage_dir / "03_graph")
        assert result["valid"] is True

    def test_validate_graph_orphan_edge(self, tmp_phage_dir, sample_graph_data):
        data = copy.deepcopy(sample_graph_data)
        data["edges"][0]["from_id"] = "nonexistent"
        nodes_path = tmp_phage_dir / "03_graph" / "nodes.json"
        edges_path = tmp_phage_dir / "03_graph" / "edges.json"
        nodes_path.write_text(json.dumps(data["nodes"]))
        edges_path.write_text(json.dumps(data["edges"]))
        meta = {
            "generated": data["generated"],
            "total_nodes": data["total_nodes"],
            "total_edges": data["total_edges"],
        }
        meta_path = tmp_phage_dir / "03_graph" / "graph_meta.json"
        meta_path.write_text(json.dumps(meta))
        result = validate_graph(tmp_phage_dir / "03_graph")
        assert result["valid"] is False
