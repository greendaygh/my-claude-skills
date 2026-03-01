"""Tests for extract_prophage.py - Extraction result validation, saving, and summary."""

import json
import copy
from pathlib import Path

import pytest

from scripts.extract_prophage import (
    validate_extraction_data,
    save_extraction,
    generate_summary,
)


class TestValidateExtraction:
    def test_validate_valid_data(self, sample_extraction, schema_data):
        errors = validate_extraction_data(sample_extraction, schema_data)
        assert errors == []

    def test_validate_unknown_entity_type(self, sample_extraction, schema_data):
        data = copy.deepcopy(sample_extraction)
        data["entities"].append({
            "label": "UnknownType",
            "properties": {"name": "test"},
        })
        errors = validate_extraction_data(data, schema_data)
        assert any("UnknownType" in e for e in errors)

    def test_validate_unknown_relationship_type(self, sample_extraction, schema_data):
        data = copy.deepcopy(sample_extraction)
        data["relationships"].append({
            "type": "UNKNOWN_REL",
            "from": {"label": "Prophage", "key": "DLP12"},
            "to": {"label": "Gene", "key": "int"},
            "properties": {"confidence": 0.5},
        })
        errors = validate_extraction_data(data, schema_data)
        assert any("UNKNOWN_REL" in e for e in errors)

    def test_validate_missing_paper_id(self, sample_extraction, schema_data):
        data = copy.deepcopy(sample_extraction)
        del data["paper_id"]
        errors = validate_extraction_data(data, schema_data)
        assert len(errors) > 0

    def test_validate_confidence_out_of_range(self, sample_extraction, schema_data):
        data = copy.deepcopy(sample_extraction)
        data["relationships"][0]["properties"]["confidence"] = 1.5
        errors = validate_extraction_data(data, schema_data)
        assert any("confidence" in e.lower() for e in errors)


class TestSaveExtraction:
    def test_save_extraction_creates_file(self, tmp_phage_dir, sample_extraction):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        path = save_extraction("P001", sample_extraction, output_dir)
        assert path.exists()
        assert path.name == "P001_extraction.json"

    def test_save_extraction_valid_structure(self, tmp_phage_dir, sample_extraction):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        path = save_extraction("P001", sample_extraction, output_dir)
        data = json.loads(path.read_text())
        assert data["paper_id"] == "P001"
        assert "entities" in data
        assert "relationships" in data

    def test_save_extraction_overwrites(self, tmp_phage_dir, sample_extraction):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        save_extraction("P001", sample_extraction, output_dir)
        modified = copy.deepcopy(sample_extraction)
        modified["entities"] = []
        save_extraction("P001", modified, output_dir)
        data = json.loads((output_dir / "P001_extraction.json").read_text())
        assert data["entities"] == []


class TestGenerateSummary:
    def test_generate_summary_counts(self, tmp_phage_dir, sample_extraction):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        save_extraction("P001", sample_extraction, output_dir)

        ext2 = copy.deepcopy(sample_extraction)
        ext2["paper_id"] = "P002"
        ext2["entities"] = ext2["entities"][:2]
        ext2["relationships"] = ext2["relationships"][:1]
        save_extraction("P002", ext2, output_dir)

        summary = generate_summary(output_dir)
        assert summary["total_papers"] == 2
        assert summary["total_entities"] == 6  # 4 + 2
        assert summary["total_relationships"] == 3  # 2 + 1

    def test_generate_summary_empty(self, tmp_phage_dir):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        summary = generate_summary(output_dir)
        assert summary["total_papers"] == 0
        assert summary["total_entities"] == 0

    def test_generate_summary_entity_types(self, tmp_phage_dir, sample_extraction):
        output_dir = tmp_phage_dir / "02_extractions" / "per_paper"
        save_extraction("P001", sample_extraction, output_dir)
        summary = generate_summary(output_dir)
        assert "Prophage" in summary["entity_type_counts"]
        assert "Gene" in summary["entity_type_counts"]
        assert summary["entity_type_counts"]["Prophage"] == 1
