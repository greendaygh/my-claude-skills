"""Tests for build_graph.py - Entity merging, graph construction, and export."""

import json
import copy
from pathlib import Path

import pytest

from scripts.build_graph import (
    load_extractions,
    merge_entities,
    build_edges,
    add_provenance,
    build_graph,
    export_graphml,
    export_csv,
)


@pytest.fixture
def two_paper_extractions(tmp_phage_dir, sample_extraction):
    """Create two extraction files with overlapping entities."""
    per_paper = tmp_phage_dir / "02_extractions" / "per_paper"

    ext1 = copy.deepcopy(sample_extraction)
    ext1["paper_id"] = "P001"
    (per_paper / "P001_extraction.json").write_text(json.dumps(ext1))

    ext2 = copy.deepcopy(sample_extraction)
    ext2["paper_id"] = "P002"
    ext2["entities"][0]["properties"]["genome_size_kb"] = 22.0
    ext2["relationships"][0]["properties"]["confidence"] = 0.85
    (per_paper / "P002_extraction.json").write_text(json.dumps(ext2))

    return per_paper


@pytest.fixture
def diff_organism_extractions(tmp_phage_dir, sample_extraction):
    """Create two extractions with same prophage name but different organisms."""
    per_paper = tmp_phage_dir / "02_extractions" / "per_paper"

    ext1 = copy.deepcopy(sample_extraction)
    ext1["paper_id"] = "P001"
    (per_paper / "P001_extraction.json").write_text(json.dumps(ext1))

    ext2 = copy.deepcopy(sample_extraction)
    ext2["paper_id"] = "P002"
    ext2["entities"][0]["properties"]["host_organism"] = "Salmonella enterica"
    (per_paper / "P002_extraction.json").write_text(json.dumps(ext2))

    return per_paper


class TestLoadExtractions:
    def test_load_extractions(self, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        assert len(extractions) == 2

    def test_load_empty_dir(self, tmp_phage_dir):
        per_paper = tmp_phage_dir / "02_extractions" / "per_paper"
        extractions = load_extractions(per_paper)
        assert extractions == []

    def test_load_excludes_rejected(self, two_paper_extractions):
        reg = {
            "paper_status": {
                "P001": {"status": "extracted"},
                "P002": {"status": "rejected"},
            }
        }
        extractions = load_extractions(two_paper_extractions, paper_status=reg.get("paper_status"))
        assert len(extractions) == 1
        assert extractions[0]["paper_id"] == "P001"


class TestMergeEntities:
    def test_merge_entities_same_name(self, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        nodes = merge_entities(extractions)
        prophage_nodes = [n for n in nodes if n["label"] == "Prophage"]
        assert len(prophage_nodes) == 1
        assert prophage_nodes[0]["merged_count"] == 2
        assert set(prophage_nodes[0]["source_papers"]) == {"P001", "P002"}

    def test_merge_entities_different_organisms(self, diff_organism_extractions):
        extractions = load_extractions(diff_organism_extractions)
        nodes = merge_entities(extractions)
        prophage_nodes = [n for n in nodes if n["label"] == "Prophage"]
        assert len(prophage_nodes) == 2


class TestBuildEdges:
    def test_build_edges_confidence_average(self, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        nodes = merge_entities(extractions)
        edges = build_edges(extractions, nodes)
        encodes_edges = [e for e in edges if e["type"] == "ENCODES"]
        assert len(encodes_edges) == 1
        assert 0.85 <= encodes_edges[0]["avg_confidence"] <= 0.95


class TestProvenance:
    def test_add_provenance_links(self, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        nodes = merge_entities(extractions)
        edges = build_edges(extractions, nodes)
        nodes, edges = add_provenance(nodes, edges, extractions)
        paper_nodes = [n for n in nodes if n["label"] == "Paper"]
        assert len(paper_nodes) >= 1
        ef_edges = [e for e in edges if e["type"] == "EXTRACTED_FROM"]
        assert len(ef_edges) > 0


class TestExport:
    def test_export_graphml_valid(self, tmp_phage_dir, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        nodes = merge_entities(extractions)
        edges = build_edges(extractions, nodes)
        export_path = tmp_phage_dir / "03_graph" / "exports" / "graph.graphml"
        export_graphml(nodes, edges, export_path)
        assert export_path.exists()
        import networkx as nx
        G = nx.read_graphml(str(export_path))
        assert G.number_of_nodes() > 0

    def test_export_csv_two_files(self, tmp_phage_dir, two_paper_extractions):
        extractions = load_extractions(two_paper_extractions)
        nodes = merge_entities(extractions)
        edges = build_edges(extractions, nodes)
        exports_dir = tmp_phage_dir / "03_graph" / "exports"
        export_csv(nodes, edges, exports_dir)
        assert (exports_dir / "nodes.csv").exists()
        assert (exports_dir / "edges.csv").exists()


class TestBuildGraphFull:
    def test_build_graph_output_files(self, tmp_phage_dir, two_paper_extractions):
        graph_dir = tmp_phage_dir / "03_graph"
        build_graph(two_paper_extractions, graph_dir)
        assert (graph_dir / "nodes.json").exists()
        assert (graph_dir / "edges.json").exists()
        assert (graph_dir / "graph_meta.json").exists()
        nodes = json.loads((graph_dir / "nodes.json").read_text())
        assert len(nodes) > 0

    def test_rejected_papers_excluded(self, two_paper_extractions, tmp_phage_dir):
        paper_status = {
            "P001": {"status": "extracted"},
            "P002": {"status": "rejected"},
        }
        graph_dir = tmp_phage_dir / "03_graph"
        build_graph(two_paper_extractions, graph_dir, paper_status=paper_status)
        nodes = json.loads((graph_dir / "nodes.json").read_text())
        for n in nodes:
            assert "P002" not in n["source_papers"]
