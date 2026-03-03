"""Paper metadata enrichment via PubMed E-utilities.

Normalizes paper_list.json and fetches missing metadata (PMID, abstract,
authors, MeSH terms) from NCBI APIs. Includes DOI validation and correction.
"""

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

# Add wf-audit/scripts to path for shared doi_validator
_AUDIT_SCRIPTS = Path.home() / ".claude/skills/wf-audit/scripts"
if str(_AUDIT_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_AUDIT_SCRIPTS))

try:
    from doi_validator import validate_and_correct_doi, normalize_doi, is_valid_doi_format
    _HAS_DOI_VALIDATOR = True
except ImportError:
    _HAS_DOI_VALIDATOR = False


# NCBI rate limit: max 3 requests/sec without API key, 10 rps with key
_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
_REQUEST_DELAY = 0.15 if _NCBI_API_KEY else 0.4  # seconds between requests

_NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_ID_CONVERTER = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"

_USER_AGENT = "wf-migrate/2.3 (purpose: academic-workflow-enrichment)"

if not _NCBI_API_KEY:
    print("[WARN] No NCBI_API_KEY set. Rate limit: 3 req/sec. "
          "Get one at https://www.ncbi.nlm.nih.gov/account/settings/",
          file=sys.stderr, flush=True)

# Europe PMC batch limit per run (policy: no bulk automated downloads)
_EUROPEPMC_BATCH_LIMIT = 50
_europepmc_batch_count = 0


# ---------------------------------------------------------------------------
# Paper list normalization
# ---------------------------------------------------------------------------

def normalize_paper_list(paper_data: dict | list) -> dict:
    """Normalize paper_list to canonical format with paper_id on every entry.

    Handles:
    - Flat list → wrap in {"papers": [...]}
    - Missing paper_id → auto-generate from "id" field or index
    - Missing "papers" key → detect list at top level

    Returns {"workflow_id": ..., "papers": [...]}.
    """
    if isinstance(paper_data, list):
        papers = paper_data
        wrapper = {"papers": papers}
    elif isinstance(paper_data, dict):
        papers = paper_data.get("papers", [])
        wrapper = dict(paper_data)
        wrapper["papers"] = papers
    else:
        return {"papers": []}

    for i, p in enumerate(papers):
        # Ensure paper_id exists
        if "paper_id" not in p:
            if "id" in p:
                p["paper_id"] = p["id"]
            else:
                p["paper_id"] = f"P{i+1:03d}"

        # Ensure core fields exist with defaults
        p.setdefault("pmid", "")
        p.setdefault("doi", "")
        p.setdefault("authors", p.get("authors", []))
        p.setdefault("year", "")
        p.setdefault("journal", "")
        p.setdefault("title", "")
        p.setdefault("abstract", "")

    return wrapper


# ---------------------------------------------------------------------------
# NCBI API helpers
# ---------------------------------------------------------------------------

def _ncbi_url(url: str) -> str:
    """Append NCBI API key to URL if available."""
    if _NCBI_API_KEY and "ncbi.nlm.nih.gov" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={_NCBI_API_KEY}"
    return url


def _http_get(url: str, timeout: int = 15, max_retries: int = 3) -> str:
    """HTTP GET with adaptive retry on 429/network errors. Returns '' on failure.

    Uses socket-level timeout to prevent TCP SYN-SENT hangs (OS default ~2min).
    Handles 403/503 as server block signals.
    """
    url = _ncbi_url(url)
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)  # TCP-level timeout 보장
    try:
        for attempt in range(max_retries):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return resp.read().decode("utf-8")
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = min(2 ** attempt * 2, 30)  # 2s, 4s, 8s... max 30s
                    print(f"  [429] Rate limited, waiting {wait}s (attempt {attempt+1}/{max_retries})...", flush=True)
                    time.sleep(wait)
                    continue
                if e.code in (403, 503):
                    print(f"  [{e.code}] Server blocked/unavailable, skipping", flush=True)
                    return ""
                return ""
            except (urllib.error.URLError, OSError, TimeoutError, socket.timeout):
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # backoff on connection failure
                    continue
                return ""
        return ""
    finally:
        socket.setdefaulttimeout(old_timeout)


