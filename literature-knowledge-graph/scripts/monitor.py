#!/usr/bin/env python3
"""Monitor for new publications and update the knowledge graph state.

This script periodically searches configured literature sources for new
publications matching monitoring queries, fetches their metadata, and
prepares them for extraction by the Claude workflow.  It does NOT perform
entity/relationship extraction itself -- it collects papers and creates a
``pending_extraction.json`` manifest so the next extraction cycle knows
what to process.

Usage:
    # Single run (default)
    python monitor.py --config monitor_state.json --neo4j-password secret

    # Daemon mode -- runs on the configured schedule
    python monitor.py --config monitor_state.json --neo4j-password secret --daemon

    # Explicit single run
    python monitor.py --config monitor_state.json --neo4j-password secret --run-once
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import tempfile
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Optional sibling-module imports (graceful fallback)
# ---------------------------------------------------------------------------

_HAS_SEARCH_MODULE = False
_HAS_FETCH_MODULE = False

try:
    # Attempt to import from sibling package laid out beside this script.
    _scripts_dir = Path(__file__).resolve().parent
    if str(_scripts_dir) not in sys.path:
        sys.path.insert(0, str(_scripts_dir))
    if str(_scripts_dir.parent) not in sys.path:
        sys.path.insert(0, str(_scripts_dir.parent))

    from search_literature import search_papers  # type: ignore[import-not-found]
    _HAS_SEARCH_MODULE = True
except Exception:
    pass

try:
    from fetch_fulltext import fetch_fulltext  # type: ignore[import-not-found]
    _HAS_FETCH_MODULE = True
except Exception:
    pass

try:
    import requests
except ImportError:
    requests = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SCHEDULE_INTERVALS: Dict[str, timedelta] = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "biweekly": timedelta(weeks=2),
    "monthly": timedelta(days=30),
}

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds

_SHUTDOWN_REQUESTED = False


def _handle_signal(signum: int, frame: Any) -> None:
    """Handle SIGINT / SIGTERM for graceful daemon shutdown."""
    global _SHUTDOWN_REQUESTED
    _SHUTDOWN_REQUESTED = True
    print("\n[monitor] Shutdown requested -- finishing current cycle ...", flush=True)


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: str | Path) -> Dict[str, Any]:
    """Load and validate the monitor configuration JSON."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r", encoding="utf-8") as fh:
        config = json.load(fh)

    required_keys = {
        "project",
        "monitoring_queries",
        "sources",
        "known_dois",
    }
    missing = required_keys - set(config.keys())
    if missing:
        raise ValueError(f"Config JSON is missing required keys: {missing}")

    # Apply defaults for optional keys.
    config.setdefault("last_search_date", datetime.utcnow().strftime("%Y-%m-%d"))
    config.setdefault("max_results_per_query", 20)
    config.setdefault("schedule", "weekly")
    config.setdefault("output_dir", "./monitor_output")
    config.setdefault("history", [])
    config.setdefault("total_papers", 0)
    config.setdefault("total_entities", 0)
    config.setdefault("total_relationships", 0)
    config.setdefault("schema_path", "")
    config.setdefault("schema_version", "")

    return config


