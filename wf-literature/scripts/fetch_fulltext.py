"""PMC/Europe PMC full text acquisition with structured section splitting.

Downloads full text XML from PMC (NCBI) and Europe PMC, parses into
canonical sections, and saves as structured text files.
Supports incremental processing (pending-only) and NCBI API key.

Based on prophage-miner fetch_fulltext.py pattern with wf-migrate's
robust HTTP handling (socket timeout, 429/503 handling, circuit breaker).
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

PMC_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
EUROPEPMC_BATCH_LIMIT = 50

_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
_REQUEST_DELAY = 0.15 if _NCBI_API_KEY else 0.4
_USER_AGENT = "wf-literature/3.0 (purpose: academic-workflow-composition)"
_MAX_FULLTEXT_CHARS = 300_000

if not _NCBI_API_KEY:
    print("[fetch_fulltext] No NCBI_API_KEY set. Rate limit: 3 req/sec.",
          file=sys.stderr, flush=True)

SECTION_MAP = {
    "intro": "INTRODUCTION",
    "introduction": "INTRODUCTION",
    "background": "INTRODUCTION",
    "methods": "METHODS",
    "materials": "METHODS",
    "materials and methods": "METHODS",
    "materials|methods": "METHODS",
    "experimental": "METHODS",
    "experimental procedures": "METHODS",
    "experimental section": "METHODS",
    "results": "RESULTS",
    "results and discussion": "RESULTS",
    "discussion": "DISCUSSION",
    "conclusions": "DISCUSSION",
    "conclusion": "DISCUSSION",
}

ORDERED_SECTIONS = ["ABSTRACT", "INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION"]


# ---------------------------------------------------------------------------
# HTTP helper (adapted from wf-migrate _http_get)
# ---------------------------------------------------------------------------

def _ncbi_url(url: str) -> str:
    if _NCBI_API_KEY and "ncbi.nlm.nih.gov" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={_NCBI_API_KEY}"
    return url


def _http_get(url: str, timeout: int = 30, max_retries: int = 3) -> str:
    """HTTP GET with adaptive retry on 429/network errors."""
    url = _ncbi_url(url)
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = min(2 ** attempt * 2, 30)
                    print(f"  [429] Rate limited, waiting {wait}s "
                          f"(attempt {attempt+1}/{max_retries})...",
                          file=sys.stderr, flush=True)
                    time.sleep(wait)
                    continue
                if e.code in (403, 503):
                    print(f"  [{e.code}] Server blocked/unavailable, skipping",
                          file=sys.stderr, flush=True)
                    return ""
                return ""
            except (urllib.error.URLError, OSError, TimeoutError, socket.timeout):
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return ""
        return ""
    finally:
        socket.setdefaulttimeout(old_timeout)


# ---------------------------------------------------------------------------
# XML section parsing
# ---------------------------------------------------------------------------

def _collect_text(element: ET.Element) -> str:
    """Recursively collect all text content from an XML element."""
    parts = []
    for el in element.iter():
        if el.tag == "title":
            continue
        if el.text:
            parts.append(el.text.strip())
        if el.tail:
            parts.append(el.tail.strip())
    return " ".join(p for p in parts if p)


def parse_sections(xml_text: str) -> dict[str, str]:
    """Parse PMC XML into section-name -> text mapping.

    Extracts ABSTRACT, INTRODUCTION, METHODS, RESULTS, DISCUSSION and
    any additional named sections found in the <body>.
    """
    if not xml_text or not xml_text.strip():
        return {}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    sections: dict[str, str] = {}

    # Abstract
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        abstract_text = _collect_text(abstract_el)
        if abstract_text.strip():
            sections["ABSTRACT"] = abstract_text.strip()

    # Body sections
    for sec in root.findall(".//body/sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title_text = (title_el.text or "").lower() if title_el is not None else ""

        section_name = None
        for key, name in SECTION_MAP.items():
            if key in sec_type or key in title_text:
                section_name = name
                break

        if section_name is None:
            if title_el is not None and title_el.text:
                section_name = title_el.text.strip().upper()
            else:
                continue

        text = _collect_text(sec)
        if text.strip():
            if section_name in sections:
                sections[section_name] += "\n" + text.strip()
            else:
                sections[section_name] = text.strip()

    return sections


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_pmc_xml(pmcid: str) -> str:
    """Fetch full text XML from NCBI PMC efetch API."""
    if not pmcid:
        return ""
    numeric_id = pmcid.replace("PMC", "")
    url = (f"{PMC_EFETCH}?db=pmc&id={numeric_id}&rettype=xml&retmode=xml")
    print(f"[fetch_fulltext] Fetching PMC XML for {pmcid}...",
          file=sys.stderr, flush=True)
    time.sleep(_REQUEST_DELAY)
    return _http_get(url)


_europepmc_batch_count = 0


def fetch_europepmc(pmcid: str) -> str:
    """Fallback: fetch full text XML from Europe PMC REST API."""
    global _europepmc_batch_count
    if not pmcid:
        return ""
    if _europepmc_batch_count >= EUROPEPMC_BATCH_LIMIT:
        print("[fetch_fulltext] Europe PMC batch limit reached",
              file=sys.stderr, flush=True)
        return ""
    _europepmc_batch_count += 1
    url = f"{EUROPEPMC_BASE}/{pmcid}/fullTextXML"
    print(f"[fetch_fulltext] Trying Europe PMC for {pmcid}...",
          file=sys.stderr, flush=True)
    time.sleep(_REQUEST_DELAY)
    return _http_get(url)


# ---------------------------------------------------------------------------
# Save
# ---------------------------------------------------------------------------

def save_fulltext(paper_id: str, sections: dict[str, str], output_dir: Path) -> Path:
    """Save sections as structured text file with === SECTION === headers."""
    output_dir = Path(output_dir)
    path = output_dir / "01_papers" / "full_texts" / f"{paper_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    for key in ORDERED_SECTIONS:
        if key in sections:
            lines.append(f"=== {key} ===")
            lines.append(sections[key][:_MAX_FULLTEXT_CHARS])
            lines.append("")

    for key in sorted(sections.keys()):
        if key not in ORDERED_SECTIONS:
            lines.append(f"=== {key} ===")
            lines.append(sections[key][:_MAX_FULLTEXT_CHARS])
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    print(f"[fetch_fulltext] Saved {paper_id}.txt ({len(sections)} sections)",
          file=sys.stderr, flush=True)
    return path


# ---------------------------------------------------------------------------
# Main processing pipeline
# ---------------------------------------------------------------------------

def process_papers(
    paper_list_path: Path,
    output_dir: Path,
    pending_only: bool = True,
) -> dict:
    """Process papers from paper_list.json: fetch full text, parse, save.

    Args:
        paper_list_path: Path to paper_list.json
        output_dir: Workflow directory (parent of 01_papers/)
        pending_only: Skip papers that already have has_full_text=True

    Returns:
        Stats dict with processed/skipped/failed counts and per-paper details.
    """
    paper_list_path = Path(paper_list_path)
    output_dir = Path(output_dir)
    data = json.loads(paper_list_path.read_text(encoding="utf-8"))

    papers = data.get("papers", [])
    if not papers:
        for key in data:
            if key.startswith("P") and isinstance(data[key], dict):
                papers.append({**data[key], "paper_id": key})

    stats: dict = {
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "no_pmcid": 0,
        "details": [],
    }

    ft_dir = output_dir / "01_papers" / "full_texts"
    consecutive_failures = 0

    for paper in papers:
        pid = paper.get("paper_id", "unknown")

        if pending_only and paper.get("has_full_text", False):
            existing_file = ft_dir / f"{pid}.txt"
            if existing_file.exists() and existing_file.stat().st_size > 100:
                stats["skipped"] += 1
                continue

        pmcid = str(paper.get("pmcid", "") or "").strip()
        if not pmcid:
            stats["no_pmcid"] += 1
            stats["details"].append({"paper_id": pid, "status": "no_pmcid"})
            continue

        xml = fetch_pmc_xml(pmcid)
        if not xml:
            xml = fetch_europepmc(pmcid)

        if not xml:
            stats["failed"] += 1
            stats["details"].append({"paper_id": pid, "status": "fetch_failed"})
            consecutive_failures += 1
            if consecutive_failures >= 5:
                print("[fetch_fulltext] 5 consecutive failures, pausing 30s...",
                      file=sys.stderr, flush=True)
                time.sleep(30)
                consecutive_failures = 0
            continue

        sections = parse_sections(xml)
        if not sections:
            stats["failed"] += 1
            stats["details"].append({"paper_id": pid, "status": "parse_failed"})
            continue

        save_fulltext(pid, sections, output_dir)
        paper["has_full_text"] = True
        paper["text_source"] = "pmc_oa"
        stats["processed"] += 1
        stats["details"].append({
            "paper_id": pid,
            "status": "ok",
            "sections": list(sections.keys()),
            "total_chars": sum(len(v) for v in sections.values()),
        })
        consecutive_failures = 0

    paper_list_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(
        f"[fetch_fulltext] Done: {stats['processed']} processed, "
        f"{stats['skipped']} skipped, {stats['failed']} failed, "
        f"{stats['no_pmcid']} no_pmcid",
        file=sys.stderr, flush=True,
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Fetch PMC full text for papers in paper_list.json"
    )
    parser.add_argument(
        "--input", type=Path, required=True,
        help="Path to paper_list.json",
    )
    parser.add_argument(
        "--output", type=Path,
        help="Workflow output directory (defaults to input's grandparent)",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Re-fetch all papers, not just pending ones",
    )
    args = parser.parse_args()

    output = args.output or args.input.parent.parent
    result = process_papers(args.input, output, pending_only=not args.all)
    json.dump(result, sys.stdout, indent=2, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
