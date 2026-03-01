"""Tests for fetch_fulltext.py - PMC XML parsing, section splitting, API calls."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.fetch_fulltext import (
    parse_sections,
    fetch_pmc_xml,
    fetch_europepmc,
    save_fulltext,
    process_papers,
)


class TestParseSections:
    def test_parse_sections_from_pmc_xml(self, sample_pmc_xml):
        sections = parse_sections(sample_pmc_xml)
        assert "INTRODUCTION" in sections
        assert "METHODS" in sections
        assert "RESULTS" in sections
        assert "DISCUSSION" in sections
        assert len(sections) >= 4
        assert "PHASTER" in sections["METHODS"]

    def test_parse_sections_missing_methods(self):
        xml = """<?xml version="1.0"?>
        <pmc-articleset>
        <article><body>
          <sec sec-type="intro"><title>Introduction</title><p>Intro text.</p></sec>
          <sec sec-type="results"><title>Results</title><p>Results text.</p></sec>
        </body></article>
        </pmc-articleset>"""
        sections = parse_sections(xml)
        assert "INTRODUCTION" in sections
        assert "RESULTS" in sections
        assert "METHODS" not in sections

    def test_parse_sections_abstract_only(self):
        xml = """<?xml version="1.0"?>
        <pmc-articleset>
        <article>
          <front><article-meta><abstract><p>Abstract text here.</p></abstract></article-meta></front>
          <body></body>
        </article>
        </pmc-articleset>"""
        sections = parse_sections(xml)
        assert "ABSTRACT" in sections
        assert "Abstract text here." in sections["ABSTRACT"]

    def test_parse_sections_empty_xml(self):
        sections = parse_sections("")
        assert sections == {}

    def test_parse_sections_nested_paragraphs(self):
        xml = """<?xml version="1.0"?>
        <pmc-articleset>
        <article><body>
          <sec sec-type="results">
            <title>Results</title>
            <p>Paragraph 1.</p>
            <p>Paragraph 2.</p>
            <sec><title>Subsection</title><p>Sub para.</p></sec>
          </sec>
        </body></article>
        </pmc-articleset>"""
        sections = parse_sections(xml)
        assert "Paragraph 1." in sections["RESULTS"]
        assert "Sub para." in sections["RESULTS"]


class TestFetchPmcXml:
    def test_fetch_pmc_xml_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<xml>content</xml>"
        with patch("scripts.fetch_fulltext.requests.get", return_value=mock_resp):
            result = fetch_pmc_xml("PMC12345678")
        assert result == "<xml>content</xml>"

    def test_fetch_pmc_xml_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.raise_for_status.side_effect = Exception("503 Service Unavailable")
        with patch("scripts.fetch_fulltext.requests.get", return_value=mock_resp):
            result = fetch_pmc_xml("PMC12345678")
        assert result == ""


class TestFetchEuropePmc:
    def test_fetch_europepmc_fallback(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0"?>
        <article><body>
          <sec sec-type="intro"><title>Introduction</title><p>Europe PMC intro.</p></sec>
        </body></article>"""
        with patch("scripts.fetch_fulltext.requests.get", return_value=mock_resp):
            result = fetch_europepmc("PMC12345678")
        assert "Europe PMC intro" in result

    def test_fetch_europepmc_failure(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = Exception("404")
        with patch("scripts.fetch_fulltext.requests.get", return_value=mock_resp):
            result = fetch_europepmc("PMC12345678")
        assert result == ""


class TestSaveFulltext:
    def test_save_fulltext_format(self, tmp_phage_dir):
        sections = {
            "ABSTRACT": "Abstract content.",
            "INTRODUCTION": "Intro content.",
            "RESULTS": "Results content.",
        }
        path = save_fulltext("P001", sections, tmp_phage_dir)
        assert path.exists()
        text = path.read_text()
        assert "=== ABSTRACT ===" in text
        assert "=== INTRODUCTION ===" in text
        assert "=== RESULTS ===" in text
        assert "Abstract content." in text

    def test_save_fulltext_creates_file_path(self, tmp_phage_dir):
        sections = {"RESULTS": "Data."}
        path = save_fulltext("P042", sections, tmp_phage_dir)
        assert path == tmp_phage_dir / "01_papers" / "full_texts" / "P042.txt"


class TestProcessPapers:
    def test_pending_only_skips_downloaded(self, tmp_phage_dir, sample_paper_list):
        paper_list_path = tmp_phage_dir / "01_papers" / "paper_list.json"
        paper_list_path.write_text(json.dumps(sample_paper_list))

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = """<?xml version="1.0"?>
        <pmc-articleset><article><body>
        <sec sec-type="results"><title>Results</title><p>Data.</p></sec>
        </body></article></pmc-articleset>"""

        with patch("scripts.fetch_fulltext.fetch_pmc_xml", return_value=mock_resp.text):
            stats = process_papers(paper_list_path, tmp_phage_dir, pending_only=True)

        assert stats["skipped"] >= 1
        assert stats["processed"] >= 0

    def test_process_updates_has_full_text(self, tmp_phage_dir):
        paper_list = {
            "search_date": "2026-02-28",
            "query": "test",
            "total_pubmed_hits": 100,
            "selected_count": 1,
            "papers": [{
                "paper_id": "P001",
                "pmid": "111",
                "pmcid": "PMC111",
                "title": "A valid test paper title for fetch testing",
                "authors": "Author",
                "year": 2024,
                "journal": "J",
                "has_full_text": False,
                "extraction_status": "pending",
            }],
        }
        paper_list_path = tmp_phage_dir / "01_papers" / "paper_list.json"
        paper_list_path.write_text(json.dumps(paper_list))

        mock_xml = """<?xml version="1.0"?>
        <pmc-articleset><article><body>
        <sec sec-type="results"><title>Results</title><p>Data found.</p></sec>
        </body></article></pmc-articleset>"""

        with patch("scripts.fetch_fulltext.fetch_pmc_xml", return_value=mock_xml):
            process_papers(paper_list_path, tmp_phage_dir, pending_only=True)

        updated = json.loads(paper_list_path.read_text())
        assert updated["papers"][0]["has_full_text"] is True