def save_config(config: Dict[str, Any], path: str | Path) -> None:
    """Atomically write config: write to a temp file then rename."""
    config_path = Path(path)
    config_dir = config_path.parent
    config_dir.mkdir(parents=True, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(config_dir),
        prefix=".monitor_state_",
        suffix=".json.tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(config, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp_path, str(config_path))
    except BaseException:
        # Clean up temp file on failure.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Network helpers with retry
# ---------------------------------------------------------------------------

def _retry(func, *args, max_retries: int = _MAX_RETRIES, **kwargs) -> Any:
    """Call *func* with exponential-backoff retries on network errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            last_exc = exc
            # Only retry on likely-transient network errors.
            is_transient = False
            if requests is not None:
                try:
                    from requests.exceptions import (
                        ConnectionError as ReqConnectionError,
                        Timeout as ReqTimeout,
                        HTTPError as ReqHTTPError,
                    )
                    if isinstance(exc, (ReqConnectionError, ReqTimeout)):
                        is_transient = True
                    elif isinstance(exc, ReqHTTPError):
                        if hasattr(exc, "response") and exc.response is not None:
                            if exc.response.status_code in (429, 500, 502, 503, 504):
                                is_transient = True
                except ImportError:
                    pass

            if isinstance(exc, (ConnectionError, TimeoutError, OSError)):
                is_transient = True

            if not is_transient:
                raise

            wait = _RETRY_BACKOFF_BASE ** attempt
            print(
                f"  [retry] Attempt {attempt + 1}/{max_retries} failed: {exc}. "
                f"Retrying in {wait}s ...",
                flush=True,
            )
            time.sleep(wait)

    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Builtin (fallback) literature search
# ---------------------------------------------------------------------------

def _builtin_search_pubmed(
    query: str,
    since_date: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """Search PubMed via the NCBI E-utilities API (no API key required
    for low-volume use).  Returns a list of paper metadata dicts."""
    if requests is None:
        print("  [warn] 'requests' not installed -- skipping PubMed search", flush=True)
        return []

    base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    # E-search: get PMIDs.
    search_params = {
        "db": "pubmed",
        "term": query,
        "retmax": max_results,
        "retmode": "json",
        "sort": "date",
        "mindate": since_date.replace("-", "/"),
        "maxdate": datetime.utcnow().strftime("%Y/%m/%d"),
        "datetype": "pdat",
    }

    def _do_search():
        resp = requests.get(f"{base}/esearch.fcgi", params=search_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    data = _retry(_do_search)
    id_list = data.get("esearchresult", {}).get("idlist", [])
    if not id_list:
        return []

    # E-summary: get metadata for each PMID.
    summary_params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "json",
    }

    def _do_summary():
        resp = requests.get(f"{base}/esummary.fcgi", params=summary_params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    summary_data = _retry(_do_summary)
    results: List[Dict[str, Any]] = []
    uid_records = summary_data.get("result", {})
    for pmid in id_list:
        rec = uid_records.get(pmid)
        if rec is None:
            continue

        # Try to extract DOI from article IDs.
        doi = ""
        for aid in rec.get("articleids", []):
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break

        results.append({
            "pmid": pmid,
            "doi": doi,
            "title": rec.get("title", ""),
            "authors": [
                a.get("name", "") for a in rec.get("authors", [])
            ],
            "journal": rec.get("fulljournalname", rec.get("source", "")),
            "year": rec.get("pubdate", "")[:4],
            "abstract": "",  # E-summary does not return abstracts.
            "source": "pubmed",
        })

    return results


def _builtin_search_openalex(
    query: str,
    since_date: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """Search OpenAlex for works matching *query* published since *since_date*."""
    if requests is None:
        print("  [warn] 'requests' not installed -- skipping OpenAlex search", flush=True)
        return []

    params = {
        "search": query,
        "filter": f"from_publication_date:{since_date}",
        "per_page": min(max_results, 50),
        "sort": "publication_date:desc",
        "mailto": "monitor@example.com",
    }

    def _do_search():
        resp = requests.get(
            "https://api.openalex.org/works",
            params=params,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    data = _retry(_do_search)
    results: List[Dict[str, Any]] = []
    for work in data.get("results", []):
        doi_url = work.get("doi", "") or ""
        doi = doi_url.replace("https://doi.org/", "").replace("http://doi.org/", "")

        authorships = work.get("authorships", [])
        authors = []
        for a in authorships:
            author_obj = a.get("author", {})
            name = author_obj.get("display_name", "")
            if name:
                authors.append(name)

        results.append({
            "doi": doi,
            "title": work.get("title", ""),
            "authors": authors,
            "journal": (work.get("primary_location") or {}).get("source", {}).get("display_name", "") if work.get("primary_location") else "",
            "year": str(work.get("publication_year", "")),
            "abstract": "",
            "source": "openalex",
            "openalex_id": work.get("id", ""),
        })

    return results


def _builtin_search_biorxiv(
    query: str,
    since_date: str,
    max_results: int,
) -> List[Dict[str, Any]]:
    """Search bioRxiv/medRxiv via the bioRxiv content API.

    Note: the bioRxiv API is date-range based and does not support full-text
    keyword search.  We fetch recent preprints and do client-side title
    filtering as a best-effort approach.
    """
    if requests is None:
        print("  [warn] 'requests' not installed -- skipping bioRxiv search", flush=True)
        return []

    today = datetime.utcnow().strftime("%Y-%m-%d")
    url = f"https://api.biorxiv.org/details/biorxiv/{since_date}/{today}/0/50"

    def _do_search():
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.json()

    try:
        data = _retry(_do_search)
    except Exception as exc:
        print(f"  [warn] bioRxiv API error: {exc}", flush=True)
        return []

    query_lower = query.lower()
    query_terms = query_lower.split()
    results: List[Dict[str, Any]] = []

    for item in data.get("collection", []):
        title = item.get("title", "")
        abstract = item.get("abstract", "")
        text = f"{title} {abstract}".lower()

        # Require all query terms to appear in title or abstract.
        if not all(term in text for term in query_terms):
            continue

        results.append({
            "doi": item.get("doi", ""),
            "title": title,
            "authors": item.get("authors", "").split("; ") if item.get("authors") else [],
            "journal": "bioRxiv",
            "year": item.get("date", "")[:4],
            "abstract": abstract,
            "source": "biorxiv",
        })

        if len(results) >= max_results:
            break

    return results


# ---------------------------------------------------------------------------
# Core search dispatcher
# ---------------------------------------------------------------------------

_SOURCE_SEARCHERS = {
    "pubmed": _builtin_search_pubmed,
    "openalex": _builtin_search_openalex,
    "biorxiv": _builtin_search_biorxiv,
}


def search_new_papers(
    queries: List[str],
    sources: List[str],
    since_date: str,
    max_results_per_query: int,
    known_dois: set,
) -> List[Dict[str, Any]]:
    """Search multiple sources for papers matching *queries* since *since_date*.

    If the ``search_literature`` sibling module is available its
    ``search_papers`` function is used; otherwise the built-in searchers
    are used as a fallback.

    Returns deduplicated results excluding *known_dois*.
    """
    all_papers: List[Dict[str, Any]] = []
    seen_dois: set = set()
    failures: List[Dict[str, str]] = []

    for query in queries:
        for source in sources:
            source_key = source.lower().strip()
            print(f"  Searching {source_key} for: {query!r}", flush=True)

            try:
                if _HAS_SEARCH_MODULE:
                    papers = _retry(
                        search_papers,
                        query=query,
                        source=source_key,
                        since_date=since_date,
                        max_results=max_results_per_query,
                    )
                elif source_key in _SOURCE_SEARCHERS:
                    papers = _retry(
                        _SOURCE_SEARCHERS[source_key],
                        query,
                        since_date,
                        max_results_per_query,
                    )
                else:
                    print(
                        f"    [skip] No searcher available for source: {source_key}",
                        flush=True,
                    )
                    continue
            except Exception as exc:
                msg = f"Search failed for query={query!r} source={source_key}: {exc}"
                print(f"    [error] {msg}", flush=True)
                failures.append({"query": query, "source": source_key, "error": str(exc)})
                continue

            new_count = 0
            for paper in papers:
                doi = (paper.get("doi") or "").strip()
                if not doi:
                    # Papers without DOIs -- use a synthetic key.
                    pmid = paper.get("pmid", "")
                    if pmid:
                        doi = f"pmid:{pmid}"
                    else:
                        doi = f"notitle:{hash(paper.get('title', ''))}"

                if doi in known_dois or doi in seen_dois:
                    continue

                seen_dois.add(doi)
                paper["_doi_key"] = doi
                all_papers.append(paper)
                new_count += 1

            print(f"    Found {new_count} new paper(s)", flush=True)

    if failures:
        print(f"\n  [warn] {len(failures)} search(es) failed (see log above)", flush=True)

    return all_papers


# ---------------------------------------------------------------------------
# Full-text fetching
# ---------------------------------------------------------------------------

def fetch_paper_fulltext(paper: Dict[str, Any]) -> Dict[str, Any]:
    """Attempt to fetch full text for a paper.

    Uses the ``fetch_fulltext`` sibling module if available; otherwise
    returns the paper as-is with ``full_text_available`` set to False.
    """
    if _HAS_FETCH_MODULE:
        try:
            enriched = _retry(fetch_fulltext, paper)
            return enriched
        except Exception as exc:
            print(
                f"    [warn] Full-text fetch failed for {paper.get('doi', '?')}: {exc}",
                flush=True,
            )

    paper["full_text_available"] = False
    return paper


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def save_papers(papers: List[Dict[str, Any]], output_dir: Path) -> Path:
    """Save collected papers to a JSON file in *output_dir*.

    Returns the path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_path = output_dir / f"papers_{timestamp}.json"

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(papers, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return out_path


def save_pending_extraction(
    papers: List[Dict[str, Any]],
    output_dir: Path,
    config: Dict[str, Any],
) -> Path:
    """Create a ``pending_extraction.json`` manifest signalling that new
    papers are available for the Claude extraction workflow.

    Returns the path to the manifest file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "pending_extraction.json"

    manifest: Dict[str, Any] = {
        "created": datetime.utcnow().isoformat() + "Z",
        "project": config.get("project", ""),
        "schema_path": config.get("schema_path", ""),
        "schema_version": config.get("schema_version", ""),
        "paper_count": len(papers),
        "papers": [
            {
                "doi": p.get("doi", ""),
                "pmid": p.get("pmid", ""),
                "title": p.get("title", ""),
                "source": p.get("source", ""),
                "full_text_available": p.get("full_text_available", False),
            }
            for p in papers
        ],
        "status": "pending",
    }

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    return manifest_path


# ---------------------------------------------------------------------------
# Single monitoring cycle
# ---------------------------------------------------------------------------

def run_cycle(config: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    """Execute one monitoring cycle.  Returns a summary dict."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    since_date = config.get("last_search_date", today)
    known_dois = set(config.get("known_dois", []))
    output_dir = Path(config.get("output_dir", "./monitor_output"))

    print(f"\n{'=' * 60}", flush=True)
    print(f"  Monitor cycle -- {today}", flush=True)
    print(f"  Project: {config.get('project', '?')}", flush=True)
    print(f"  Searching since: {since_date}", flush=True)
    print(f"  Queries: {config.get('monitoring_queries', [])}", flush=True)
    print(f"  Sources: {config.get('sources', [])}", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    # 1. Search for new papers.
    new_papers = search_new_papers(
        queries=config.get("monitoring_queries", []),
        sources=config.get("sources", []),
        since_date=since_date,
        max_results_per_query=config.get("max_results_per_query", 20),
        known_dois=known_dois,
    )

    # 2. Fetch full text for each new paper.
    enriched_papers: List[Dict[str, Any]] = []
    for i, paper in enumerate(new_papers, 1):
        doi_display = paper.get("doi") or paper.get("pmid") or paper.get("title", "?")
        print(f"  [{i}/{len(new_papers)}] Fetching: {doi_display}", flush=True)
        enriched = fetch_paper_fulltext(paper)
        enriched_papers.append(enriched)

    # 3. Save papers and pending-extraction manifest.
    source_counts: Dict[str, int] = {}
    new_doi_keys: List[str] = []
    if enriched_papers:
        papers_path = save_papers(enriched_papers, output_dir)
        print(f"\n  Papers saved to: {papers_path}", flush=True)

        manifest_path = save_pending_extraction(enriched_papers, output_dir, config)
        print(f"  Pending-extraction manifest: {manifest_path}", flush=True)

        for p in enriched_papers:
            src = p.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1
            doi_key = p.get("_doi_key") or p.get("doi", "")
            if doi_key:
                new_doi_keys.append(doi_key)

    # 4. Update config state.
    config["last_search_date"] = today
    config["known_dois"] = list(known_dois | set(new_doi_keys))
    config["total_papers"] = config.get("total_papers", 0) + len(enriched_papers)

    history_entry = {
        "date": today,
        "new_papers": len(enriched_papers),
        "new_entities": 0,
        "new_relationships": 0,
        "cycle": "monitor",
        "status": "papers_collected" if enriched_papers else "no_new_papers",
    }
    config.setdefault("history", []).append(history_entry)

    save_config(config, config_path)
    print(f"\n  Config updated: {config_path}", flush=True)

    # 5. Print report.
    print(f"\n{'=' * 60}", flush=True)
    print(f"  Monitoring report -- {today}", flush=True)
    print(f"{'=' * 60}", flush=True)
    print(f"  New papers found: {len(enriched_papers)}", flush=True)
    if source_counts:
        for src, cnt in sorted(source_counts.items()):
            print(f"    - {src}: {cnt}", flush=True)
    else:
        print("    (none)", flush=True)
    print(f"  Total known papers: {config['total_papers']}", flush=True)
    print(f"  Total known DOIs:   {len(config['known_dois'])}", flush=True)
    if enriched_papers:
        print(f"\n  ** {len(enriched_papers)} paper(s) pending extraction **", flush=True)
    print(f"{'=' * 60}\n", flush=True)

    return {
        "date": today,
        "new_papers": len(enriched_papers),
        "source_counts": source_counts,
        "status": history_entry["status"],
    }


# ---------------------------------------------------------------------------
# Daemon loop
# ---------------------------------------------------------------------------

def run_daemon(config: Dict[str, Any], config_path: Path) -> None:
    """Run monitoring cycles on a schedule until interrupted."""
    schedule = config.get("schedule", "weekly").lower().strip()
    interval = _SCHEDULE_INTERVALS.get(schedule)
    if interval is None:
        print(
            f"[error] Unknown schedule '{schedule}'. "
            f"Valid options: {', '.join(_SCHEDULE_INTERVALS)}",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[monitor] Daemon mode -- schedule={schedule} (every {interval})", flush=True)
    print("[monitor] Press Ctrl+C to stop.\n", flush=True)

    # Register signal handlers for graceful shutdown.
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not _SHUTDOWN_REQUESTED:
        try:
            # Reload config each cycle so external edits are picked up.
            config = load_config(config_path)
            run_cycle(config, config_path)
        except Exception:
            print("[error] Cycle failed with exception:", file=sys.stderr, flush=True)
            traceback.print_exc(file=sys.stderr)

        if _SHUTDOWN_REQUESTED:
            break

        # Sleep in small increments to respond promptly to shutdown signals.
        sleep_seconds = interval.total_seconds()
        print(
            f"[monitor] Next run in {interval}. Sleeping until "
            f"{(datetime.utcnow() + interval).strftime('%Y-%m-%d %H:%M UTC')} ...\n",
            flush=True,
        )
        slept = 0.0
        while slept < sleep_seconds and not _SHUTDOWN_REQUESTED:
            chunk = min(10.0, sleep_seconds - slept)
            time.sleep(chunk)
            slept += chunk

    print("[monitor] Daemon stopped.", flush=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor for new publications and prepare them for knowledge-graph "
            "extraction."
        ),
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the monitor config/state JSON file (required)",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--run-once",
        action="store_true",
        default=True,
        help="Run a single monitoring cycle and exit (default)",
    )
    mode_group.add_argument(
        "--daemon",
        action="store_true",
        default=False,
        help="Run continuously on the configured schedule",
    )

    parser.add_argument(
        "--neo4j-uri",
        default="bolt://localhost:7687",
        help="Neo4j Bolt URI (default: bolt://localhost:7687)",
    )
    parser.add_argument(
        "--neo4j-user",
        default="neo4j",
        help="Neo4j username (default: neo4j)",
    )
    parser.add_argument(
        "--neo4j-password",
        required=True,
        help="Neo4j password (required)",
    )

    return parser.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)

    # Validate config path.
    config_path = Path(args.config).resolve()
    try:
        config = load_config(config_path)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[error] Config error: {exc}", file=sys.stderr)
        return 1

    # Store Neo4j connection info in config for downstream use (not persisted).
    config["_neo4j"] = {
        "uri": args.neo4j_uri,
        "user": args.neo4j_user,
        "password": args.neo4j_password,
    }

    # Announce capabilities.
    if _HAS_SEARCH_MODULE:
        print("[monitor] Using search_literature module for searches.", flush=True)
    else:
        print("[monitor] search_literature module not found -- using built-in searchers.", flush=True)

    if _HAS_FETCH_MODULE:
        print("[monitor] Using fetch_fulltext module for full-text retrieval.", flush=True)
    else:
        print("[monitor] fetch_fulltext module not found -- full text will not be fetched.", flush=True)

    if requests is None:
        print(
            "[warn] 'requests' library not installed. "
            "Built-in searchers will be unavailable.\n"
            "Install it with:  pip install requests",
            file=sys.stderr,
        )

    # Run.
    if args.daemon:
        run_daemon(config, config_path)
        return 0
    else:
        try:
            summary = run_cycle(config, config_path)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 1
        return 0


if __name__ == "__main__":
    sys.exit(main())
