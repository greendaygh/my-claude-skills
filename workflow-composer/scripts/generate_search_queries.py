#!/usr/bin/env python3
"""
generate_search_queries.py — Deterministic search query generation for workflow-composer v2.0.

Replaces Expert Panel Round A (search strategy generation).
Generates queries from search_config.json templates and ranks Pass 1 papers
using multi-signal scoring.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

_SCRIPTS_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPTS_DIR.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from scripts import __version__

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"


def load_search_config() -> dict:
    """Load search_config.json. Returns minimal default if file not found."""
    config_path = ASSETS_DIR / "search_config.json"
    if not config_path.exists():
        return {
            "domain_queries": {},
            "default_date_range_years": 10,
            "query_expansion_rules": {"automation_keywords": []},
            "fallback_query": "{workflow_name} protocol automated biofoundry",
        }
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_v2_config() -> dict:
    """Load v2_config.json."""
    config_path = ASSETS_DIR / "v2_config.json"
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_technique_template(workflow_id: str, search_config: dict) -> tuple[dict | None, str | None]:
    """Find technique template for a workflow ID across all domains.

    Returns:
        (template_dict, domain_name) or (None, None) if not found.
    """
    for domain_name, domain_data in search_config.get("domain_queries", {}).items():
        templates = domain_data.get("technique_templates", {})
        if workflow_id in templates:
            return templates[workflow_id], domain_name
    return None, None


def generate_queries(workflow_id: str, workflow_name: str = "",
                     domain: str = "", search_config: dict = None) -> list[dict]:
    """Generate deterministic search queries from config templates.

    Args:
        workflow_id: e.g. "WB030"
        workflow_name: e.g. "DNA Assembly"
        domain: e.g. "Molecular Biology / Cloning"
        search_config: pre-loaded config (loaded if None)

    Returns:
        List of query dicts with 'query', 'source', 'target' fields.
    """
    if search_config is None:
        search_config = load_search_config()

    template, found_domain = find_technique_template(workflow_id, search_config)
    date_range = search_config.get("default_date_range_years", 10)
    current_year = datetime.now().year
    min_year = current_year - date_range

    queries = []

    if template:
        # Primary: keyword-based queries
        keywords = template.get("keywords", [])
        synonyms = template.get("synonyms", [])
        exclusions = template.get("exclusions", [])

        domain_data = {}
        for dname, ddata in search_config.get("domain_queries", {}).items():
            if workflow_id in ddata.get("technique_templates", {}):
                domain_data = ddata
                break

        mesh_terms = domain_data.get("base_mesh", [])

        # Query 1: Primary keywords with MeSH
        all_terms = keywords + synonyms
        if all_terms and mesh_terms:
            synonyms_or = " OR ".join(f'"{t}"' for t in all_terms)
            mesh_or = " OR ".join(f'"{m}"' for m in mesh_terms)
            query = search_config.get("query_template", "({synonyms_OR}) AND (protocol OR methods) AND ({mesh_terms})")
            query = query.replace("{synonyms_OR}", synonyms_or).replace("{mesh_terms}", mesh_or)
            queries.append({
                "query": query,
                "source": "template_primary",
                "target": "websearch",
                "workflow_id": workflow_id,
            })

        # Query 2: Keywords + automation terms
        auto_keywords = search_config.get("query_expansion_rules", {}).get("automation_keywords", [])
        if keywords and auto_keywords:
            kw_or = " OR ".join(f'"{k}"' for k in keywords[:3])
            auto_or = " OR ".join(f'"{a}"' for a in auto_keywords[:3])
            query = f"({kw_or}) AND ({auto_or}) AND protocol"
            queries.append({
                "query": query,
                "source": "template_automation",
                "target": "websearch",
                "workflow_id": workflow_id,
            })

        # Query 3: PubMed-specific query
        if all_terms and mesh_terms:
            pubmed_template = search_config.get("pubmed_query_template", "")
            if pubmed_template:
                synonyms_or = " OR ".join(all_terms[:5])
                mesh_or = " OR ".join(mesh_terms[:3])
                query = pubmed_template.replace("{synonyms_OR}", synonyms_or).replace("{mesh_terms}", mesh_or)
                queries.append({
                    "query": query,
                    "source": "template_pubmed",
                    "target": "pubmed",
                    "workflow_id": workflow_id,
                })

        # Query 4: Preferred journals
        preferred = template.get("preferred_journals", [])
        if preferred and keywords:
            journal_or = " OR ".join(f'"{j}"' for j in preferred[:3])
            kw = keywords[0]
            query = f'"{kw}" AND (protocol OR methods) AND ({journal_or})'
            queries.append({
                "query": query,
                "source": "template_journal",
                "target": "websearch",
                "workflow_id": workflow_id,
            })

        # Query 5: Exclusion-aware broad query
        if keywords:
            kw_or = " OR ".join(f'"{k}"' for k in keywords)
            excl = " ".join(f'-"{e}"' for e in exclusions) if exclusions else ""
            query = f"({kw_or}) AND (protocol OR step-by-step) {excl}".strip()
            queries.append({
                "query": query,
                "source": "template_broad",
                "target": "websearch",
                "workflow_id": workflow_id,
            })

    # Fallback query (always generated)
    fallback_template = search_config.get("fallback_query", "")
    if fallback_template and workflow_name:
        fallback = fallback_template.replace("{workflow_name}", workflow_name)
        queries.append({
            "query": fallback,
            "source": "fallback",
            "target": "websearch",
            "workflow_id": workflow_id,
        })

    # Tag all queries with date range
    for q in queries:
        q["min_year"] = min_year
        q["max_year"] = current_year

    return queries


def _compute_year_recency_score(year: int, current_year: int = None, max_age: int = 15) -> float:
    """Compute year recency score in [0, 1]. Recent years score higher."""
    if current_year is None:
        current_year = datetime.now().year
    if year is None or year < 1900:
        return 0.0
    age = current_year - year
    if age <= 0:
        return 1.0
    if age >= max_age:
        return 0.0
    return round(1.0 - (age / max_age), 3)


def _compute_keyword_overlap(title: str, keywords: list[str]) -> float:
    """Compute Jaccard-like keyword overlap between title and keyword list."""
    if not title or not keywords:
        return 0.0
    title_lower = title.lower()
    title_words = set(re.findall(r'\w+', title_lower))

    matches = 0
    for kw in keywords:
        kw_words = set(re.findall(r'\w+', kw.lower()))
        if kw_words & title_words:
            matches += 1

    return round(matches / len(keywords), 3) if keywords else 0.0


def _normalize_citation_count(count: int, max_count: int = 500) -> float:
    """Normalize citation count to [0, 1] with log scaling."""
    if count is None or count <= 0:
        return 0.0
    import math
    return round(min(math.log1p(count) / math.log1p(max_count), 1.0), 3)


def rank_pass1_papers(candidates: list[dict], workflow_keywords: list[str] = None,
                      known_papers: dict = None, config: dict = None) -> list[dict]:
    """Rank Pass 1 paper candidates using multi-signal scoring.

    Signals (from v2_config.json phase3_search.pass1_ranking_weights):
        - has_pmcid: 0.30 — papers with PMC IDs are freely accessible
        - year_recency: 0.20 — recent papers preferred
        - title_keyword_overlap: 0.30 — relevance to workflow
        - citation_count_norm: 0.20 — impact indicator

    Args:
        candidates: list of paper dicts with keys: title, year, pmcid, pmid, citation_count
        workflow_keywords: keywords for relevance scoring
        known_papers: dict from build_known_paper_set() for dedup
        config: v2_config (loaded if None)

    Returns:
        Sorted list (descending by score) with 'ranking_score' and 'ranking_signals' added.
    """
    if config is None:
        config = load_v2_config()

    weights = config.get("phases", {}).get("phase_2_search", {}).get(
        "pass1_ranking_weights", {
            "has_pmcid": 0.30, "year_recency": 0.20,
            "title_keyword_overlap": 0.30, "citation_count_norm": 0.20
        }
    )

    current_year = datetime.now().year
    if workflow_keywords is None:
        workflow_keywords = []

    scored = []
    for paper in candidates:
        # Dedup check
        if known_papers:
            pmid = str(paper.get("pmid", "")).strip()
            doi = str(paper.get("doi", "")).strip().lower()
            pmcid = str(paper.get("pmcid", "")).strip()
            if (pmid and pmid in known_papers.get("pmids", set())) or \
               (doi and doi in known_papers.get("dois", set())) or \
               (pmcid and pmcid in known_papers.get("pmcids", set())):
                continue

        # Compute signals
        has_pmcid = 1.0 if paper.get("pmcid") else 0.0
        year_score = _compute_year_recency_score(paper.get("year"), current_year)
        keyword_score = _compute_keyword_overlap(paper.get("title", ""), workflow_keywords)
        citation_score = _normalize_citation_count(paper.get("citation_count", 0))

        signals = {
            "has_pmcid": has_pmcid,
            "year_recency": year_score,
            "title_keyword_overlap": keyword_score,
            "citation_count_norm": citation_score,
        }

        # Weighted sum
        total = sum(weights.get(k, 0) * v for k, v in signals.items())

        paper_copy = dict(paper)
        paper_copy["ranking_score"] = round(total, 4)
        paper_copy["ranking_signals"] = signals
        scored.append(paper_copy)

    # Sort descending
    scored.sort(key=lambda p: p["ranking_score"], reverse=True)
    return scored


def save_search_strategy(wf_dir: str | Path, queries: list[dict],
                         ranked_papers: list[dict] = None) -> Path:
    """Save generated search strategy and rankings to workflow directory.

    Args:
        wf_dir: workflow output directory
        queries: list from generate_queries()
        ranked_papers: optional list from rank_pass1_papers()

    Returns:
        Path to saved search_strategy.json
    """
    wf_dir = Path(wf_dir)
    papers_dir = wf_dir / "01_papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    strategy = {
        "generated": datetime.now().isoformat(),
        "generator": f"workflow-composer v{__version__}",
        "method": "config_template_deterministic",
        "queries": queries,
        "total_queries": len(queries),
    }

    if ranked_papers is not None:
        strategy["pass1_ranking"] = {
            "total_candidates": len(ranked_papers),
            "top_papers": ranked_papers[:20],  # Save top 20
        }

    strategy_path = papers_dir / "search_strategy.json"
    with open(strategy_path, "w", encoding="utf-8") as f:
        json.dump(strategy, f, indent=2, ensure_ascii=False)

    return strategy_path


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("=== generate_search_queries.py self-test ===\n")

        # Test 1: Generate queries for known workflow
        queries = generate_queries("WB030", "DNA Assembly")
        assert len(queries) >= 2, f"Expected >=2 queries, got {len(queries)}"
        assert any(q["source"] == "template_primary" for q in queries), "Missing primary query"
        assert any(q["source"] == "fallback" for q in queries), "Missing fallback query"
        print(f"Test 1 PASS: Generated {len(queries)} queries for WB030")
        for q in queries:
            print(f"  [{q['source']}] {q['query'][:80]}...")

        # Test 2: Generate queries for unknown workflow (fallback only)
        queries_unknown = generate_queries("WX999", "Unknown Workflow")
        assert len(queries_unknown) >= 1, "Expected at least fallback query"
        assert queries_unknown[-1]["source"] == "fallback"
        print(f"\nTest 2 PASS: Generated {len(queries_unknown)} queries for unknown WX999")

        # Test 3: Rank papers
        test_papers = [
            {"title": "Gibson Assembly protocol for DNA cloning", "year": 2024, "pmcid": "PMC123", "citation_count": 50},
            {"title": "Clinical trial results for cancer treatment", "year": 2020, "pmcid": None, "citation_count": 200},
            {"title": "Golden Gate assembly automated workflow", "year": 2023, "pmcid": "PMC456", "citation_count": 30},
            {"title": "Old paper on molecular methods", "year": 2010, "pmcid": None, "citation_count": 5},
        ]
        ranked = rank_pass1_papers(test_papers, workflow_keywords=["DNA assembly", "Gibson assembly", "Golden Gate"])
        assert len(ranked) == 4
        # The Gibson Assembly paper should rank high (has PMCID + keyword match + recent)
        assert ranked[0]["title"].startswith("Gibson") or ranked[0]["title"].startswith("Golden"), \
            f"Expected relevant paper first, got: {ranked[0]['title']}"
        print(f"\nTest 3 PASS: Ranked {len(ranked)} papers")
        for i, p in enumerate(ranked):
            print(f"  #{i+1} score={p['ranking_score']:.3f} — {p['title'][:60]}")

        # Test 4: Dedup
        known = {"pmids": {"12345"}, "dois": set(), "pmcids": {"PMC123"}}
        test_papers_dedup = [
            {"title": "Paper A", "year": 2024, "pmcid": "PMC123", "citation_count": 50},
            {"title": "Paper B", "year": 2024, "pmcid": "PMC789", "citation_count": 30},
        ]
        ranked_dedup = rank_pass1_papers(test_papers_dedup, known_papers=known)
        assert len(ranked_dedup) == 1, f"Expected 1 after dedup, got {len(ranked_dedup)}"
        assert ranked_dedup[0]["title"] == "Paper B"
        print(f"\nTest 4 PASS: Dedup removed known paper (PMC123)")

        # Test 5: Year recency scoring
        assert _compute_year_recency_score(2026, 2026) == 1.0
        assert _compute_year_recency_score(2020, 2026) > 0.0
        assert _compute_year_recency_score(2000, 2026) == 0.0
        print(f"\nTest 5 PASS: Year recency scoring correct")

        print("\n=== All tests passed! ===")
    else:
        print("Usage: python generate_search_queries.py --test")
        print("  Or import and use generate_queries(), rank_pass1_papers()")
