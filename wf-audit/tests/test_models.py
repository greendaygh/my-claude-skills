"""Tests for Pydantic canonical models."""

import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))


# ---------------------------------------------------------------------------
# CompositionData
# ---------------------------------------------------------------------------

class TestCompositionData:
    def test_valid(self):
        from models import CompositionData
        data = {
            "schema_version": "4.0.0",
            "workflow_id": "WB005",
            "workflow_name": "Test",
            "category": "Build",
            "domain": "DNA",
            "version": 1,
            "composition_date": "2026-01-01",
            "description": "Test workflow",
            "statistics": {
                "papers_analyzed": 5,
                "cases_collected": 10,
                "variants_identified": 3,
                "total_uos": 8,
                "qc_checkpoints": 2,
                "confidence_score": 0.85,
            },
        }
        obj = CompositionData.model_validate(data)
        assert obj.workflow_id == "WB005"

    def test_missing_statistics(self):
        from models import CompositionData
        data = {
            "schema_version": "4.0.0",
            "workflow_id": "WB005",
            "workflow_name": "Test",
            "category": "Build",
            "domain": "DNA",
            "version": 1,
            "composition_date": "2026-01-01",
            "description": "Test",
        }
        with pytest.raises(ValidationError) as exc:
            CompositionData.model_validate(data)
        errors = exc.value.errors()
        assert any(e["loc"] == ("statistics",) for e in errors)

    def test_bad_schema_version(self):
        from models import CompositionData
        data = {
            "schema_version": "3.0.0",
            "workflow_id": "WB005",
            "workflow_name": "T",
            "category": "B",
            "domain": "D",
            "version": 1,
            "composition_date": "2026",
            "description": "T",
            "statistics": {
                "papers_analyzed": 1,
                "cases_collected": 1,
                "variants_identified": 1,
                "total_uos": 1,
                "qc_checkpoints": 1,
                "confidence_score": 0.5,
            },
        }
        with pytest.raises(ValidationError) as exc:
            CompositionData.model_validate(data)
        errors = exc.value.errors()
        assert any("pattern" in str(e["type"]) for e in errors)

    def test_extra_fields_allowed(self):
        from models import CompositionData
        data = {
            "schema_version": "4.0.0",
            "workflow_id": "WB005",
            "workflow_name": "T",
            "category": "B",
            "domain": "D",
            "version": 1,
            "composition_date": "2026",
            "description": "T",
            "statistics": {
                "papers_analyzed": 1,
                "cases_collected": 1,
                "variants_identified": 1,
                "total_uos": 1,
                "qc_checkpoints": 1,
                "confidence_score": 0.5,
            },
            "custom_field": "value",
        }
        obj = CompositionData.model_validate(data)
        assert obj.workflow_id == "WB005"


# ---------------------------------------------------------------------------
# PaperList
# ---------------------------------------------------------------------------

class TestPaperList:
    def test_valid(self):
        from models import PaperList
        data = {
            "workflow_id": "WB005",
            "total_papers": 1,
            "papers": [
                {
                    "paper_id": "P001",
                    "doi": "10.1000/abc",
                    "title": "Test",
                    "authors": "Smith J",
                    "year": 2023,
                    "journal": "Nature",
                }
            ],
        }
        obj = PaperList.model_validate(data)
        assert len(obj.papers) == 1

    def test_authors_must_be_string(self):
        from models import PaperList
        data = {
            "workflow_id": "WB005",
            "total_papers": 1,
            "papers": [
                {
                    "paper_id": "P001",
                    "doi": "10.1000/abc",
                    "title": "Test",
                    "authors": ["Smith J"],
                    "year": 2023,
                    "journal": "Nature",
                }
            ],
        }
        with pytest.raises(ValidationError):
            PaperList.model_validate(data)


# ---------------------------------------------------------------------------
# CaseCard
# ---------------------------------------------------------------------------

class TestCaseCard:
    def test_valid(self):
        from models import CaseCard
        data = {
            "case_id": "WB005-C001",
            "metadata": {"title": "Test"},
            "steps": [
                {
                    "step_number": 1,
                    "step_name": "Step 1",
                    "description": "Do something",
                }
            ],
            "completeness": {"score": 0.9},
            "flow_diagram": "graph LR A-->B",
            "workflow_context": {"workflow_id": "WB005"},
        }
        obj = CaseCard.model_validate(data)
        assert obj.case_id == "WB005-C001"

    def test_bad_case_id(self):
        from models import CaseCard
        data = {
            "case_id": "C001",
            "metadata": {"title": "Test"},
            "steps": [{"step_number": 1, "step_name": "S", "description": "D"}],
            "completeness": {"score": 0.9},
            "flow_diagram": "g",
            "workflow_context": {"workflow_id": "WB005"},
        }
        with pytest.raises(ValidationError) as exc:
            CaseCard.model_validate(data)
        errors = exc.value.errors()
        assert any("case_id" in str(e["loc"]) for e in errors)


