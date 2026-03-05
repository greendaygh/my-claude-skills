from __future__ import annotations
from typing import Literal

from pydantic import field_validator

from .base import StrictModel


class PhaseConfig(StrictModel):
    phase2_search: bool
    phase3_fetch: bool
    phase4_extract: bool
    phase4_5_aggregate: bool


class PanelDecision(StrictModel):
    run: bool
    mode: Literal["full", "quick", "skip"] = "skip"
    reason: str = ""


class PanelConfig(StrictModel):
    panel_b: PanelDecision
    panel_c: PanelDecision


class SearchConfig(StrictModel):
    exclude_dois: list[str] = []
    select_n: int = 10
    seed: int

    @field_validator("seed")
    @classmethod
    def seed_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("seed must be > 0")
        return v


class FilePaths(StrictModel):
    extraction_guide: str
    panel_protocol: str
    extraction_template: str
    panel_configs: str
    wf_output_dir: str
    domain_context: str


class SessionContext(StrictModel):
    domain: str
    uo_candidates: list[str]
    wf_description: str


class RunManifest(StrictModel):
    workflow_id: str
    run_id: int
    action: Literal["execute", "skip"]
    reason: str = ""
    phases: PhaseConfig
    panels: PanelConfig
    search_config: SearchConfig | None = None
    pending_papers: list[str] = []
    pending_extractions: list[str] = []
    file_paths: FilePaths
    session_context: SessionContext
