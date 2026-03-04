from __future__ import annotations
from typing import Literal
from .base import StrictModel


class MiningPaper(StrictModel):
    paper_id: str
    pmid: str = ""
    pmcid: str | None = None
    doi: str | None = None
    title: str = ""
    authors: list[str] = []
    year: int = 2024
    journal: str = ""
    abstract: str = ""
    has_full_text: bool = False
    extraction_status: str = "pending"
    added_in_run: int = 0
    source: Literal["pubmed", "openalex", "manual"] = "pubmed"
    panel_b_verdict: str | None = None
    panel_b_score: float | None = None
    panel_b_reason: str | None = None
    panel_verdict: str | None = None


class MiningPaperList(StrictModel):
    search_date: str = ""
    workflow_id: str = ""
    run_id: int = 0
    query: str = ""
    total_search_hits: int = 0
    pubmed_hits: int = 0
    openalex_hits: int = 0
    selected_count: int = 0
    papers: list[MiningPaper] = []
