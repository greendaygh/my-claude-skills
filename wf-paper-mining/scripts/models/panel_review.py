from __future__ import annotations
from typing import Literal
from .base import StrictModel


class ExpertResponse(StrictModel):
    expert_id: str
    expert_name: str
    score: float | None = None
    assessment: str = ""
    verdict: str = ""
    flags: list[str] = []


class RunTaggedReview(StrictModel):
    paper_id: str
    reviewed_in_run: int
    verdict: str
    experts: list[ExpertResponse] = []
    reason: str = ""


class PanelRunRecord(StrictModel):
    run_id: int
    panel_mode: Literal["full", "quick", "skip"]
    input_prompt: dict = {}
    round_1_responses: dict = {}
    round_2_discussion: list[str] = []
    round_3_votes: dict = {}
    final_verdicts: dict[str, str] = {}
    timestamp: str = ""


class PanelReview(StrictModel):
    panel_type: str
    workflow_id: str
    language: str = "ko"
    cumulative_reviews: int = 0
    latest_run: int = 0
    paper_reviews: list[RunTaggedReview] = []