def resolve_pmid_from_doi(doi: str) -> dict:
    """Resolve a DOI to PubMed ID and PMC ID using NCBI ID Converter API.

    Returns {"pmid": "...", "pmcid": "PMC..."} with empty strings if not found.
    """
    result = {"pmid": "", "pmcid": ""}
    if not doi:
        return result

    # Clean DOI
    doi = doi.strip()
    if doi.startswith("http"):
        doi = re.sub(r"https?://doi\.org/", "", doi)

    url = f"{_NCBI_ID_CONVERTER}?ids={urllib.parse.quote(doi)}&format=json"
    text = _http_get(url)
    if not text:
        return result

    try:
        data = json.loads(text)
        records = data.get("records", [])
        if records:
            result["pmid"] = records[0].get("pmid", "")
            result["pmcid"] = records[0].get("pmcid", "")
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    return result


def fetch_pubmed_details(pmid: str) -> dict:
    """Fetch paper details from PubMed E-utilities (efetch).

    Returns dict with: title, authors, journal, year, abstract, mesh_terms, doi.
    Returns empty dict on failure.
    """
    if not pmid:
        return {}

    url = (f"{_NCBI_EUTILS_BASE}/efetch.fcgi?"
           f"db=pubmed&id={pmid}&rettype=xml&retmode=xml")
    xml_text = _http_get(url)
    if not xml_text:
        return {}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    article = root.find(".//PubmedArticle")
    if article is None:
        return {}

    result = {}

    # Title
    title_el = article.find(".//ArticleTitle")
    if title_el is not None and title_el.text:
        result["title"] = title_el.text.strip()

    # Authors
    author_list = article.findall(".//Author")
    authors = []
    for a in author_list:
        last = a.findtext("LastName", "")
        initials = a.findtext("Initials", "")
        if last:
            authors.append(f"{last} {initials}".strip())
    if authors:
        result["authors"] = authors

    # Journal
    journal_el = article.find(".//Journal/Title")
    if journal_el is not None and journal_el.text:
        result["journal"] = journal_el.text.strip()

    # Year
    year_el = article.find(".//PubDate/Year")
    if year_el is not None and year_el.text:
        try:
            result["year"] = int(year_el.text)
        except ValueError:
            result["year"] = year_el.text

    # Abstract
    abstract_parts = article.findall(".//AbstractText")
    if abstract_parts:
        abstract_text = " ".join(
            (a.text or "") for a in abstract_parts
        ).strip()
        if abstract_text:
            result["abstract"] = abstract_text

    # MeSH terms
    mesh_headings = article.findall(".//MeshHeading/DescriptorName")
    if mesh_headings:
        result["mesh_terms"] = [
            m.text for m in mesh_headings if m.text
        ]

    # DOI from article IDs
    for aid in article.findall(".//ArticleId"):
        if aid.get("IdType") == "doi" and aid.text:
            result["doi"] = aid.text.strip()
            break

    return result


def search_pmid_by_title(title: str) -> str:
    """Search PubMed by title to find PMID when DOI lookup fails.

    Returns PMID string or '' if not found.
    """
    if not title:
        return ""

    query = urllib.parse.quote(f"{title}[Title]")
    url = f"{_NCBI_EUTILS_BASE}/esearch.fcgi?db=pubmed&term={query}&retmax=1&retmode=json"
    text = _http_get(url)
    if not text:
        return ""

    try:
        data = json.loads(text)
        id_list = data.get("esearchresult", {}).get("idlist", [])
        if id_list:
            return id_list[0]
    except (json.JSONDecodeError, KeyError, IndexError):
        pass

    return ""


# ---------------------------------------------------------------------------
# PMC full text retrieval
# ---------------------------------------------------------------------------

_MAX_FULLTEXT_CHARS = 300_000