# ---------------------------------------------------------------------------
# Variant (canonical)
# ---------------------------------------------------------------------------

class TestVariant:
    def test_valid_canonical(self):
        from models import Variant
        data = {
            "variant_id": "V1",
            "variant_name": "UV Spectrophotometry",
            "workflow_id": "WB005",
            "unit_operations": [
                {
                    "uo_id": "UHW400",
                    "uo_name": "Sample Preparation",
                    "step_position": 1,
                    "input": {"items": []},
                    "output": {"items": []},
                    "equipment": {"items": []},
                    "consumables": {"items": []},
                    "material_and_method": {},
                    "result": {},
                    "discussion": {},
                }
            ],
        }
        obj = Variant.model_validate(data)
        assert obj.variant_id == "V1"
        assert len(obj.unit_operations) == 1

    def test_missing_unit_operations(self):
        from models import Variant
        data = {
            "variant_id": "V1",
            "variant_name": "Test",
            "workflow_id": "WB005",
        }
        with pytest.raises(ValidationError) as exc:
            Variant.model_validate(data)
        errors = exc.value.errors()
        assert any(e["loc"] == ("unit_operations",) for e in errors)

    def test_legacy_format_fails(self):
        """Legacy format with 'name' instead of 'variant_name' should fail."""
        from models import Variant
        data = {
            "variant_id": "V1",
            "name": "Legacy Name",
            "workflow_id": "WB005",
            "uo_sequence": ["UO-001", "UO-002"],
        }
        with pytest.raises(ValidationError) as exc:
            Variant.model_validate(data)
        error_locs = [e["loc"] for e in exc.value.errors()]
        assert ("variant_name",) in error_locs
        assert ("unit_operations",) in error_locs


# ---------------------------------------------------------------------------
# CaseSummary
# ---------------------------------------------------------------------------

class TestCaseSummary:
    def test_valid(self):
        from models import CaseSummary
        data = {
            "workflow_id": "WB005",
            "total_cases": 2,
            "cases": [{"case_id": "WB005-C001"}, {"case_id": "WB005-C002"}],
        }
        obj = CaseSummary.model_validate(data)
        assert obj.total_cases == 2


# ---------------------------------------------------------------------------
# Analysis models
# ---------------------------------------------------------------------------

class TestAnalysisModels:
    def test_cluster_result(self):
        from models import ClusterResult
        data = {
            "workflow_id": "WB005",
            "total_cases": 5,
            "variants": [{"variant_id": "V1", "name": "Standard"}],
        }
        obj = ClusterResult.model_validate(data)
        assert len(obj.variants) == 1

    def test_common_pattern(self):
        from models import CommonPattern
        data = {
            "workflow_id": "WB005",
            "total_cases": 5,
            "workflow_skeleton": {"common_steps": []},
        }
        obj = CommonPattern.model_validate(data)
        assert obj.workflow_id == "WB005"


# ---------------------------------------------------------------------------
# DetailedViolation helpers
# ---------------------------------------------------------------------------

class TestDetailedViolation:
    def test_pydantic_errors_to_violations(self):
        from models.base import pydantic_errors_to_violations, DetailedViolation
        from models import CompositionData

        try:
            CompositionData.model_validate({"workflow_id": "WB005"})
        except ValidationError as e:
            violations = pydantic_errors_to_violations(
                e.errors(), source_file="composition_data.json", record_id="WB005",
            )
            assert len(violations) > 0
            for v in violations:
                assert isinstance(v, DetailedViolation)
                assert v.file == "composition_data.json"
                assert v.record == "WB005"
                assert v.error_type in ("missing", "wrong_type", "pattern_mismatch", "value_error")
                assert len(v.fix_hint) > 0

    def test_to_dict(self):
        from models.base import DetailedViolation
        v = DetailedViolation(
            file="test.json", record="R1", path="field_a",
            error="Field required", error_type="missing",
            fix_hint="Add field_a",
        )
        d = v.to_dict()
        assert d["file"] == "test.json"
        assert d["error_type"] == "missing"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
