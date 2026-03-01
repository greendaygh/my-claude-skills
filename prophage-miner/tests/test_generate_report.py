"""Tests for generate_report.py - Catalog, matrix, inventory, and markdown report."""

import json
from pathlib import Path

import pytest

from scripts.generate_report import (
    build_prophage_catalog,
    build_host_range_matrix,
    build_gene_inventory,
    generate_markdown_report,
    generate_reports,
)


@pytest.fixture
def graph_data_files(tmp_phage_dir, sample_graph_data):
    """Write graph data files to tmp_phage_dir/03_graph/."""
    graph_dir = tmp_phage_dir / "03_graph"
    (graph_dir / "nodes.json").write_text(json.dumps(sample_graph_data["nodes"]))
    (graph_dir / "edges.json").write_text(json.dumps(sample_graph_data["edges"]))
    return graph_dir


@pytest.fixture
def richer_graph_data(tmp_phage_dir):
    """Create richer graph data with multiple prophages and hosts."""
    nodes = [
        {
            "id": "prophage_dlp12",
            "label": "Prophage",
            "properties": {"name": "DLP12", "host_organism": "E. coli K-12", "genome_size_kb": 21.3, "completeness": "intact"},
            "source_papers": ["P001"],
            "merged_count": 1,
        },
        {
            "id": "prophage_gifsy1",
            "label": "Prophage",
            "properties": {"name": "Gifsy-1", "host_organism": "S. enterica", "genome_size_kb": 48.0, "completeness": "intact"},
            "source_papers": ["P002"],
            "merged_count": 1,
        },
        {
            "id": "gene_int_dlp12",
            "label": "Gene",
            "properties": {"name": "intDLP12", "category": "integration", "function": "integrase"},
            "source_papers": ["P001"],
            "merged_count": 1,
        },
        {
            "id": "gene_holin",
            "label": "Gene",
            "properties": {"name": "holin", "category": "lysis", "function": "holin protein"},
            "source_papers": ["P001", "P002"],
            "merged_count": 2,
        },
        {
            "id": "gene_capsid",
            "label": "Gene",
            "properties": {"name": "capsid", "category": "structural", "function": "capsid assembly"},
            "source_papers": ["P002"],
            "merged_count": 1,
        },
        {
            "id": "host_ecoli",
            "label": "Host",
            "properties": {"species": "Escherichia coli", "strain": "K-12"},
            "source_papers": ["P001"],
            "merged_count": 1,
        },
        {
            "id": "host_salmonella",
            "label": "Host",
            "properties": {"species": "Salmonella enterica", "strain": "LT2"},
            "source_papers": ["P002"],
            "merged_count": 1,
        },
    ]
    edges = [
        {
            "id": "edge_encodes_dlp12_int",
            "type": "ENCODES",
            "from_id": "prophage_dlp12",
            "to_id": "gene_int_dlp12",
            "properties": {},
            "avg_confidence": 0.9,
            "source_papers": ["P001"],
        },
        {
            "id": "edge_integrates_dlp12_ecoli",
            "type": "INTEGRATES_INTO",
            "from_id": "prophage_dlp12",
            "to_id": "host_ecoli",
            "properties": {"mechanism": "site-specific"},
            "avg_confidence": 0.85,
            "source_papers": ["P001"],
        },
        {
            "id": "edge_integrates_gifsy_sal",
            "type": "INTEGRATES_INTO",
            "from_id": "prophage_gifsy1",
            "to_id": "host_salmonella",
            "properties": {"mechanism": "site-specific"},
            "avg_confidence": 0.88,
            "source_papers": ["P002"],
        },
    ]
    graph_dir = tmp_phage_dir / "03_graph"
    (graph_dir / "nodes.json").write_text(json.dumps(nodes))
    (graph_dir / "edges.json").write_text(json.dumps(edges))
    return graph_dir, nodes, edges


class TestProphageCatalog:
    def test_build_prophage_catalog_structure(self, richer_graph_data):
        _, nodes, edges = richer_graph_data
        catalog = build_prophage_catalog(nodes, edges)
        assert "prophages" in catalog
        assert len(catalog["prophages"]) == 2
        names = {p["name"] for p in catalog["prophages"]}
        assert "DLP12" in names
        assert "Gifsy-1" in names
        for entry in catalog["prophages"]:
            assert "name" in entry
            assert "host_organism" in entry

    def test_catalog_includes_genes(self, richer_graph_data):
        _, nodes, edges = richer_graph_data
        catalog = build_prophage_catalog(nodes, edges)
        dlp12 = [p for p in catalog["prophages"] if p["name"] == "DLP12"][0]
        assert len(dlp12["encoded_genes"]) >= 1


class TestHostRangeMatrix:
    def test_build_host_range_matrix(self, richer_graph_data):
        _, nodes, edges = richer_graph_data
        matrix = build_host_range_matrix(nodes, edges)
        assert "hosts" in matrix
        assert "prophages" in matrix
        assert "matrix" in matrix
        assert len(matrix["hosts"]) == 2
        assert len(matrix["prophages"]) == 2


class TestGeneInventory:
    def test_build_gene_inventory_categories(self, richer_graph_data):
        _, nodes, edges = richer_graph_data
        inventory = build_gene_inventory(nodes)
        assert "total_genes" in inventory
        assert inventory["total_genes"] == 3
        assert "by_category" in inventory
        assert "integration" in inventory["by_category"]
        assert "lysis" in inventory["by_category"]
        assert "structural" in inventory["by_category"]


class TestMarkdownReport:
    def test_generate_markdown_has_sections(self, richer_graph_data):
        _, nodes, edges = richer_graph_data
        catalog = build_prophage_catalog(nodes, edges)
        matrix = build_host_range_matrix(nodes, edges)
        inventory = build_gene_inventory(nodes)
        md = generate_markdown_report(catalog, matrix, inventory)
        assert "# Prophage Research Report" in md
        assert "## Prophage Catalog" in md
        assert "## Host Range" in md
        assert "## Gene Inventory" in md
        assert "DLP12" in md


class TestGenerateReportsFull:
    def test_generate_reports_creates_files(self, tmp_phage_dir, richer_graph_data):
        graph_dir, _, _ = richer_graph_data
        generate_reports(graph_dir, tmp_phage_dir)
        assert (tmp_phage_dir / "04_analysis" / "prophage_catalog.json").exists()
        assert (tmp_phage_dir / "04_analysis" / "host_range_matrix.json").exists()
        assert (tmp_phage_dir / "04_analysis" / "gene_inventory.json").exists()
        assert (tmp_phage_dir / "05_reports" / "research_report.md").exists()
