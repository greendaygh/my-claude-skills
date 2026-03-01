"""PubMed search + random selection + incremental paper_list.json update.

Searches PubMed for prophage-related papers, excludes already-known PMIDs,
randomly selects ~20 papers with PMCIDs, and appends to paper_list.json.
"""

from __future__ import annotations

import json
import random
import sys
import time
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

RATE_LIMIT_DELAY = 0.35

DEFAULT_QUERY = (
    '"prophage identification" OR "prophage induction" OR "lysogeny decision" '
    'OR "prophage genomics" OR "temperate bacteriophage integration" '
    'OR "prophage-host interaction" OR "prophage gene expression"'
)


def search_pubmed(query: str, max_results: int = 500) -> tuple[list[str], int]:
    """Search PubMed and return (pmid_list, total_count)."""
    params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "xml",
        "sort": "relevance",
        "datetype": "pdat",
        "mindate": "2015",
        "maxdate": str(date.today().year),
    }
    print(f"[search_papers] Searching PubMed: {query[:60]}...", file=sys.stderr)
    time.sleep(RATE_LIMIT_DELAY)
    resp = requests.get(PUBMED_ESEARCH, params=params, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    total = int(root.findtext("Count", "0"))
    pmids = [id_el.text for id_el in root.findall(".//IdList/Id") if id_el.text]
    print(f"[search_papers] Found {total} total results, retrieved {len(pmids)} PMIDs", file=sys.stderr)
    return pmids, total


def fetch_metadata(pmids: list[str]) -> list[dict]:
    """Fetch metadata for given PMIDs from PubMed efetch."""
    if not pmids:
        return []
    print(f"[search_papers] Fetching metadata for {len(pmids)} papers...", file=sys.stderr)
    time.sleep(RATE_LIMIT_DELAY)
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    resp = requests.get(PUBMED_EFETCH, params=params, timeout=30)
    resp.raise_for_status()

    root = ET.fromstring(resp.text)
    papers = []
    for article in root.findall(".//PubmedArticle"):
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        pmid = citation.findtext("PMID", "")
        art = citation.find("Article")
        if art is None:
            continue

        title = art.findtext("ArticleTitle", "")
        journal = art.findtext(".//Journal/Title", "")
        abstract = art.findtext(".//Abstract/AbstractText", "")

        authors_list = []
        for author in art.findall(".//AuthorList/Author"):
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            if last:
                authors_list.append(f"{last} {fore}".strip())
        authors = ", ".join(authors_list)

        doi = ""
        pmcid = ""
        # ArticleIdList is under PubmedData, not Article
        for aid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = aid.get("IdType", "")
            if id_type == "doi":
                doi = aid.text or ""
            elif id_type == "pmc":
                pmcid = aid.text or ""

        year_el = article.find(".//PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year")
        year = int(year_el.text) if year_el is not None and year_el.text else 2024

        papers.append({
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "abstract": abstract,
        })
    print(f"[search_papers] Parsed metadata for {len(papers)} papers", file=sys.stderr)
    return papers


def random_select(
    pmids: list[str],
    exclude_pmids: set[str],
    n: int = 20,
) -> list[str]:
    """Randomly select up to n PMIDs, excluding known ones."""
    available = [p for p in pmids if p not in exclude_pmids]
    if len(available) <= n:
        return available
    return random.sample(available, n)


def append_paper_list(
    new_papers: list[dict],
    output_dir: Path,
    query: str = "",
    total_hits: int = 0,
) -> Path:
    """Append new papers to paper_list.json (creates if not exists)."""
    output_dir = Path(output_dir)
    path = output_dir / "01_papers" / "paper_list.json"

    if path.exists():
        existing = json.loads(path.read_text())
    else:
        existing = {
            "search_date": str(date.today()),
            "query": query,
            "total_pubmed_hits": total_hits,
            "selected_count": 0,
            "papers": [],
        }

    for p in new_papers:
        entry = {
            "paper_id": p.get("paper_id", ""),
            "pmid": p.get("pmid", ""),
            "pmcid": p.get("pmcid"),
            "doi": p.get("doi"),
            "title": p.get("title", ""),
            "authors": p.get("authors", ""),
            "year": p.get("year", 2024),
            "journal": p.get("journal", ""),
            "abstract": p.get("abstract"),
            "has_full_text": False,
            "extraction_status": "pending",
        }
        existing["papers"].append(entry)

    existing["selected_count"] = len(existing["papers"])
    existing["total_pubmed_hits"] = max(existing.get("total_pubmed_hits", 0), total_hits)
    existing["search_date"] = str(date.today())
    if query:
        existing["query"] = query

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))
    print(f"[search_papers] paper_list.json updated: {len(existing['papers'])} total papers", file=sys.stderr)
    return path


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Search PubMed for prophage papers")
    parser.add_argument("--output", type=Path, required=True, help="Output directory (~/dev/phage)")
    parser.add_argument("--exclude-file", type=Path, help="run_registry.json to exclude known PMIDs")
    parser.add_argument("--max-results", type=int, default=500)
    parser.add_argument("--select-n", type=int, default=20)
    parser.add_argument("--query", type=str, default=DEFAULT_QUERY)
    parser.add_argument("--run-id", type=str, help="Existing run_id from orchestrator (skips start_run)")
    args = parser.parse_args()

    exclude_pmids: set[str] = set()
    if args.exclude_file and args.exclude_file.exists():
        reg = json.loads(args.exclude_file.read_text())
        exclude_pmids = set(reg.get("known_pmids", []))

    pmids, total = search_pubmed(args.query, max_results=args.max_results)
    selected = random_select(pmids, exclude_pmids, n=args.select_n)

    if not selected:
        print("[search_papers] No new papers found", file=sys.stderr)
        return

    metadata = fetch_metadata(selected)
    metadata_with_pmcid = [p for p in metadata if p.get("pmcid")]
    print(f"[search_papers] {len(metadata_with_pmcid)}/{len(metadata)} papers have PMCIDs", file=sys.stderr)

    from scripts.run_tracker import RunTracker
    tracker = RunTracker(args.output)
    run_id = args.run_id if args.run_id else tracker.start_run()
    start_id = int(tracker.get_next_paper_id()[1:])
    for i, p in enumerate(metadata_with_pmcid):
        p["paper_id"] = f"P{start_id + i:03d}"

    # Register papers in run_registry so Phase 3 can find pending extractions
    tracker.add_papers(run_id, metadata_with_pmcid)

    append_paper_list(metadata_with_pmcid, args.output, query=args.query, total_hits=total)
    print(f"[search_papers] Added {len(metadata_with_pmcid)} papers", file=sys.stderr)


if __name__ == "__main__":
    main()
