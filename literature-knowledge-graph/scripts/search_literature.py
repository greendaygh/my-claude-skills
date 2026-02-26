#!/usr/bin/env python3
from __future__ import annotations
"""
Integrated literature search across PubMed, bioRxiv, and OpenAlex with deduplication.

Searches multiple bibliographic databases, normalizes results into a common schema,
deduplicates by DOI and fuzzy title matching, and outputs a merged JSON array.
"""

import argparse
import json
import re
import string
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
from urllib.parse import quote_plus

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
BIORXIV_API_URL = "https://api.biorxiv.org/details/biorxiv"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

POLITE_EMAIL = "literature-search-bot@example.com"

TITLE_SIMILARITY_THRESHOLD = 0.9

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_session(max_retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Return a requests.Session with automatic retry on transient errors."""
    session = requests.Session()
    retry_kwargs = dict(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    # urllib3 >=1.26.0 uses allowed_methods; older versions use method_whitelist
    try:
        retry_strategy = Retry(allowed_methods=["GET", "POST"], **retry_kwargs)
    except TypeError:
        retry_strategy = Retry(method_whitelist=["GET", "POST"], **retry_kwargs)
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


SESSION = _build_session()


def _normalize_title(title: str) -> str:
    """Lowercase, strip punctuation and extra whitespace for fuzzy matching."""
    title = title.lower()
    title = title.translate(str.maketrans("", "", string.punctuation))
    title = re.sub(r"\s+", " ", title).strip()
    return title


def _title_similarity(a: str, b: str) -> float:
    """
    Compute similarity between two normalized titles using character-level
    Jaccard on bigrams. Fast and adequate for near-duplicate detection.
    """
    if not a or not b:
        return 0.0

    def _bigrams(s: str) -> set[str]:
        return {s[i : i + 2] for i in range(len(s) - 1)} if len(s) >= 2 else {s}

    ba, bb = _bigrams(a), _bigrams(b)
    if not ba or not bb:
        return 0.0
    intersection = ba & bb
    union = ba | bb
    return len(intersection) / len(union)


def _clean_doi(doi: str | None) -> str | None:
    """Normalize DOI to bare identifier (no URL prefix)."""
    if not doi:
        return None
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix) :]
    return doi.strip() if doi.strip() else None


def _safe_int(value: Any, default: int | None = None) -> int | None:
    """Try to cast value to int, return default on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Reconstruct abstract text from OpenAlex inverted index format."""
    if not inverted_index:
        return ""
    word_positions: list[tuple[int, str]] = []
    for word, positions in inverted_index.items():
        for pos in positions:
            word_positions.append((pos, word))
    word_positions.sort(key=lambda x: x[0])
    return " ".join(w for _, w in word_positions)


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------


def _pubmed_esearch(
    query: str, max_results: int, date_from: str | None, date_to: str | None
) -> list[str]:
    """Run PubMed ESearch and return a list of PMIDs."""
    params: dict[str, Any] = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "relevance",
    }
    if date_from:
        params["mindate"] = date_from.replace("-", "/")
        params["datetype"] = "pdat"
    if date_to:
        params["maxdate"] = date_to.replace("-", "/")
        params["datetype"] = "pdat"

    time.sleep(0.34)  # ~3 req/s rate limit
    resp = SESSION.get(PUBMED_ESEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("esearchresult", {}).get("idlist", [])


def _pubmed_efetch(pmids: list[str]) -> list[dict[str, Any]]:
    """Fetch article metadata from PubMed for a batch of PMIDs."""
    if not pmids:
        return []

    results: list[dict[str, Any]] = []
    batch_size = 200
    for i in range(0, len(pmids), batch_size):
        batch = pmids[i : i + batch_size]
        time.sleep(0.34)
        params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "retmode": "xml",
            "rettype": "abstract",
        }
        resp = SESSION.get(PUBMED_EFETCH_URL, params=params, timeout=60)
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        for article_el in root.findall(".//PubmedArticle"):
            results.append(_parse_pubmed_article(article_el))

    return results


def _parse_pubmed_article(article_el: ET.Element) -> dict[str, Any]:
    """Parse a single PubmedArticle XML element into our common schema."""
    medline = article_el.find(".//MedlineCitation")
    article = medline.find(".//Article") if medline is not None else None

    pmid = ""
    pmid_el = medline.find("PMID") if medline is not None else None
    if pmid_el is not None and pmid_el.text:
        pmid = pmid_el.text.strip()

    # DOI
    doi = None
    for id_el in article_el.findall(".//ArticleId"):
        if id_el.get("IdType") == "doi" and id_el.text:
            doi = _clean_doi(id_el.text)
            break
    # Fallback: look in ELocationID
    if not doi and article is not None:
        for eloc in article.findall("ELocationID"):
            if eloc.get("EIdType") == "doi" and eloc.text:
                doi = _clean_doi(eloc.text)
                break

    # PMCID
    pmcid = None
    for id_el in article_el.findall(".//ArticleId"):
        if id_el.get("IdType") == "pmc" and id_el.text:
            pmcid = id_el.text.strip()
            break

    # Title
    title = ""
    title_el = article.find("ArticleTitle") if article is not None else None
    if title_el is not None:
        title = "".join(title_el.itertext()).strip()

    # Authors
    authors: list[str] = []
    if article is not None:
        for author_el in article.findall(".//Author"):
            last = author_el.findtext("LastName", "").strip()
            fore = author_el.findtext("ForeName", "").strip()
            initials = author_el.findtext("Initials", "").strip()
            if last:
                name = f"{last} {fore}" if fore else f"{last} {initials}" if initials else last
                authors.append(name)

    # Abstract
    abstract_parts: list[str] = []
    if article is not None:
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label", "")
            text = "".join(abs_text.itertext()).strip()
            if label and text:
                abstract_parts.append(f"{label}: {text}")
            elif text:
                abstract_parts.append(text)
    abstract = " ".join(abstract_parts)

    # Year
    year = None
    if article is not None:
        pub_date = article.find(".//PubDate")
        if pub_date is not None:
            year_el = pub_date.find("Year")
            if year_el is not None and year_el.text:
                year = _safe_int(year_el.text)
            else:
                medline_date = pub_date.findtext("MedlineDate", "")
                match = re.search(r"(\d{4})", medline_date)
                if match:
                    year = _safe_int(match.group(1))

    # Journal
    journal = ""
    if article is not None:
        journal_el = article.find(".//Journal/Title")
        if journal_el is not None and journal_el.text:
            journal = journal_el.text.strip()
        else:
            iso_el = article.find(".//Journal/ISOAbbreviation")
            if iso_el is not None and iso_el.text:
                journal = iso_el.text.strip()

    return {
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "openalex_id": None,
        "title": title,
        "authors": authors,
        "abstract": abstract,
        "year": year,
        "journal": journal,
        "source_db": ["pubmed"],
        "citation_count": None,
    }


def search_pubmed(
    query: str, max_results: int, date_from: str | None, date_to: str | None
) -> list[dict[str, Any]]:
    """Full PubMed search: esearch then efetch."""
    print(f"  [PubMed] Searching: {query!r} (max {max_results})")
    try:
        pmids = _pubmed_esearch(query, max_results, date_from, date_to)
        if not pmids:
            print("  [PubMed] No results found.")
            return []
        print(f"  [PubMed] Found {len(pmids)} PMIDs, fetching metadata...")
        papers = _pubmed_efetch(pmids)
        print(f"  [PubMed] Retrieved {len(papers)} papers.")
        return papers
    except requests.RequestException as exc:
        print(f"  [PubMed] Error: {exc}", file=sys.stderr)
        return []


# ---------------------------------------------------------------------------
# bioRxiv
# ---------------------------------------------------------------------------


def search_biorxiv(
    query: str, max_results: int, date_from: str | None, date_to: str | None
) -> list[dict[str, Any]]:
    """
    Search bioRxiv via its content-detail API.

    The bioRxiv API uses date-range based endpoints:
        /details/biorxiv/{from}/{to}/{cursor}
    We paginate and filter by query terms client-side.
    """
    print(f"  [bioRxiv] Searching: {query!r} (max {max_results})")

    d_from = date_from if date_from else "2019-01-01"
    d_to = date_to if date_to else datetime.now().strftime("%Y-%m-%d")

    query_terms = [t.strip().lower() for t in query.split() if t.strip()]
    results: list[dict[str, Any]] = []
    cursor = 0
    page_size = 100
    max_pages = 10  # safety limit

    try:
        for _ in range(max_pages):
            url = f"{BIORXIV_API_URL}/{d_from}/{d_to}/{cursor}"
            time.sleep(0.5)  # rate limit
            resp = SESSION.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            collection = data.get("collection", [])
            if not collection:
                break

            for item in collection:
                title = item.get("title", "")
                abstract = item.get("abstract", "")
                combined = f"{title} {abstract}".lower()

                if all(term in combined for term in query_terms):
                    doi = _clean_doi(item.get("doi"))
                    # Parse authors: bioRxiv gives semicolon-separated string
                    author_str = item.get("authors", "")
                    authors = [
                        a.strip() for a in author_str.split(";") if a.strip()
                    ]

                    # Parse year from date
                    pub_date = item.get("date", "")
                    year = None
                    if pub_date:
                        match = re.search(r"(\d{4})", pub_date)
                        if match:
                            year = _safe_int(match.group(1))

                    results.append(
                        {
                            "doi": doi,
                            "pmid": None,
                            "pmcid": None,
                            "openalex_id": None,
                            "title": title.strip(),
                            "authors": authors,
                            "abstract": abstract.strip(),
                            "year": year,
                            "journal": "bioRxiv",
                            "source_db": ["biorxiv"],
                            "citation_count": None,
                            "_category": item.get("category", ""),
                        }
                    )

                    if len(results) >= max_results:
                        break

            if len(results) >= max_results:
                break

            # bioRxiv paginates in chunks; move cursor forward
            total_raw = data.get("messages", [{}])[0].get("total", 0)
            try:
                total = int(total_raw)
            except (TypeError, ValueError):
                total = 0
            cursor += page_size
            if cursor >= total:
                break

    except requests.RequestException as exc:
        print(f"  [bioRxiv] Error: {exc}", file=sys.stderr)

    print(f"  [bioRxiv] Retrieved {len(results)} papers.")
    return results[: max_results]


# ---------------------------------------------------------------------------
# OpenAlex
# ---------------------------------------------------------------------------


def search_openalex(
    query: str, max_results: int, date_from: str | None, date_to: str | None
) -> list[dict[str, Any]]:
    """Search OpenAlex /works endpoint with search query and optional date filter."""
    print(f"  [OpenAlex] Searching: {query!r} (max {max_results})")

    results: list[dict[str, Any]] = []
    per_page = min(max_results, 200)
    page = 1
    max_pages = (max_results + per_page - 1) // per_page

    try:
        for p in range(max_pages):
            params: dict[str, Any] = {
                "search": query,
                "per_page": per_page,
                "page": page + p,
                "mailto": POLITE_EMAIL,
            }

            # Build filter string
            filters: list[str] = []
            if date_from:
                filters.append(f"from_publication_date:{date_from}")
            if date_to:
                filters.append(f"to_publication_date:{date_to}")
            if filters:
                params["filter"] = ",".join(filters)

            time.sleep(0.1)  # 10 req/s polite rate limit
            resp = SESSION.get(OPENALEX_WORKS_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            works = data.get("results", [])
            if not works:
                break

            for work in works:
                doi = _clean_doi(work.get("doi"))

                # Authors
                authors: list[str] = []
                for authorship in work.get("authorships", []):
                    author_info = authorship.get("author", {})
                    display_name = author_info.get("display_name", "")
                    if display_name:
                        authors.append(display_name)

                # Abstract
                abstract = _reconstruct_abstract(
                    work.get("abstract_inverted_index")
                )

                # OpenAlex ID
                openalex_id = work.get("id", "")
                if openalex_id.startswith("https://openalex.org/"):
                    openalex_id = openalex_id.replace("https://openalex.org/", "")

                # Journal / source
                journal = ""
                primary_location = work.get("primary_location") or {}
                source = primary_location.get("source") or {}
                journal = source.get("display_name", "")

                # IDs: try to extract PMID from work.ids
                ids_dict = work.get("ids", {})
                pmid = None
                pmid_url = ids_dict.get("pmid", "")
                if pmid_url:
                    # Format: https://pubmed.ncbi.nlm.nih.gov/12345678
                    match = re.search(r"(\d+)$", pmid_url)
                    if match:
                        pmid = match.group(1)
                pmcid = ids_dict.get("pmcid")
                if pmcid and pmcid.startswith("https://www.ncbi.nlm.nih.gov/pmc/articles/"):
                    pmcid = pmcid.replace(
                        "https://www.ncbi.nlm.nih.gov/pmc/articles/", ""
                    ).rstrip("/")

                results.append(
                    {
                        "doi": doi,
                        "pmid": pmid,
                        "pmcid": pmcid,
                        "openalex_id": openalex_id,
                        "title": work.get("title", "") or "",
                        "authors": authors,
                        "abstract": abstract,
                        "year": _safe_int(work.get("publication_year")),
                        "journal": journal,
                        "source_db": ["openalex"],
                        "citation_count": _safe_int(
                            work.get("cited_by_count"), default=0
                        ),
                    }
                )

                if len(results) >= max_results:
                    break

            if len(results) >= max_results:
                break

    except requests.RequestException as exc:
        print(f"  [OpenAlex] Error: {exc}", file=sys.stderr)

    print(f"  [OpenAlex] Retrieved {len(results)} papers.")
    return results[: max_results]


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def _merge_paper(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    """Merge incoming paper record into an existing one, preserving all IDs."""
    merged = dict(existing)

    # Merge IDs: keep non-None values
    for key in ("doi", "pmid", "pmcid", "openalex_id"):
        if not merged.get(key) and incoming.get(key):
            merged[key] = incoming[key]

    # Merge source_db lists
    existing_sources = set(merged.get("source_db", []))
    incoming_sources = set(incoming.get("source_db", []))
    merged["source_db"] = sorted(existing_sources | incoming_sources)

    # Prefer longer abstract
    if len(incoming.get("abstract", "")) > len(merged.get("abstract", "")):
        merged["abstract"] = incoming["abstract"]

    # Prefer non-empty title
    if not merged.get("title") and incoming.get("title"):
        merged["title"] = incoming["title"]

    # Prefer more authors
    if len(incoming.get("authors", [])) > len(merged.get("authors", [])):
        merged["authors"] = incoming["authors"]

    # Merge citation_count: take the higher value
    inc_cc = incoming.get("citation_count")
    cur_cc = merged.get("citation_count")
    if inc_cc is not None:
        if cur_cc is None or inc_cc > cur_cc:
            merged["citation_count"] = inc_cc

    # Prefer non-empty journal, prefer non-preprint name
    if incoming.get("journal") and (
        not merged.get("journal") or merged["journal"] in ("bioRxiv", "")
    ):
        merged["journal"] = incoming["journal"]

    # Year: prefer non-None
    if not merged.get("year") and incoming.get("year"):
        merged["year"] = incoming["year"]

    return merged


def deduplicate(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Deduplicate papers by DOI (primary) and normalized title similarity (secondary).

    Returns a list of merged, unique paper records.
    """
    doi_index: dict[str, int] = {}  # doi -> index in unique list
    title_index: list[tuple[str, int]] = []  # (normalized_title, index)
    unique: list[dict[str, Any]] = []

    for paper in papers:
        doi = paper.get("doi")
        norm_title = _normalize_title(paper.get("title", ""))

        # 1) DOI-based dedup
        if doi and doi in doi_index:
            idx = doi_index[doi]
            unique[idx] = _merge_paper(unique[idx], paper)
            # Also register title for this index if not done
            if norm_title:
                # Check if this title-index pair exists already
                existing_titles = {t for t, i in title_index if i == idx}
                if norm_title not in existing_titles:
                    title_index.append((norm_title, idx))
            continue

        # 2) Title-based dedup
        matched_idx = None
        if norm_title:
            for existing_title, idx in title_index:
                if _title_similarity(norm_title, existing_title) > TITLE_SIMILARITY_THRESHOLD:
                    matched_idx = idx
                    break

        if matched_idx is not None:
            unique[matched_idx] = _merge_paper(unique[matched_idx], paper)
            # Register DOI under this index too
            if doi:
                doi_index[doi] = matched_idx
            if norm_title:
                title_index.append((norm_title, matched_idx))
            continue

        # 3) New unique paper
        new_idx = len(unique)
        unique.append(dict(paper))
        if doi:
            doi_index[doi] = new_idx
        if norm_title:
            title_index.append((norm_title, new_idx))

    return unique


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Integrated literature search across PubMed, bioRxiv, and OpenAlex.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s --queries "CRISPR base editing" --sources pubmed,openalex --max-results 25
  %(prog)s --queries "gene therapy,AAV delivery" --date-from 2022-01-01 --output results.json
  %(prog)s --queries "single cell RNA-seq" --exclude-dois exclude.json
""",
    )
    parser.add_argument(
        "--queries",
        required=True,
        help="Comma-separated search queries.",
    )
    parser.add_argument(
        "--sources",
        default="pubmed,biorxiv,openalex",
        help="Comma-separated sources: pubmed, biorxiv, openalex (default: all).",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Max results per source per query (default: 50).",
    )
    parser.add_argument(
        "--date-from",
        default=None,
        help="Start date filter YYYY-MM-DD.",
    )
    parser.add_argument(
        "--date-to",
        default=None,
        help="End date filter YYYY-MM-DD.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output JSON file path. Prints to stdout if not specified.",
    )
    parser.add_argument(
        "--exclude-dois",
        default=None,
        help="Path to JSON file containing a list of DOIs to exclude (for cycle 2 dedup).",
    )
    return parser.parse_args()


def load_exclude_dois(path: str | None) -> set[str]:
    """Load a set of DOIs to exclude from a JSON file (list of strings)."""
    if not path:
        return set()
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {_clean_doi(d) for d in data if d} - {None}
        elif isinstance(data, dict) and "dois" in data:
            return {_clean_doi(d) for d in data["dois"] if d} - {None}
        else:
            print(f"Warning: unexpected format in {path}, expected list of DOIs.", file=sys.stderr)
            return set()
    except (json.JSONDecodeError, FileNotFoundError, OSError) as exc:
        print(f"Warning: could not load exclude DOIs from {path}: {exc}", file=sys.stderr)
        return set()


def main() -> None:
    args = parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]

    valid_sources = {"pubmed", "biorxiv", "openalex"}
    for src in sources:
        if src not in valid_sources:
            print(f"Error: unknown source {src!r}. Valid: {', '.join(sorted(valid_sources))}", file=sys.stderr)
            sys.exit(1)

    exclude_dois = load_exclude_dois(args.exclude_dois)
    if exclude_dois:
        print(f"Loaded {len(exclude_dois)} DOIs to exclude.")

    # Dispatch table
    search_functions = {
        "pubmed": search_pubmed,
        "biorxiv": search_biorxiv,
        "openalex": search_openalex,
    }

    all_papers: list[dict[str, Any]] = []

    for query in queries:
        print(f"\n{'='*60}")
        print(f"Query: {query}")
        print(f"{'='*60}")

        for source in sources:
            search_fn = search_functions[source]
            papers = search_fn(query, args.max_results, args.date_from, args.date_to)
            all_papers.extend(papers)

    print(f"\nTotal papers before deduplication: {len(all_papers)}")

    # Deduplicate
    unique_papers = deduplicate(all_papers)
    print(f"Unique papers after deduplication: {len(unique_papers)}")

    # Exclude DOIs from prior cycles
    if exclude_dois:
        before = len(unique_papers)
        unique_papers = [
            p for p in unique_papers if not (p.get("doi") and p["doi"] in exclude_dois)
        ]
        excluded = before - len(unique_papers)
        print(f"Excluded {excluded} papers matching exclude-dois list.")

    # Clean up internal fields
    for paper in unique_papers:
        paper.pop("_category", None)

    # Sort by citation count (desc, None last), then by year (desc)
    def _sort_key(p: dict[str, Any]) -> tuple:
        cc = p.get("citation_count")
        yr = p.get("year")
        return (
            -(cc if cc is not None else -1),
            -(yr if yr is not None else 0),
        )

    unique_papers.sort(key=_sort_key)

    print(f"Final paper count: {len(unique_papers)}")

    # Output
    output_json = json.dumps(unique_papers, indent=2, ensure_ascii=False)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
            f.write("\n")
        print(f"\nResults written to {args.output}")
    else:
        print("\n--- Results (JSON) ---")
        print(output_json)


if __name__ == "__main__":
    main()
