from __future__ import annotations
from typing import Literal
from pydantic import model_validator
from .base import StrictModel


class PaperStatus(StrictModel):
    doi: str = ""
    status: Literal["pending", "fetched", "extracted", "rejected", "failed"] = "pending"
    run_id: int = 0
    panel_verdict: Literal["accept", "reject", "flag_reextract"] | None = None
    error: str | None = None


class SaturationMetrics(StrictModel):
    total_unique_papers: int = 0
    overlap_ratio_last_run: float = 0.0
    saturation_level: str = "productive"


class StableCache(StrictModel):
    panel_a_completed: bool = False
    uo_candidates: list[str] = []
    cached_at: str = ""


class RunRecord(StrictModel):
    run_id: int
    run_date: str = ""
    papers_searched: int = 0
    papers_selected: int = 0
    papers_accepted: int = 0
    new_extractions: int = 0
    new_variants: int = 0
    panels_run: list[str] = []
    panel_mode: str = "full"


class WorkflowEntry(StrictModel):
    domain: str = ""
    runs: list[RunRecord] = []
    paper_status: dict[str, PaperStatus] = {}
    known_dois: list[str] = []
    saturation: SaturationMetrics | None = None
    stable_cache: StableCache | None = None
    last_error: str | None = None


class GlobalStats(StrictModel):
    total_runs: int = 0
    total_papers: int = 0
    total_extracted: int = 0


class RunRegistry(StrictModel):
    schema_version: str = "1.0.0"
    created: str = ""
    last_updated: str = ""
    global_stats: GlobalStats = GlobalStats()
    workflows: dict[str, WorkflowEntry] = {}


# --- v2.0: Per-workflow state files ---


class WorkflowState(StrictModel):
    """Per-workflow state file (wf_state.json)."""
    schema_version: str = "2.0.0"
    workflow_id: str
    domain: str = ""
    runs: list[RunRecord] = []
    paper_status: dict[str, PaperStatus] = {}
    known_dois: list[str] = []
    saturation: SaturationMetrics | None = None
    stable_cache: StableCache | None = None
    last_error: str | None = None

    @model_validator(mode="after")
    def _validate_known_dois_coverage(self) -> "WorkflowState":
        """All DOIs in paper_status must appear in known_dois."""
        doi_set = set(self.known_dois)
        for pid, ps in self.paper_status.items():
            if ps.doi and ps.doi not in doi_set:
                raise ValueError(
                    f"paper {pid} DOI '{ps.doi}' not in known_dois"
                )
        return self

    @model_validator(mode="after")
    def _validate_run_id_references(self) -> "WorkflowState":
        """All run_id refs in paper_status must exist in runs."""
        valid_run_ids = {r.run_id for r in self.runs}
        if not valid_run_ids:
            return self
        for pid, ps in self.paper_status.items():
            if ps.run_id and ps.run_id not in valid_run_ids:
                raise ValueError(
                    f"paper {pid} references run_id={ps.run_id} "
                    f"not in runs {valid_run_ids}"
                )
        return self


class WorkflowIndexEntry(StrictModel):
    """Per-workflow summary inside registry_index.json."""
    domain: str = ""
    run_count: int = 0
    paper_count: int = 0
    extracted_count: int = 0
    last_updated: str = ""


class RegistryIndex(StrictModel):
    """Lightweight global index (registry_index.json)."""
    schema_version: str = "2.0.0"
    created: str = ""
    last_updated: str = ""
    workflows: dict[str, WorkflowIndexEntry] = {}

    @model_validator(mode="after")
    def _validate_counts(self) -> "RegistryIndex":
        for wf_id, entry in self.workflows.items():
            if entry.extracted_count > entry.paper_count:
                raise ValueError(
                    f"{wf_id}: extracted_count ({entry.extracted_count}) "
                    f"> paper_count ({entry.paper_count})"
                )
        return self
