"""End-to-end integration tests for the prophage-miner pipeline.

Tests the full pipeline (Phase 1-6) with mocked external APIs.
"""

import json
import copy
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from scripts.run_tracker import RunTracker
from scripts.search_papers import search_pubmed, fetch_metadata, random_select, append_paper_list
from scripts.fetch_fulltext import process_papers
from scripts.extract_prophage import save_extraction, generate_summary
from scripts.validate_data import validate_papers, validate_extraction, validate_graph
from scripts.build_graph import build_graph
from scripts.generate_report import generate_reports


@pytest.fixture
def mock_esearch():
    return """<?xml version="1.0"?>
    <eSearchResult><Count>100</Count><RetMax>5</RetMax>
    <IdList>
    <Id>11111</Id><Id>22222</Id><Id>33333</Id>
    </IdList></eSearchResult>"""


@pytest.fixture
def mock_efetch():
    return """<?xml version="1.0"?>
    <PubmedArticleSet>
    <PubmedArticle><MedlineCitation><PMID>11111</PMID>
    <Article><Journal><Title>J Bacteriol</Title></Journal>
    <ArticleTitle>Prophage DLP12 characterization in E. coli K-12 strains</ArticleTitle>
    <Abstract><AbstractText>We characterized DLP12 prophage in E. coli.</AbstractText></Abstract>
    <AuthorList><Author><LastName>Smith</LastName><ForeName>J</ForeName></Author></AuthorList>
    <ArticleIdList><ArticleId IdType="doi">10.1/test1</ArticleId>
    <ArticleId IdType="pmc">PMC1111</ArticleId></ArticleIdList>
    </Article></MedlineCitation>
    <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2024</Year></PubMedPubDate></History></PubmedData>
    </PubmedArticle>
    <PubmedArticle><MedlineCitation><PMID>22222</PMID>
    <Article><Journal><Title>Nat Micro</Title></Journal>
    <ArticleTitle>Gifsy-1 prophage induction in Salmonella enterica serovar Typhimurium</ArticleTitle>
    <Abstract><AbstractText>Gifsy-1 prophage induction was studied.</AbstractText></Abstract>
    <AuthorList><Author><LastName>Kim</LastName><ForeName>H</ForeName></Author></AuthorList>
    <ArticleIdList><ArticleId IdType="doi">10.1/test2</ArticleId>
    <ArticleId IdType="pmc">PMC2222</ArticleId></ArticleIdList>
    </Article></MedlineCitation>
    <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2025</Year></PubMedPubDate></History></PubmedData>
    </PubmedArticle>
    </PubmedArticleSet>"""


@pytest.fixture
def mock_pmc_xml():
    return """<?xml version="1.0"?>
    <pmc-articleset><article><body>
    <sec sec-type="intro"><title>Introduction</title>
    <p>Prophages are widespread in bacterial genomes.</p></sec>
    <sec sec-type="methods"><title>Methods</title>
    <p>PHASTER was used to identify prophage regions.</p></sec>
    <sec sec-type="results"><title>Results</title>
    <p>DLP12 prophage is 21.3 kb and encodes integrase gene intDLP12.</p>
    <p>It integrates at the tRNA-Arg locus of E. coli K-12.</p></sec>
    <sec sec-type="discussion"><title>Discussion</title>
    <p>The prophage contributes to host fitness.</p></sec>
    </body></article></pmc-articleset>"""


def _make_extraction(paper_id):
    """Create a synthetic extraction result."""
    return {
        "paper_id": paper_id,
        "paper_doi": f"10.1/test_{paper_id}",
        "entities": [
            {"label": "Prophage", "properties": {"name": "DLP12", "host_organism": "E. coli K-12", "genome_size_kb": 21.3, "completeness": "intact"}},
            {"label": "Gene", "properties": {"name": "intDLP12", "category": "integration", "function": "integrase"}},
            {"label": "Host", "properties": {"species": "Escherichia coli", "strain": "K-12"}},
        ],
        "relationships": [
            {"type": "ENCODES", "from": {"label": "Prophage", "key": "DLP12"}, "to": {"label": "Gene", "key": "intDLP12"}, "properties": {"confidence": 0.9, "source_section": "results"}},
            {"type": "INTEGRATES_INTO", "from": {"label": "Prophage", "key": "DLP12"}, "to": {"label": "Host", "key": "Escherichia coli"}, "properties": {"confidence": 0.85, "mechanism": "site-specific"}},
        ],
        "unschemaed": [],
    }


