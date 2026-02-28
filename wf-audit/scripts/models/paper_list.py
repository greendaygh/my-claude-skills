"""Canonical Pydantic model for paper_list.json.

Canonical key mappings:
  - id → paper_id
  - authors (array) → authors (string, join with ", ")
"""

from typing import Optional

from pydantic import BaseModel

from .base import ALLOW_EXTRA


class Paper(BaseModel):
    model_config = ALLOW_EXTRA

    paper_id: str
    doi: str
    title: str
    authors: str
    year: int
    journal: str
    pmid: Optional[str] = None
    pmcid: Optional[str] = None
    access_tier: Optional[int] = None
    access_method: Optional[str] = None
    relevance: Optional[str] = None


class PaperList(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    total_papers: int
    search_date: Optional[str] = None
    papers: list[Paper]
