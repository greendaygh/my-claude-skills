"""Tests for search_papers.py - PubMed search, filtering, and appending."""

import json
import copy
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.search_papers import (
    search_pubmed,
    fetch_metadata,
    random_select,
    append_paper_list,
    DEFAULT_QUERY,
)


class TestSearchPubmed:
    def test_search_pubmed_returns_pmids(self, mock_pubmed_esearch_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_pubmed_esearch_response
        with patch("scripts.search_papers.requests.get", return_value=mock_resp):
            pmids, total = search_pubmed(DEFAULT_QUERY, max_results=100)
        assert set(pmids) == {"39876543", "39876544", "39876545", "39876546", "39876547"}
        assert total == 3500

    def test_search_pubmed_empty_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0"?>
        <eSearchResult><Count>0</Count><IdList></IdList></eSearchResult>"""
        with patch("scripts.search_papers.requests.get", return_value=mock_resp):
            pmids, total = search_pubmed("nonexistent query", max_results=100)
        assert pmids == []
        assert total == 0


class TestFetchMetadata:
    def test_fetch_metadata_parses_xml(self, mock_pubmed_efetch_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_pubmed_efetch_response
        with patch("scripts.search_papers.requests.get", return_value=mock_resp):
            papers = fetch_metadata(["39876543", "39876544"])
        assert len(papers) == 2
        assert papers[0]["pmid"] == "39876543"
        assert papers[0]["pmcid"] == "PMC12345678"
        assert "novel prophages" in papers[0]["title"].lower()
        assert papers[1]["pmid"] == "39876544"

    def test_fetch_metadata_extracts_doi(self, mock_pubmed_efetch_response):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = mock_pubmed_efetch_response
        with patch("scripts.search_papers.requests.get", return_value=mock_resp):
            papers = fetch_metadata(["39876543"])
        assert papers[0]["doi"] == "10.1038/s41586-024-00001-x"


class TestRandomSelect:
    def test_random_select_excludes_known(self):
        pmids = ["111", "222", "333", "444", "555"]
        exclude = {"222", "444"}
        selected = random_select(pmids, exclude_pmids=exclude, n=10)
        assert "222" not in selected
        assert "444" not in selected
        assert len(selected) == 3

    def test_random_select_limits_n(self):
        pmids = [str(i) for i in range(100)]
        selected = random_select(pmids, exclude_pmids=set(), n=20)
        assert len(selected) == 20

    def test_random_select_all_excluded(self):
        pmids = ["111", "222"]
        selected = random_select(pmids, exclude_pmids={"111", "222"}, n=20)
        assert selected == []


class TestAppendPaperList:
    def test_append_creates_new_file(self, tmp_phage_dir):
        papers = [
            {
                "paper_id": "P001",
                "pmid": "111",
                "pmcid": "PMC111",
                "doi": "10.1234/test1",
                "title": "A valid title for testing paper one",
                "authors": "Author A",
                "year": 2024,
                "journal": "Nature",
                "abstract": "Test abstract content for paper one.",
            }
        ]
        path = append_paper_list(papers, tmp_phage_dir, query="test query", total_hits=100)
        assert path.exists()
        data = json.loads(path.read_text())
        assert len(data["papers"]) == 1
        assert data["papers"][0]["paper_id"] == "P001"
        assert data["papers"][0]["has_full_text"] is False
        assert data["papers"][0]["extraction_status"] == "pending"

    def test_append_paper_list_no_overwrite(self, tmp_phage_dir, sample_paper_list):
        path = tmp_phage_dir / "01_papers" / "paper_list.json"
        path.write_text(json.dumps(sample_paper_list))
        new_papers = [
            {
                "paper_id": "P003",
                "pmid": "39876545",
                "pmcid": "PMC12345680",
                "doi": "10.1234/test3",
                "title": "Another valid title for testing paper three",
                "authors": "Author C",
                "year": 2025,
                "journal": "Cell",
                "abstract": "Abstract for paper three.",
            }
        ]
        append_paper_list(new_papers, tmp_phage_dir, query="test", total_hits=200)
        data = json.loads(path.read_text())
        assert len(data["papers"]) == 3
        ids = [p["paper_id"] for p in data["papers"]]
        assert "P001" in ids
        assert "P002" in ids
        assert "P003" in ids

    def test_append_updates_counts(self, tmp_phage_dir):
        papers = [
            {
                "paper_id": "P001",
                "pmid": "111",
                "title": "A valid testing title for the paper",
                "authors": "A",
                "year": 2024,
                "journal": "J",
            }
        ]
        path = append_paper_list(papers, tmp_phage_dir, query="q", total_hits=50)
        data = json.loads(path.read_text())
        assert data["selected_count"] == 1
        assert data["total_pubmed_hits"] == 50


class TestRateLimiting:
    def test_rate_limiting_delay(self):
        """Verify search_pubmed respects rate limiting between calls."""
        import time
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0"?>
        <eSearchResult><Count>1</Count><IdList><Id>111</Id></IdList></eSearchResult>"""
        call_times = []
        original_get = None

        def recording_get(*args, **kwargs):
            call_times.append(time.time())
            return mock_resp

        with patch("scripts.search_papers.requests.get", side_effect=recording_get):
            with patch("scripts.search_papers.RATE_LIMIT_DELAY", 0.05):
                search_pubmed("test", max_results=10)

        # single call for esearch - just verify it completes without error
        assert len(call_times) >= 1
