#!/usr/bin/env python3
"""Fetch full text of scientific papers from PMC XML, bioRxiv PDF, and local PDFs.

Parses retrieved content into structured sections (abstract, introduction,
methods, results, discussion, figures/tables) and saves per-paper JSON files
along with a summary manifest.

Usage:
    python fetch_fulltext.py --papers search_results.json --output-dir ./fulltext/
    python fetch_fulltext.py --papers search_results.json --local-pdfs ./pdfs/
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from threading import Lock
from typing import Any, Dict, List, Optional

import requests
from lxml import etree

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Rate-limit helpers
# ---------------------------------------------------------------------------

class RateLimiter:
    """Thread-safe token-bucket style rate limiter (minimum interval)."""

    def __init__(self, min_interval: float):
        self._min_interval = min_interval
        self._last: float = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)
            self._last = time.monotonic()


_pmc_limiter = RateLimiter(1.0 / 3.0)      # 3 req/s
_biorxiv_limiter = RateLimiter(0.5)         # 0.5 s between requests

# ---------------------------------------------------------------------------
# PDF text extraction helpers
# ---------------------------------------------------------------------------

def _extract_text_markitdown(pdf_bytes: bytes) -> Optional[str]:
    """Try markitdown first; returns markdown text or None."""
    try:
        from markitdown import MarkItDown  # type: ignore

        converter = MarkItDown()
        result = converter.convert_stream(io.BytesIO(pdf_bytes), file_extension=".pdf")
        text = getattr(result, "text_content", None) or getattr(result, "markdown", None)
        if text and len(text.strip()) > 100:
            return text.strip()
    except Exception as exc:
        log.debug("markitdown failed: %s", exc)
    return None


def _extract_text_pypdf(pdf_bytes: bytes) -> Optional[str]:
    """Fallback: extract text with pypdf."""
    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text)
        full = "\n\n".join(pages)
        if full.strip():
            return full.strip()
    except Exception as exc:
        log.debug("pypdf failed: %s", exc)
    return None


def _pdf_to_text(pdf_bytes: bytes) -> Optional[str]:
    """Convert PDF bytes to text, trying markitdown then pypdf."""
    text = _extract_text_markitdown(pdf_bytes)
    if text:
        return text
    return _extract_text_pypdf(pdf_bytes)


# ---------------------------------------------------------------------------
# Heuristic section splitting for plain text / markdown
# ---------------------------------------------------------------------------

# Canonical section names in order of appearance
_SECTION_PATTERNS: List[tuple[str, re.Pattern]] = [
    ("abstract", re.compile(
        r"^\s*(?:#{1,3}\s*)?(?:abstract)\s*$", re.IGNORECASE | re.MULTILINE)),
    ("introduction", re.compile(
        r"^\s*(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:introduction|background)\s*$",
        re.IGNORECASE | re.MULTILINE)),
    ("methods", re.compile(
        r"^\s*(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:methods?|materials?\s*(?:and|&)\s*methods?|experimental\s*(?:procedures?|section))\s*$",
        re.IGNORECASE | re.MULTILINE)),
    ("results", re.compile(
        r"^\s*(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:results?|results?\s*(?:and|&)\s*discussion)\s*$",
        re.IGNORECASE | re.MULTILINE)),
    ("discussion", re.compile(
        r"^\s*(?:#{1,3}\s*)?(?:\d+\.?\s*)?(?:discussion|conclusions?|summary)\s*$",
        re.IGNORECASE | re.MULTILINE)),
]


def _split_sections_heuristic(text: str) -> Dict[str, str]:
    """Split free-form text into sections by recognising common headings."""
    # Find all heading positions
    found: list[tuple[str, int]] = []
    for name, pat in _SECTION_PATTERNS:
        m = pat.search(text)
        if m:
            found.append((name, m.start()))

    # Sort by position in the document
    found.sort(key=lambda x: x[1])

    sections: Dict[str, str] = {}

    if not found:
        # Could not identify any headings; put everything in abstract
        sections["abstract"] = text[:5000].strip()
        return sections

    # Text before the first identified heading (could be title / abstract)
    preamble = text[: found[0][1]].strip()
    if preamble and "abstract" not in [f[0] for f in found]:
        sections["abstract"] = preamble[:5000]

    for idx, (name, start) in enumerate(found):
        end = found[idx + 1][1] if idx + 1 < len(found) else len(text)
        # Skip the heading line itself
        heading_end = text.find("\n", start)
        if heading_end == -1:
            heading_end = start
        body = text[heading_end:end].strip()
        if body:
            sections[name] = body

    return sections


# ---------------------------------------------------------------------------
# PMC XML fetching & parsing
# ---------------------------------------------------------------------------

_EFETCH_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pmc&id={pmcid}&rettype=xml"
)


def _fetch_pmc_xml(pmcid: str, session: requests.Session) -> Optional[str]:
    """Download PMC XML for a given PMCID. Returns raw XML string or None."""
    url = _EFETCH_URL.format(pmcid=pmcid)
    _pmc_limiter.wait()
    try:
        resp = session.get(url, timeout=60)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as exc:
        log.warning("PMC fetch failed for %s: %s", pmcid, exc)
        return None


def _text_of(element: Optional[etree._Element]) -> str:
    """Recursively extract text from an lxml element, joining all text nodes."""
    if element is None:
        return ""
    parts: list[str] = []
    for node in element.iter():
        if node.text:
            parts.append(node.text)
        if node.tail:
            parts.append(node.tail)
    return " ".join(parts).strip()


def _extract_named_section(body: etree._Element, title_keywords: List[str]) -> str:
    """Find a <sec> whose <title> matches any of the given keywords."""
    for sec in body.iter("sec"):
        title_el = sec.find("title")
        if title_el is not None:
            title_text = _text_of(title_el).lower()
            if any(kw in title_text for kw in title_keywords):
                # Collect all paragraphs inside this section
                paragraphs = [_text_of(p) for p in sec.iter("p")]
                return "\n\n".join(p for p in paragraphs if p)
    return ""


def _parse_pmc_xml(xml_str: str) -> Dict[str, Any]:
    """Parse PMC XML into structured sections dict."""
    sections: Dict[str, Any] = {
        "abstract": "",
        "introduction": "",
        "methods": "",
        "results": "",
        "discussion": "",
        "figures_tables": [],
    }

    try:
        root = etree.fromstring(xml_str.encode("utf-8"))
    except etree.XMLSyntaxError as exc:
        log.warning("XML parse error: %s", exc)
        return sections

    # --- Abstract ---
    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        paragraphs = [_text_of(p) for p in abstract_el.iter("p")]
        sections["abstract"] = "\n\n".join(p for p in paragraphs if p)

    # --- Body sections ---
    body = root.find(".//body")
    if body is not None:
        sections["introduction"] = _extract_named_section(
            body, ["introduction", "background"]
        )
        sections["methods"] = _extract_named_section(
            body, ["method", "material", "experimental", "procedure"]
        )
        sections["results"] = _extract_named_section(
            body, ["result"]
        )
        sections["discussion"] = _extract_named_section(
            body, ["discussion", "conclusion", "summary"]
        )

        # --- Figures and Tables ---
        figs_tables: list[str] = []

        for tw in body.iter("table-wrap"):
            label_el = tw.find("label")
            caption_el = tw.find("caption")
            label = _text_of(label_el) if label_el is not None else "Table"
            caption = _text_of(caption_el) if caption_el is not None else ""
            entry = f"{label}: {caption}".strip()
            if entry:
                figs_tables.append(entry)

        for fig in body.iter("fig"):
            label_el = fig.find("label")
            caption_el = fig.find("caption")
            label = _text_of(label_el) if label_el is not None else "Figure"
            caption = _text_of(caption_el) if caption_el is not None else ""
            entry = f"{label}: {caption}".strip()
            if entry:
                figs_tables.append(entry)

        sections["figures_tables"] = figs_tables

    return sections


# ---------------------------------------------------------------------------
# bioRxiv PDF fetching
# ---------------------------------------------------------------------------

_BIORXIV_PDF_URL = "https://www.biorxiv.org/content/{doi}v1.full.pdf"


def _fetch_biorxiv_pdf(doi: str, session: requests.Session) -> Optional[bytes]:
    """Download a bioRxiv paper as PDF bytes."""
    url = _BIORXIV_PDF_URL.format(doi=doi)
    _biorxiv_limiter.wait()
    try:
        resp = session.get(url, timeout=120, allow_redirects=True)
        resp.raise_for_status()
        if "application/pdf" in resp.headers.get("Content-Type", ""):
            return resp.content
        # Sometimes the server returns HTML instead of PDF
        if resp.content[:5] == b"%PDF-":
            return resp.content
        log.warning("bioRxiv response for %s was not a PDF", doi)
        return None
    except requests.RequestException as exc:
        log.warning("bioRxiv PDF fetch failed for %s: %s", doi, exc)
        return None


# ---------------------------------------------------------------------------
# Local PDF matching
# ---------------------------------------------------------------------------

def _doi_to_filename(doi: str) -> str:
    """Convert a DOI to the expected local filename (/ -> _)."""
    return doi.replace("/", "_")


def _find_local_pdf(
    doi: Optional[str],
    title: Optional[str],
    local_dir: Path,
) -> Optional[Path]:
    """Locate a local PDF by DOI-based filename or title similarity."""
    if not local_dir.is_dir():
        return None

    pdf_files = list(local_dir.glob("*.pdf")) + list(local_dir.glob("*.PDF"))
    if not pdf_files:
        return None

    # 1. Match by DOI in filename
    if doi:
        doi_safe = _doi_to_filename(doi)
        for pdf in pdf_files:
            stem = pdf.stem
            if stem == doi_safe or stem.lower() == doi_safe.lower():
                return pdf

    # 2. Match by title similarity
    if title:
        best_score = 0.0
        best_file: Optional[Path] = None
        title_lower = title.lower()
        for pdf in pdf_files:
            stem = pdf.stem.replace("_", " ").replace("-", " ").lower()
            score = SequenceMatcher(None, title_lower, stem).ratio()
            if score > best_score:
                best_score = score
                best_file = pdf
        if best_score >= 0.6 and best_file is not None:
            log.info(
                "Matched local PDF '%s' to title '%s' (score=%.2f)",
                best_file.name, title, best_score,
            )
            return best_file

    return None


# ---------------------------------------------------------------------------
# Per-paper processing
# ---------------------------------------------------------------------------

def _make_doi_safe(doi: str) -> str:
    """Create a filesystem-safe version of a DOI for use as filename."""
    return doi.replace("/", "_").replace(":", "_")


def _process_paper(
    paper: Dict[str, Any],
    session: requests.Session,
    local_pdfs_dir: Optional[Path],
) -> Dict[str, Any]:
    """Fetch and parse full text for a single paper.

    Returns the output dict ready to be serialised as JSON.
    """
    doi = paper.get("doi", "")
    pmid = paper.get("pmid", "")
    pmcid = paper.get("pmcid", "")
    title = paper.get("title", "")
    abstract = paper.get("abstract", "")

    result: Dict[str, Any] = {
        "doi": doi,
        "pmid": pmid,
        "pmcid": pmcid,
        "title": title,
        "full_text_available": False,
        "source_type": "abstract_only",
        "sections": {
            "abstract": abstract,
            "introduction": "",
            "methods": "",
            "results": "",
            "discussion": "",
            "figures_tables": [],
        },
    }

    # ------------------------------------------------------------------
    # Strategy 1: PMC XML (highest fidelity)
    # ------------------------------------------------------------------
    if pmcid:
        log.info("Fetching PMC XML for %s (%s)", pmcid, doi or title[:60])
        xml_str = _fetch_pmc_xml(pmcid, session)
        if xml_str:
            sections = _parse_pmc_xml(xml_str)
            # Check we actually got meaningful content
            has_content = any(
                sections.get(k) for k in ("introduction", "methods", "results", "discussion")
            )
            if has_content:
                if sections["abstract"] == "" and abstract:
                    sections["abstract"] = abstract
                result["sections"] = sections
                result["full_text_available"] = True
                result["source_type"] = "pmc_xml"
                return result
            else:
                log.info("PMC XML for %s had no body sections, trying alternatives", pmcid)

    # ------------------------------------------------------------------
    # Strategy 2: bioRxiv / medRxiv PDF
    # ------------------------------------------------------------------
    if doi and doi.startswith("10.1101/"):
        log.info("Fetching bioRxiv PDF for %s", doi)
        pdf_bytes = _fetch_biorxiv_pdf(doi, session)
        if pdf_bytes:
            text = _pdf_to_text(pdf_bytes)
            if text:
                sections = _split_sections_heuristic(text)
                if abstract and not sections.get("abstract"):
                    sections["abstract"] = abstract
                sections.setdefault("figures_tables", [])
                result["sections"] = sections
                result["full_text_available"] = True
                result["source_type"] = "biorxiv_pdf"
                return result

    # ------------------------------------------------------------------
    # Strategy 3: Local PDF
    # ------------------------------------------------------------------
    if local_pdfs_dir:
        pdf_path = _find_local_pdf(doi, title, local_pdfs_dir)
        if pdf_path:
            log.info("Using local PDF: %s", pdf_path)
            try:
                pdf_bytes = pdf_path.read_bytes()
                text = _pdf_to_text(pdf_bytes)
                if text:
                    sections = _split_sections_heuristic(text)
                    if abstract and not sections.get("abstract"):
                        sections["abstract"] = abstract
                    sections.setdefault("figures_tables", [])
                    result["sections"] = sections
                    result["full_text_available"] = True
                    result["source_type"] = "local_pdf"
                    return result
            except Exception as exc:
                log.warning("Failed to read local PDF %s: %s", pdf_path, exc)

    # ------------------------------------------------------------------
    # Fallback: abstract only
    # ------------------------------------------------------------------
    log.info("No full text available for %s — using abstract only", doi or title[:60])
    return result


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def run(
    papers_path: str,
    output_dir: str,
    max_concurrent: int = 3,
    local_pdfs: Optional[str] = None,
) -> None:
    """Main entry point: load papers, fetch full texts, write outputs."""

    # Load input papers
    papers_file = Path(papers_path)
    if not papers_file.is_file():
        log.error("Papers file not found: %s", papers_path)
        sys.exit(1)

    with open(papers_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Accept either a list or a dict with a "papers" / "results" key
    if isinstance(data, list):
        papers: List[Dict[str, Any]] = data
    elif isinstance(data, dict):
        papers = data.get("papers", data.get("results", []))
    else:
        log.error("Unexpected JSON structure in %s", papers_path)
        sys.exit(1)

    if not papers:
        log.warning("No papers found in %s", papers_path)
        sys.exit(0)

    log.info("Loaded %d papers from %s", len(papers), papers_path)

    # Prepare output directory
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    local_pdfs_dir = Path(local_pdfs) if local_pdfs else None

    # Shared HTTP session
    session = requests.Session()
    session.headers.update({
        "User-Agent": "literature-knowledge-graph/1.0 (research; mailto:user@example.com)",
    })

    # Process papers concurrently (bounded by max_concurrent)
    summary_entries: list[Dict[str, Any]] = []
    succeeded = 0
    failed = 0

    def _worker(paper: Dict[str, Any]) -> Dict[str, Any]:
        return _process_paper(paper, session, local_pdfs_dir)

    with ThreadPoolExecutor(max_workers=max_concurrent) as pool:
        future_to_paper = {
            pool.submit(_worker, paper): paper for paper in papers
        }

        for future in as_completed(future_to_paper):
            paper = future_to_paper[future]
            doi = paper.get("doi", "")
            title = paper.get("title", "unknown")

            try:
                result = future.result()
            except Exception as exc:
                log.error("Unhandled error processing '%s': %s", title[:80], exc)
                failed += 1
                summary_entries.append({
                    "doi": doi,
                    "title": title,
                    "full_text_available": False,
                    "source_type": "error",
                    "error": str(exc),
                })
                continue

            # Write per-paper JSON
            if doi:
                fname = _make_doi_safe(doi) + ".json"
            else:
                # fallback: use sanitised title
                safe_title = re.sub(r"[^a-zA-Z0-9]+", "_", title)[:80]
                fname = safe_title + ".json"

            out_file = out_path / fname
            try:
                with open(out_file, "w", encoding="utf-8") as fout:
                    json.dump(result, fout, indent=2, ensure_ascii=False)
                log.info(
                    "Saved %s  [%s, fulltext=%s]",
                    out_file.name,
                    result["source_type"],
                    result["full_text_available"],
                )
                succeeded += 1
            except OSError as exc:
                log.error("Failed to write %s: %s", out_file, exc)
                failed += 1

            summary_entries.append({
                "doi": result.get("doi", ""),
                "pmid": result.get("pmid", ""),
                "pmcid": result.get("pmcid", ""),
                "title": result.get("title", ""),
                "full_text_available": result.get("full_text_available", False),
                "source_type": result.get("source_type", ""),
                "output_file": fname,
            })

    # Write summary manifest
    summary = {
        "total_papers": len(papers),
        "full_text_available": sum(
            1 for e in summary_entries if e.get("full_text_available")
        ),
        "abstract_only": sum(
            1 for e in summary_entries if not e.get("full_text_available")
        ),
        "succeeded": succeeded,
        "failed": failed,
        "papers": summary_entries,
    }

    summary_file = out_path / "fulltext_summary.json"
    with open(summary_file, "w", encoding="utf-8") as fout:
        json.dump(summary, fout, indent=2, ensure_ascii=False)
    log.info("Summary written to %s", summary_file)

    log.info(
        "Done. %d succeeded, %d failed, %d/%d with full text.",
        succeeded,
        failed,
        summary["full_text_available"],
        len(papers),
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch full text of scientific papers and parse into structured sections.",
    )
    parser.add_argument(
        "--papers",
        required=True,
        help="Path to JSON file with paper metadata (output from search_literature.py).",
    )
    parser.add_argument(
        "--output-dir",
        default="./fulltext/",
        help="Directory to save per-paper fulltext JSONs (default: ./fulltext/).",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=3,
        help="Maximum number of concurrent downloads (default: 3).",
    )
    parser.add_argument(
        "--local-pdfs",
        default=None,
        help="Optional directory containing user-provided PDFs (matched by DOI in filename).",
    )

    args = parser.parse_args()

    run(
        papers_path=args.papers,
        output_dir=args.output_dir,
        max_concurrent=args.max_concurrent,
        local_pdfs=args.local_pdfs,
    )


if __name__ == "__main__":
    main()