_SECTION_MAP = {
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

_ORDERED_SECTIONS = ["ABSTRACT", "INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION"]


def _xml_element_to_text(element: ET.Element) -> str:
    """Recursively extract plain text from an XML element."""
    return " ".join(element.itertext()).strip()


def _parse_pmc_sections(root: ET.Element) -> dict[str, str]:
    """Parse PMC XML into section-name -> text mapping (all sections)."""
    sections: dict[str, str] = {}

    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        text = _xml_element_to_text(abstract_el)
        if text.strip():
            sections["ABSTRACT"] = text.strip()

    for sec in root.findall(".//body/sec"):
        sec_type = (sec.get("sec-type") or "").lower()
        title_el = sec.find("title")
        title_text = (title_el.text or "").lower() if title_el is not None else ""

        section_name = None
        for key, name in _SECTION_MAP.items():
            if key in sec_type or key in title_text:
                section_name = name
                break

        if section_name is None:
            if title_el is not None and title_el.text:
                section_name = title_el.text.strip().upper()
            else:
                continue

        text = _xml_element_to_text(sec)
        if text.strip():
            if section_name in sections:
                sections[section_name] += "\n" + text.strip()
            else:
                sections[section_name] = text.strip()

    return sections


def _sections_to_structured_text(sections: dict[str, str]) -> str:
    """Convert section dict to structured text with === SECTION === headers."""
    lines: list[str] = []
    for key in _ORDERED_SECTIONS:
        if key in sections:
            lines.append(f"=== {key} ===")
            lines.append(sections[key][:_MAX_FULLTEXT_CHARS])
            lines.append("")
    for key in sorted(sections.keys()):
        if key not in _ORDERED_SECTIONS:
            lines.append(f"=== {key} ===")
            lines.append(sections[key][:_MAX_FULLTEXT_CHARS])
            lines.append("")
    return "\n".join(lines)


def fetch_pmc_fulltext(pmcid: str) -> str | None:
    """Fetch full text from PMC Open Access via efetch API.

    Extracts ALL sections (Abstract, Introduction, Methods, Results, Discussion)
    as structured text with === SECTION === headers.
    Falls back to full <body> text if section parsing yields nothing.

    Returns structured plain text or None on failure.
    """
    if not pmcid:
        return None

    numeric_id = pmcid.replace("PMC", "")
    url = (f"{_NCBI_EUTILS_BASE}/efetch.fcgi?"
           f"db=pmc&id={numeric_id}&rettype=xml&retmode=xml")
    xml_text = _http_get(url, timeout=30)
    if not xml_text:
        return None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    sections = _parse_pmc_sections(root)
    if sections:
        return _sections_to_structured_text(sections)

    body = root.find(".//body")
    if body is not None:
        text = _xml_element_to_text(body)
        if text and len(text) > 200:
            return text[:_MAX_FULLTEXT_CHARS]

    return None


def fetch_europepmc_fulltext(pmcid: str) -> str | None:
    """Fetch full text from Europe PMC REST API (fallback for PMC OA).

    Limited to _EUROPEPMC_BATCH_LIMIT calls per run to comply with
    Europe PMC's policy against bulk automated downloads.

    Returns structured plain text or None on failure.
    """
    global _europepmc_batch_count
    if not pmcid:
        return None
    if _europepmc_batch_count >= _EUROPEPMC_BATCH_LIMIT:
        return None
    _europepmc_batch_count += 1

    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    xml_text = _http_get(url, timeout=30)
    if not xml_text:
        return None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    sections = _parse_pmc_sections(root)
    if sections:
        return _sections_to_structured_text(sections)

    body = root.find(".//body")
    if body is not None:
        text = _xml_element_to_text(body)
        if text and len(text) > 200:
            return text[:_MAX_FULLTEXT_CHARS]

    return None


def validate_pmid_title_match(pmid: str, expected_title: str) -> bool:
    """Cross-validate PMID by comparing PubMed title with expected title.

    Returns True if titles match (cosine similarity >= 0.3), False otherwise.
    """
    if not pmid:
        return True  # no PMID to validate
    if not expected_title:
        return False  # cannot verify without title — reject merge to be safe
    details = fetch_pubmed_details(pmid)
    if not details or "title" not in details:
        return True  # can't validate, assume ok
    pubmed_title = details["title"]

    import math
    from collections import Counter

    def _tok(t: str) -> list[str]:
        stops = {"a","an","the","and","or","in","on","at","to","for","of","with","by","from","is","are","was","were"}
        return [w for w in re.findall(r"[a-z0-9]+", t.lower()) if w not in stops and len(w) > 2]

    ta, tb = _tok(expected_title), _tok(pubmed_title)
    if not ta or not tb:
        return True
    ca, cb = Counter(ta), Counter(tb)
    keys = set(ca) | set(cb)
    dot = sum(ca.get(k,0) * cb.get(k,0) for k in keys)
    ma = math.sqrt(sum(v*v for v in ca.values()))
    mb = math.sqrt(sum(v*v for v in cb.values()))
    sim = dot / (ma * mb) if ma and mb else 0.0
    if sim < 0.3:
        print(f"  [WARN] PMID {pmid} title mismatch (sim={sim:.3f}): "
              f"expected='{expected_title[:60]}' vs pubmed='{pubmed_title[:60]}'",
              file=sys.stderr, flush=True)
        return False
    return True


# ---------------------------------------------------------------------------
# Paper list enrichment (main entry point)
# ---------------------------------------------------------------------------

def enrich_paper_list(paper_data: dict | list, rate_delay: float = _REQUEST_DELAY) -> dict:
    """Enrich all papers in paper_list with PubMed metadata.

    For each paper:
    1. If no PMID: resolve from DOI via NCBI ID Converter
    2. If still no PMID: search PubMed by title
    3. Fetch PubMed details (abstract, MeSH, full author list)
    4. Merge fetched data (preserving existing non-empty values)

    Args:
        paper_data: raw paper_list data (list or dict)
        rate_delay: seconds between API calls (default 0.4s)

    Returns:
        Normalized paper_list dict with enriched papers.
        Each paper gets an "enrichment_status" field: "enriched", "partial", or "failed".
    """
    normalized = normalize_paper_list(paper_data)
    papers = normalized.get("papers", [])

    consecutive_failures = 0
    total_adaptive_pauses = 0
    max_adaptive_pauses = 3  # Circuit breaker: skip remaining after 3 pause cycles
    adaptive_delay = rate_delay
    skipped_count = 0

    for paper in papers:
        # Idempotency: skip already-enriched papers (PMID + substantial abstract)
        if (paper.get("pmid") and paper.get("abstract")
                and len(paper.get("abstract", "")) > 50):
            if paper.get("enrichment_status") != "failed":
                skipped_count += 1
                continue

        pmid = str(paper.get("pmid", "")).strip()
        pmcid = str(paper.get("pmcid", "")).strip()
        doi = str(paper.get("doi", "")).strip()
        title = str(paper.get("title", "")).strip()

        # api_failure tracks actual network/server errors, NOT "paper not found"
        api_failure = False

        # Step 1: Resolve PMID + PMCID from DOI if missing
        if not pmid and doi:
            id_result = resolve_pmid_from_doi(doi)
            pmid = id_result.get("pmid", "")
            if pmid and title:
                if not validate_pmid_title_match(pmid, title):
                    paper["pmid_title_mismatch"] = True
                    print(f"  [REJECT-PMID] {paper.get('paper_id', '?')}: "
                          f"DOI→PMID {pmid} title mismatch, discarding resolved PMID",
                          file=sys.stderr, flush=True)
                    pmid = ""
            if pmid:
                paper["pmid"] = pmid
            if not pmcid and id_result.get("pmcid"):
                pmcid = id_result["pmcid"]
                paper["pmcid"] = pmcid
            time.sleep(adaptive_delay)

        # Step 2: Search by title if still no PMID
        if not pmid and title:
            pmid = search_pmid_by_title(title)
            if pmid:
                if not validate_pmid_title_match(pmid, title):
                    print(f"  [REJECT-PMID] {paper.get('paper_id', '?')}: "
                          f"title-search PMID {pmid} mismatch, discarding",
                          file=sys.stderr, flush=True)
                    pmid = ""
                else:
                    paper["pmid"] = pmid
            time.sleep(adaptive_delay)

        # Step 3: Fetch PubMed details
        if pmid:
            details = fetch_pubmed_details(pmid)
            time.sleep(adaptive_delay)

            if details:
                # Step 3.1: Cross-validate PMID → title before merging
                if title and details.get("title"):
                    if not validate_pmid_title_match(pmid, title):
                        paper["pmid_title_mismatch"] = True
                        print(f"  [SKIP-MERGE] {paper.get('paper_id', '?')}: "
                              f"PMID {pmid} title mismatch, skipping metadata merge",
                              file=sys.stderr, flush=True)
                        paper["enrichment_status"] = "partial"
                        continue

                # Merge: only fill in missing/empty fields
                for key, value in details.items():
                    existing = paper.get(key)
                    if not existing or (isinstance(existing, str) and not existing.strip()):
                        paper[key] = value

                paper["enrichment_status"] = "enriched"
            else:
                paper["enrichment_status"] = "partial"
                api_failure = True
        else:
            paper["enrichment_status"] = "failed"

        # Step 4: Fetch PMC full text (if PMCID available)
        if pmcid:
            text_source = "abstract_only"
            full_text = fetch_pmc_fulltext(pmcid)
            time.sleep(adaptive_delay)

            if full_text:
                text_source = "pmc_oa"
            else:
                full_text = fetch_europepmc_fulltext(pmcid)
                time.sleep(adaptive_delay)
                if full_text:
                    text_source = "europepmc"

            if full_text:
                paper["has_full_text"] = True
                paper["_full_text_pending"] = full_text
            paper["text_source"] = text_source
        else:
            paper["text_source"] = "abstract_only"

        # Adaptive rate limiting: only track actual API/network failures
        if api_failure:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                total_adaptive_pauses += 1
                if total_adaptive_pauses > max_adaptive_pauses:
                    print(f"  [CIRCUIT-BREAK] {max_adaptive_pauses} adaptive pauses reached, skipping remaining papers", flush=True)
                    break
                print(f"  [ADAPTIVE] 3+ consecutive failures, pausing 60s... (cycle {total_adaptive_pauses}/{max_adaptive_pauses})", flush=True)
                time.sleep(60)
                # Connectivity check
                test = _http_get(
                    f"{_NCBI_EUTILS_BASE}/esearch.fcgi?db=pubmed&term=test&retmax=1",
                    timeout=10, max_retries=1)
                if not test:
                    print("  [BLOCKED] NCBI unreachable, skipping remaining papers", flush=True)
                    break
                consecutive_failures = 0
                adaptive_delay = min(adaptive_delay * 2, 3.0)
        else:
            consecutive_failures = 0
            adaptive_delay = max(adaptive_delay * 0.9, rate_delay)

    if skipped_count:
        print(f"  [SKIP] {skipped_count} already-enriched papers skipped", flush=True)

    # Step 5: DOI validation and correction (post-enrichment)
    if _HAS_DOI_VALIDATOR:
        doi_stats = {"validated": 0, "corrected": 0, "invalid": 0}
        for paper in papers:
            doi = str(paper.get("doi", "")).strip()
            if not doi or doi.upper() in ("N/A", "NONE"):
                continue

            # Normalize DOI format (strip URL prefix)
            normalized_doi = normalize_doi(doi)
            if normalized_doi != doi:
                paper["doi"] = normalized_doi

            # Validate and attempt correction
            result = validate_and_correct_doi(paper, rate_delay=rate_delay)
            doi_stats["validated"] += 1
            if result["status"] == "corrected":
                doi_stats["corrected"] += 1
            elif result["status"] in ("invalid_format", "unresolvable"):
                doi_stats["invalid"] += 1
                paper["doi_validation"] = result["status"]

        normalized["doi_validation_stats"] = doi_stats

    return normalized


def save_paper_fulltext(wf_dir: Path, paper_id: str, text: str) -> Path:
    """Save paper text (abstract or full text) to full_texts/ directory.

    Args:
        wf_dir: workflow directory
        paper_id: e.g. "P001"
        text: text content to save

    Returns:
        Path to saved file.
    """
    ft_dir = wf_dir / "01_papers" / "full_texts"
    ft_dir.mkdir(parents=True, exist_ok=True)

    out_path = ft_dir / f"{paper_id}.txt"
    out_path.write_text(text, encoding="utf-8")
    return out_path


def save_enriched_paper_list(wf_dir: Path, paper_data: dict) -> Path:
    """Write enriched paper_list.json back to the workflow directory.

    Tries 01_papers/ first, then 01_literature/.
    """
    for subdir in ("01_papers", "01_literature"):
        candidate = wf_dir / subdir / "paper_list.json"
        if candidate.parent.exists():
            with open(candidate, "w", encoding="utf-8") as f:
                json.dump(paper_data, f, indent=2, ensure_ascii=False)
            return candidate

    # Fallback: create 01_papers/
    out_dir = wf_dir / "01_papers"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "paper_list.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(paper_data, f, indent=2, ensure_ascii=False)
    return out_path
