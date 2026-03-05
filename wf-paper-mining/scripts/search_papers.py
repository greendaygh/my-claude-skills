"""PubMed primary + OpenAlex fallback paper search.

Searches PubMed (MeSH + workflow keywords), falls back to OpenAlex
when PubMed results are insufficient.  Outputs per-run paper_list_{run_id}.json.

CLI:
    python -m scripts.search_papers \
        --workflow-id WB030 \
        --run-id 1 \
        --config assets/extraction_config.json \
        --assets assets/ \
        --output ~/dev/wf-mining/WB030 \
        --exclude-file ~/dev/wf-mining/run_registry.json \
        --select-n 10 \
        --seed 42
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from datetime import date
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

from .models.paper_list import MiningPaper, MiningPaperList

# ========== Constants ==========

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
OPENALEX_WORKS = "https://api.openalex.org/works"

RATE_LIMIT_DELAY = 0.35
OPENALEX_POLITE_EMAIL = "wf-paper-mining@biofoundry.org"

AUTOMATION_TERMS = (
    "automated OR high-throughput OR biofoundry "
    "OR 'laboratory automation' "
    "OR (robotic AND (liquid handling OR plate reader OR pipetting OR microplate OR assay))"
)


# ========== PubMed functions ==========

def _build_pubmed_query(
    wf_name: str,
    domain_keywords: list[str],
    mesh_terms: list[str],
) -> str:
    """Build a PubMed query using MeSH terms + workflow name + domain keywords."""
    parts: list[str] = []

    if mesh_terms:
        mesh_part = " OR ".join(f'"{t}"[MeSH]' for t in mesh_terms[:5])
        parts.append(f"({mesh_part})")

    if wf_name:
        parts.append(f'"{wf_name}"')

    if domain_keywords:
        kw_part = " OR ".join(f'"{k}"' for k in domain_keywords[:6])
        parts.append(f"({kw_part})")

    base = " OR ".join(parts) if parts else "biofoundry"
    return f"({base}) AND ({AUTOMATION_TERMS})"


def _search_pubmed(query: str, max_results: int = 300, max_retries: int = 3) -> tuple[list[str], int]:
    """Search PubMed via esearch with retry. Returns (pmid_list, total_count)."""
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
    print(f"[search] PubMed query: {query[:80]}...", file=sys.stderr)
    for attempt in range(1, max_retries + 1):
        try:
            time.sleep(RATE_LIMIT_DELAY * attempt)
            resp = requests.get(PUBMED_ESEARCH, params=params, timeout=60)
            resp.raise_for_status()
            root = ET.fromstring(resp.text)
            total = int(root.findtext("Count", "0"))
            pmids = [el.text for el in root.findall(".//IdList/Id") if el.text]
            print(f"[search] PubMed: {total} total, {len(pmids)} retrieved", file=sys.stderr)
            return pmids, total
        except (requests.exceptions.RequestException, ET.ParseError) as exc:
            print(f"[search] esearch attempt {attempt}/{max_retries} failed: {exc}", file=sys.stderr)
            if attempt == max_retries:
                raise
            time.sleep(3 * attempt)
    return [], 0


def _fetch_pubmed_metadata(pmids: list[str], batch_size: int = 50, max_retries: int = 3) -> list[dict]:
    """Fetch metadata for PMIDs from PubMed efetch in batches."""
    if not pmids:
        return []
    print(f"[search] Fetching PubMed metadata for {len(pmids)} papers (batch_size={batch_size})...", file=sys.stderr)

    all_articles = []
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        print(f"[search]   batch {i // batch_size + 1}: PMIDs {i+1}-{i+len(batch)}", file=sys.stderr)
        for attempt in range(1, max_retries + 1):
            try:
                time.sleep(RATE_LIMIT_DELAY)
                resp = requests.get(
                    PUBMED_EFETCH,
                    params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"},
                    timeout=60,
                )
                resp.raise_for_status()
                batch_root = ET.fromstring(resp.text)
                all_articles.extend(batch_root.findall(".//PubmedArticle"))
                break
            except (requests.exceptions.RequestException, ET.ParseError) as exc:
                print(f"[search]   attempt {attempt}/{max_retries} failed: {exc}", file=sys.stderr)
                if attempt == max_retries:
                    print(f"[search]   skipping batch after {max_retries} failures", file=sys.stderr)
                time.sleep(2 * attempt)

    results: list[dict] = []
    for article in all_articles:
        citation = article.find("MedlineCitation")
        if citation is None:
            continue
        pmid = citation.findtext("PMID", "")
        art = citation.find("Article")
        if art is None:
            continue

        title = art.findtext("ArticleTitle", "")
        journal = art.findtext(".//Journal/Title", "")

        abstract_parts = []
        for ab in art.findall(".//Abstract/AbstractText"):
            label = ab.get("Label", "")
            text = ab.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        authors_list = []
        for author in art.findall(".//AuthorList/Author"):
            last = author.findtext("LastName", "")
            fore = author.findtext("ForeName", "")
            if last:
                authors_list.append(f"{last} {fore}".strip())
        authors = authors_list

        doi = ""
        pmcid = ""
        for aid in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
            id_type = aid.get("IdType", "")
            if id_type == "doi":
                doi = aid.text or ""
            elif id_type == "pmc":
                pmcid = aid.text or ""

        year_el = article.find(
            ".//PubmedData/History/PubMedPubDate[@PubStatus='pubmed']/Year"
        )
        year = int(year_el.text) if year_el is not None and year_el.text else 2024

        has_full_text = bool(pmcid)

        results.append({
            "pmid": pmid,
            "pmcid": pmcid,
            "doi": doi,
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "abstract": abstract,
            "has_full_text": has_full_text,
            "source": "pubmed",
        })
    print(f"[search] Parsed {len(results)} PubMed metadata entries", file=sys.stderr)
    return results


def _pubmed_meta_to_mining_paper(meta: dict, paper_id: str, run_id: int = 0) -> MiningPaper:
    return MiningPaper(
        paper_id=paper_id,
        pmid=meta.get("pmid", ""),
        pmcid=meta.get("pmcid") or None,
        doi=meta.get("doi", ""),
        title=meta.get("title", ""),
        authors=meta.get("authors", []),
        year=meta.get("year", 2024),
        journal=meta.get("journal", ""),
        abstract=meta.get("abstract", ""),
        has_full_text=meta.get("has_full_text", False),
        extraction_status="pending",
        added_in_run=run_id,
        source="pubmed",
    )


# ========== OpenAlex functions ==========

def _reconstruct_abstract(inverted_index: dict | None) -> str:
    """Reconstruct abstract from OpenAlex abstract_inverted_index."""
    if not inverted_index:
        return ""
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort()
    return " ".join(w for _, w in word_positions)


def _build_openalex_query(
    wf_name: str,
    domain_keywords: list[str],
) -> str:
    """Build a 3-tier OpenAlex query."""
    tier1 = f'"{wf_name}" AND ({AUTOMATION_TERMS})' if wf_name else ""
    if domain_keywords:
        domain_part = " OR ".join(f'"{k}"' for k in domain_keywords[:8])
        tier2 = f"({domain_part}) AND ({AUTOMATION_TERMS})"
    else:
        tier2 = ""

    parts = [p for p in [tier1, tier2] if p]
    return " OR ".join(parts) if parts else f"biofoundry AND ({AUTOMATION_TERMS})"


def _fetch_openalex(
    query: str,
    max_results: int = 100,
    exclude_dois: set[str] | None = None,
) -> tuple[list[dict], int]:
    """Fetch papers from OpenAlex. Returns (results, total_count)."""
    exclude_dois = exclude_dois or set()
    params = {
        "search": query,
        "per_page": min(max_results, 100),
        "sort": "relevance_score:desc",
        "mailto": OPENALEX_POLITE_EMAIL,
    }
    for attempt in range(2):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            resp = requests.get(OPENALEX_WORKS, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            total = data.get("meta", {}).get("count", 0)
            results: list[dict] = []
            for work in data.get("results", []):
                doi_raw = (work.get("doi") or "").replace("https://doi.org/", "")
                if doi_raw.lower() in exclude_dois:
                    continue

                pmcid = ""
                pmid = ""
                for loc in work.get("locations", []):
                    src = loc.get("source") or {}
                    if "PMC" in (src.get("display_name") or ""):
                        landing = loc.get("landing_page_url") or ""
                        if "PMC" in landing:
                            pmcid = landing.split("/")[-1]

                ids = work.get("ids") or {}
                if not pmid and ids.get("pmid"):
                    pmid = ids["pmid"].replace("https://pubmed.ncbi.nlm.nih.gov/", "")

                has_full_text = bool(pmcid) or bool(
                    (work.get("open_access") or {}).get("is_oa")
                )

                abstract = _reconstruct_abstract(
                    work.get("abstract_inverted_index")
                )

                results.append({
                    "pmid": pmid,
                    "pmcid": pmcid,
                    "doi": doi_raw,
                    "title": work.get("title", ""),
                    "authors": [
                        a.get("author", {}).get("display_name", "")
                        for a in (work.get("authorships") or [])[:10]
                    ],
                    "year": work.get("publication_year", 2024),
                    "journal": (
                        work.get("primary_location", {}) or {}
                    ).get("source", {}).get("display_name", "")
                    if work.get("primary_location") else "",
                    "abstract": abstract,
                    "has_full_text": has_full_text,
                    "source": "openalex",
                })
            return results, total
        except Exception as e:
            if attempt == 0:
                print(f"[search] OpenAlex attempt 1 failed: {e}, retrying...", file=sys.stderr)
                time.sleep(RATE_LIMIT_DELAY)
                continue
            print(f"[search] OpenAlex failed: {e}", file=sys.stderr)
            return [], 0
    return [], 0


def _openalex_meta_to_mining_paper(meta: dict, paper_id: str, run_id: int = 0) -> MiningPaper:
    return MiningPaper(
        paper_id=paper_id,
        pmid=meta.get("pmid", ""),
        pmcid=meta.get("pmcid") or None,
        doi=meta.get("doi", ""),
        title=meta.get("title", ""),
        authors=meta.get("authors", []),
        year=meta.get("year", 2024),
        journal=meta.get("journal", ""),
        abstract=meta.get("abstract", ""),
        has_full_text=meta.get("has_full_text", False),
        extraction_status="pending",
        added_in_run=run_id,
        source="openalex",
    )


# ========== Dedup helpers ==========

def _norm_doi(doi: str | None) -> str:
    if not doi:
        return ""
    return doi.strip().lower().replace("https://doi.org/", "")


def _load_known_pmids(papers_dir: Path) -> set[str]:
    """Load all known PMIDs from existing paper_list_*.json files."""
    known: set[str] = set()
    for f in papers_dir.glob("paper_list_*.json"):
        try:
            data = json.loads(f.read_text())
            for p in data.get("papers", []):
                pmid = p.get("pmid", "")
                if pmid:
                    known.add(pmid)
        except Exception:
            continue
    return known


def _load_known_dois_from_papers(papers_dir: Path) -> set[str]:
    """Load all known DOIs from existing paper_list_*.json files."""
    known: set[str] = set()
    for f in papers_dir.glob("paper_list_*.json"):
        try:
            data = json.loads(f.read_text())
            for p in data.get("papers", []):
                doi = p.get("doi", "")
                if doi:
                    known.add(_norm_doi(doi))
        except Exception:
            continue
    return known


def _find_domain_info(
    extraction_config: dict, wf_id: str
) -> tuple[str, list[str], list[str]]:
    """Find (domain_name, search_keywords, mesh_terms) for a workflow."""
    for domain_name, group in extraction_config.get("domain_groups", {}).items():
        if wf_id in group.get("workflows", []):
            return (
                domain_name,
                group.get("search_keywords", []),
                group.get("mesh_terms", []),
            )
    return ("unknown", [], [])


# ========== Main ==========

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search PubMed + OpenAlex for workflow-related papers"
    )
    parser.add_argument("--workflow-id", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--config", type=Path, required=True,
                        help="Path to extraction_config.json")
    parser.add_argument("--assets", type=Path, required=True,
                        help="Path to assets directory (has workflow_catalog.json)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Workflow output directory (e.g. ~/dev/wf-mining/WB030)")
    parser.add_argument("--exclude-file", type=Path, default=None,
                        help="run_registry.json for DOI exclusion")
    parser.add_argument("--select-n", type=int, default=10)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    # --- Load configs ---
    extraction_config = json.loads(args.config.read_text())
    wf_catalog_path = args.assets / "workflow_catalog.json"
    wf_catalog = json.loads(wf_catalog_path.read_text()) if wf_catalog_path.exists() else {}

    wf_info = wf_catalog.get("workflows", {}).get(args.workflow_id, {})
    wf_name = wf_info.get("name", args.workflow_id)

    domain_name, domain_keywords, mesh_terms = _find_domain_info(
        extraction_config, args.workflow_id,
    )

    # --- Load known DOIs/PMIDs for dedup ---
    papers_dir = args.output / "01_papers"
    papers_dir.mkdir(parents=True, exist_ok=True)

    known_dois: set[str] = set()
    known_pmids: set[str] = set()

    if args.exclude_file and args.exclude_file.exists():
        try:
            reg = json.loads(args.exclude_file.read_text())
            # Exclude DOIs from ALL workflows to avoid cross-workflow duplication
            for wf_id_key, wf_entry in reg.get("workflows", {}).items():
                for d in wf_entry.get("known_dois", []):
                    known_dois.add(_norm_doi(d))
        except Exception:
            pass

    known_dois |= _load_known_dois_from_papers(papers_dir)
    known_pmids |= _load_known_pmids(papers_dir)

    print(
        f"[search] Known exclusions: {len(known_dois)} DOIs, {len(known_pmids)} PMIDs",
        file=sys.stderr,
    )

    # --- PubMed primary search ---
    pubmed_query = _build_pubmed_query(wf_name, domain_keywords, mesh_terms)
    pmids, pubmed_total = _search_pubmed(pubmed_query)

    new_pmids = [p for p in pmids if p not in known_pmids]
    if args.seed:
        random.seed(args.seed)

    # Fetch metadata for a larger batch to identify papers with PMCIDs,
    # then prioritize those with full text available.
    SCAN_BATCH = min(200, len(new_pmids))  # PubMed efetch limit per request
    scan_pmids = (
        random.sample(new_pmids, SCAN_BATCH)
        if len(new_pmids) > SCAN_BATCH
        else new_pmids
    )

    all_meta: list[dict] = []
    if scan_pmids:
        all_meta = _fetch_pubmed_metadata(scan_pmids)
        all_meta = [
            p for p in all_meta
            if _norm_doi(p.get("doi", "")) not in known_dois or not p.get("doi")
        ]

    # Split into papers with and without PMCIDs
    with_pmcid = [p for p in all_meta if p.get("pmcid")]
    without_pmcid = [p for p in all_meta if not p.get("pmcid")]

    print(
        f"[search] Scanned {len(all_meta)} papers: {len(with_pmcid)} with PMCID, {len(without_pmcid)} without",
        file=sys.stderr,
    )

    # Select: prioritize papers with PMCIDs, fill remainder without
    if len(with_pmcid) >= args.select_n:
        pubmed_papers = random.sample(with_pmcid, args.select_n)
    else:
        need_more_no_pmc = args.select_n - len(with_pmcid)
        fill = (
            random.sample(without_pmcid, min(need_more_no_pmc, len(without_pmcid)))
            if len(without_pmcid) > need_more_no_pmc
            else without_pmcid
        )
        pubmed_papers = with_pmcid + fill

    print(
        f"[search] PubMed: {len(pubmed_papers)} new papers after dedup",
        file=sys.stderr,
    )

    # --- OpenAlex fallback if PubMed insufficient ---
    openalex_papers: list[dict] = []
    openalex_total = 0
    need_more = args.select_n - len(pubmed_papers)

    if need_more > 0:
        print(
            f"[search] PubMed yielded {len(pubmed_papers)}, need {need_more} more from OpenAlex",
            file=sys.stderr,
        )
        oa_query = _build_openalex_query(wf_name, domain_keywords)

        pubmed_dois = {_norm_doi(p.get("doi", "")) for p in pubmed_papers if p.get("doi")}
        all_exclude_dois = known_dois | pubmed_dois

        oa_results, openalex_total = _fetch_openalex(
            oa_query,
            max_results=100,
            exclude_dois=all_exclude_dois,
        )

        oa_new = [
            r for r in oa_results
            if r.get("pmid", "") not in known_pmids
        ]
        openalex_papers = oa_new[:need_more]
        print(
            f"[search] OpenAlex: {len(openalex_papers)} supplementary papers",
            file=sys.stderr,
        )

    # --- Assign paper IDs and build MiningPaper list ---
    all_meta = pubmed_papers + openalex_papers
    if not all_meta:
        print("[search] No new papers found", file=sys.stderr)
        empty_list = MiningPaperList(
            search_date=str(date.today()),
            workflow_id=args.workflow_id,
            run_id=args.run_id,
            query=pubmed_query,
            total_search_hits=pubmed_total + openalex_total,
            pubmed_hits=pubmed_total,
            openalex_hits=openalex_total,
            selected_count=0,
            papers=[],
        )
        paper_list_path = papers_dir / f"paper_list_{args.run_id}.json"
        paper_list_path.write_text(
            empty_list.model_dump_json(indent=2),
        )
        print(json.dumps({"papers_added": 0, "path": str(paper_list_path)}))
        return

    start_id = len(known_dois) + len(known_pmids) + 1
    papers: list[MiningPaper] = []
    for i, meta in enumerate(all_meta):
        pid = f"P{start_id + i:04d}"
        if meta.get("source") == "pubmed":
            papers.append(_pubmed_meta_to_mining_paper(meta, pid, args.run_id))
        else:
            papers.append(_openalex_meta_to_mining_paper(meta, pid, args.run_id))

    # --- Save per-run paper_list_{run_id}.json ---
    paper_list = MiningPaperList(
        search_date=str(date.today()),
        workflow_id=args.workflow_id,
        run_id=args.run_id,
        query=pubmed_query,
        total_search_hits=pubmed_total + openalex_total,
        pubmed_hits=pubmed_total,
        openalex_hits=openalex_total,
        selected_count=len(papers),
        papers=papers,
    )

    # --- Guard: DOI overlap with existing paper_lists (exclude current run) ---
    existing_dois = set()
    for f in papers_dir.glob("paper_list_*.json"):
        if f.name == f"paper_list_{args.run_id}.json":
            continue
        try:
            data = json.loads(f.read_text())
            for p in data.get("papers", []):
                doi = p.get("doi", "")
                if doi:
                    existing_dois.add(_norm_doi(doi))
        except Exception:
            continue
    overlap = [p for p in papers if p.doi and _norm_doi(p.doi) in existing_dois]
    if overlap:
        print(
            f"[search] ERROR: {len(overlap)} papers overlap with existing paper_lists",
            file=sys.stderr,
        )
        sys.exit(1)

    # --- Guard: paper_id collision with existing paper_lists ---
    existing_ids: set[str] = set()
    for f in papers_dir.glob("paper_list_*.json"):
        if f.name == f"paper_list_{args.run_id}.json":
            continue
        try:
            data = json.loads(f.read_text())
            for p in data.get("papers", []):
                pid = p.get("paper_id", "")
                if pid:
                    existing_ids.add(pid)
        except Exception:
            continue
    for p in papers:
        if p.paper_id in existing_ids:
            print(
                f"[search] ERROR: paper_id {p.paper_id} already exists",
                file=sys.stderr,
            )
            sys.exit(1)

    paper_list_path = papers_dir / f"paper_list_{args.run_id}.json"
    paper_list_path.write_text(paper_list.model_dump_json(indent=2))

    print(
        f"[search] Saved {len(papers)} papers to {paper_list_path.name}",
        file=sys.stderr,
    )

    # --- Sync to run_registry ---
    if args.exclude_file:
        try:
            from .run_tracker import RunTracker
            tracker = RunTracker(args.exclude_file.expanduser().resolve())
            tracker.add_papers(
                args.workflow_id,
                args.run_id,
                [{"paper_id": p.paper_id, "doi": p.doi or ""} for p in papers],
            )
            print("[search] Synced DOIs to run_registry", file=sys.stderr)
        except Exception as e:
            print(f"[search] Warning: registry sync failed: {e}", file=sys.stderr)

    print(json.dumps({
        "papers_added": len(papers),
        "pubmed_count": len(pubmed_papers),
        "openalex_count": len(openalex_papers),
        "path": str(paper_list_path),
    }))


if __name__ == "__main__":
    main()
