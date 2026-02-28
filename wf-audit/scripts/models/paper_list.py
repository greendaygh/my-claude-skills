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
    abstract: Optional[str] = None
    enrichment_status: Optional[str] = None
    text_source: Optional[str] = None
    openalex_id: Optional[str] = None
    oa_status: Optional[str] = None
    cited_by_count: Optional[int] = None
    mesh_terms: Optional[list[str]] = None


class PaperList(BaseModel):
    model_config = ALLOW_EXTRA

    workflow_id: str
    total_papers: int
    search_date: Optional[str] = None
    papers: list[Paper]
