from __future__ import annotations
from typing import Literal
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