class TestFullPipelineSingleRun:
    def test_full_pipeline_single_run(self, tmp_phage_dir, sample_schema, mock_esearch, mock_efetch, mock_pmc_xml):
        tracker = RunTracker(tmp_phage_dir)
        run_id = tracker.start_run()

        # Phase 1: Search
        mock_resp_search = MagicMock(status_code=200, text=mock_esearch)
        mock_resp_fetch = MagicMock(status_code=200, text=mock_efetch)
        with patch("scripts.search_papers.requests.get", side_effect=[mock_resp_search, mock_resp_fetch]):
            pmids, total = search_pubmed("test", max_results=10)
            selected = random_select(pmids, tracker.get_known_pmids(), n=2)
            metadata = fetch_metadata(selected)

        for i, p in enumerate(metadata):
            p["paper_id"] = f"P{i+1:03d}"
        append_paper_list(metadata, tmp_phage_dir, query="test", total_hits=total)
        tracker.add_papers(run_id, metadata)

        result = validate_papers(tmp_phage_dir / "01_papers" / "paper_list.json")
        assert result["valid"] is True

        # Phase 2: Full text
        with patch("scripts.fetch_fulltext.fetch_pmc_xml", return_value=mock_pmc_xml):
            process_papers(tmp_phage_dir / "01_papers" / "paper_list.json", tmp_phage_dir)

        # Phase 3: Extraction (simulated, normally by subagent)
        per_paper_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        for p in metadata:
            ext = _make_extraction(p["paper_id"])
            save_extraction(p["paper_id"], ext, per_paper_dir)
            tracker.mark_extracted(p["paper_id"])

        for f in per_paper_dir.glob("*_extraction.json"):
            r = validate_extraction(f)
            assert r["valid"] is True

        # Phase 5: Graph
        graph_dir = tmp_phage_dir / "03_graph"
        build_graph(per_paper_dir, graph_dir)
        gr = validate_graph(graph_dir)
        assert gr["valid"] is True

        # Phase 6: Report
        generate_reports(graph_dir, tmp_phage_dir)

        tracker.complete_run(run_id)

        # Verify outputs
        assert (tmp_phage_dir / "01_papers" / "paper_list.json").exists()
        assert (tmp_phage_dir / "03_graph" / "nodes.json").exists()
        assert (tmp_phage_dir / "03_graph" / "edges.json").exists()
        assert (tmp_phage_dir / "04_analysis" / "prophage_catalog.json").exists()
        assert (tmp_phage_dir / "05_reports" / "research_report.md").exists()

        s = tracker.summary()
        assert s["total_runs"] == 1
        assert s["total_papers"] >= 1
        assert s["total_extracted"] >= 1


class TestIncrementalSecondRun:
    def test_incremental_second_run(self, tmp_phage_dir, sample_schema, mock_esearch, mock_efetch, mock_pmc_xml):
        """Verify second run adds new papers without overwriting existing."""
        tracker = RunTracker(tmp_phage_dir)

        # Run 1
        r1 = tracker.start_run()
        mock_resp = MagicMock(status_code=200, text=mock_efetch)
        with patch("scripts.search_papers.requests.get", side_effect=[MagicMock(status_code=200, text=mock_esearch), mock_resp]):
            pmids, total = search_pubmed("test", max_results=10)
            selected = random_select(pmids, tracker.get_known_pmids(), n=2)
            metadata = fetch_metadata(selected)

        for i, p in enumerate(metadata):
            p["paper_id"] = f"P{i+1:03d}"
        append_paper_list(metadata, tmp_phage_dir, query="test", total_hits=total)
        tracker.add_papers(r1, metadata)

        per_paper_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        for p in metadata:
            save_extraction(p["paper_id"], _make_extraction(p["paper_id"]), per_paper_dir)
            tracker.mark_extracted(p["paper_id"])
        tracker.complete_run(r1)

        run1_paper_count = len(metadata)

        # Run 2: new search returns different PMIDs
        mock_esearch2 = """<?xml version="1.0"?>
        <eSearchResult><Count>200</Count>
        <IdList><Id>44444</Id><Id>55555</Id></IdList></eSearchResult>"""
        mock_efetch2 = """<?xml version="1.0"?>
        <PubmedArticleSet>
        <PubmedArticle><MedlineCitation><PMID>44444</PMID>
        <Article><Journal><Title>Cell</Title></Journal>
        <ArticleTitle>Novel prophage elements in Pseudomonas aeruginosa biofilm communities</ArticleTitle>
        <Abstract><AbstractText>Novel prophage elements.</AbstractText></Abstract>
        <AuthorList><Author><LastName>Park</LastName><ForeName>S</ForeName></Author></AuthorList>
        <ArticleIdList><ArticleId IdType="doi">10.1/test3</ArticleId>
        <ArticleId IdType="pmc">PMC4444</ArticleId></ArticleIdList>
        </Article></MedlineCitation>
        <PubmedData><History><PubMedPubDate PubStatus="pubmed"><Year>2025</Year></PubMedPubDate></History></PubmedData>
        </PubmedArticle></PubmedArticleSet>"""

        r2 = tracker.start_run()
        with patch("scripts.search_papers.requests.get", side_effect=[
            MagicMock(status_code=200, text=mock_esearch2),
            MagicMock(status_code=200, text=mock_efetch2),
        ]):
            pmids2, total2 = search_pubmed("test", max_results=10)
            selected2 = random_select(pmids2, tracker.get_known_pmids(), n=2)
            metadata2 = fetch_metadata(selected2)

        next_id = int(tracker.get_next_paper_id()[1:])
        for i, p in enumerate(metadata2):
            p["paper_id"] = f"P{next_id + i:03d}"
        append_paper_list(metadata2, tmp_phage_dir, query="test", total_hits=total2)
        tracker.add_papers(r2, metadata2)

        for p in metadata2:
            save_extraction(p["paper_id"], _make_extraction(p["paper_id"]), per_paper_dir)
            tracker.mark_extracted(p["paper_id"])
        tracker.complete_run(r2)

        # Verify incremental: more papers than run 1
        paper_list = json.loads((tmp_phage_dir / "01_papers" / "paper_list.json").read_text())
        assert len(paper_list["papers"]) > run1_paper_count

        s = tracker.summary()
        assert s["total_runs"] == 2


class TestFailedExtractionRecovery:
    def test_failed_extraction_recovery(self, tmp_phage_dir, sample_schema, mock_efetch, mock_pmc_xml):
        """Verify failed papers in run 1 can be recovered in run 2."""
        tracker = RunTracker(tmp_phage_dir)

        r1 = tracker.start_run()
        papers = [
            {"paper_id": "P001", "pmid": "111"},
            {"paper_id": "P002", "pmid": "222"},
        ]
        tracker.add_papers(r1, papers)
        tracker.mark_extracted("P001")
        tracker.mark_extract_failed("P002", "PMC timeout")
        tracker.complete_run(r1)

        assert tracker.get_pending_extractions() == []
        assert tracker.summary()["total_failed"] == 1

        # Run 2: restore failed to pending
        r2 = tracker.start_run()
        tracker._registry["paper_status"]["P002"]["status"] = "pending"
        del tracker._registry["paper_status"]["P002"]["error"]
        tracker._save()

        pending = tracker.get_pending_extractions()
        assert "P002" in pending

        per_paper_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        save_extraction("P002", _make_extraction("P002"), per_paper_dir)
        tracker.mark_extracted("P002")
        tracker.complete_run(r2)

        assert tracker.summary()["total_extracted"] == 2
        assert tracker.summary()["total_failed"] == 0
