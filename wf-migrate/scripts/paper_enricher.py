"""Paper metadata enrichment via PubMed E-utilities.

Normalizes paper_list.json and fetches missing metadata (PMID, abstract,
authors, MeSH terms) from NCBI APIs. Includes DOI validation and correction.
"""

import json
import os
import re
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

_USER_AGENT = "wf-migrate/2.2 (purpose: academic-workflow-enrichment)"

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
    """HTTP GET with adaptive retry on 429. Returns '' on failure."""
    url = _ncbi_url(url)
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
            return ""
        except (urllib.error.URLError, OSError, TimeoutError):
            return ""
    return ""


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

_MAX_FULLTEXT_CHARS = 200_000  # ~50k words; cap to protect memory


def fetch_pmc_fulltext(pmcid: str) -> str | None:
    """Fetch full text from PMC Open Access via efetch API.

    Prioritizes Methods/Materials and Methods sections.
    Falls back to full <body> text.

    Returns plain text or None on failure.
    """
    if not pmcid:
        return None

    # Strip "PMC" prefix for efetch if present
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

    # Try to extract Methods section first
    methods_text = _extract_sections_from_pmc_xml(root, [
        "methods", "materials and methods", "materials & methods",
        "experimental", "experimental procedures", "experimental section",
    ])
    if methods_text and len(methods_text) > 200:
        return methods_text[:_MAX_FULLTEXT_CHARS]

    # Fallback: extract full body text
    body = root.find(".//body")
    if body is not None:
        text = _xml_element_to_text(body)
        if text and len(text) > 200:
            return text[:_MAX_FULLTEXT_CHARS]

    return None


def _extract_sections_from_pmc_xml(root: ET.Element, section_titles: list[str]) -> str:
    """Extract specific sections from PMC XML by sec-type or title match."""
    parts = []

    for sec in root.iter("sec"):
        # Check sec-type attribute
        sec_type = (sec.get("sec-type") or "").lower()
        if sec_type in section_titles:
            parts.append(_xml_element_to_text(sec))
            continue

        # Check <title> element text
        title_el = sec.find("title")
        if title_el is not None and title_el.text:
            title_text = title_el.text.strip().lower()
            if any(st in title_text for st in section_titles):
                parts.append(_xml_element_to_text(sec))

    return "\n\n".join(parts)


def _xml_element_to_text(element: ET.Element) -> str:
    """Recursively extract plain text from an XML element."""
    return " ".join(element.itertext()).strip()


def fetch_europepmc_fulltext(pmcid: str) -> str | None:
    """Fetch full text from Europe PMC REST API (fallback for PMC OA).

    Limited to _EUROPEPMC_BATCH_LIMIT calls per run to comply with
    Europe PMC's policy against bulk automated downloads.

    Returns plain text or None on failure.
    """
    global _europepmc_batch_count
    if not pmcid:
        return None
    if _europepmc_batch_count >= _EUROPEPMC_BATCH_LIMIT:
        return None  # batch limit reached
    _europepmc_batch_count += 1

    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    xml_text = _http_get(url, timeout=30)
    if not xml_text:
        return None

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    # Try Methods first
    methods_text = _extract_sections_from_pmc_xml(root, [
        "methods", "materials and methods", "materials & methods",
        "experimental", "experimental procedures",
    ])
    if methods_text and len(methods_text) > 200:
        return methods_text[:_MAX_FULLTEXT_CHARS]

    # Fallback: full body
    body = root.find(".//body")
    if body is not None:
        text = _xml_element_to_text(body)
        if text and len(text) > 200:
            return text[:_MAX_FULLTEXT_CHARS]

    return None


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

    for paper in papers:
        pmid = str(paper.get("pmid", "")).strip()
        pmcid = str(paper.get("pmcid", "")).strip()
        doi = str(paper.get("doi", "")).strip()
        title = str(paper.get("title", "")).strip()

        # Step 1: Resolve PMID + PMCID from DOI if missing
        if not pmid and doi:
            id_result = resolve_pmid_from_doi(doi)
            pmid = id_result.get("pmid", "")
            if pmid:
                paper["pmid"] = pmid
            if not pmcid and id_result.get("pmcid"):
                pmcid = id_result["pmcid"]
                paper["pmcid"] = pmcid
            time.sleep(rate_delay)

        # Step 2: Search by title if still no PMID
        if not pmid and title:
            pmid = search_pmid_by_title(title)
            if pmid:
                paper["pmid"] = pmid
            time.sleep(rate_delay)

        # Step 3: Fetch PubMed details
        if pmid:
            details = fetch_pubmed_details(pmid)
            time.sleep(rate_delay)

            if details:
                # Merge: only fill in missing/empty fields
                for key, value in details.items():
                    existing = paper.get(key)
                    if not existing or (isinstance(existing, str) and not existing.strip()):
                        paper[key] = value

                paper["enrichment_status"] = "enriched"
            else:
                paper["enrichment_status"] = "partial"
        else:
            paper["enrichment_status"] = "failed"

        # Step 4: Fetch PMC full text (if PMCID available)
        if pmcid:
            text_source = "abstract_only"
            full_text = fetch_pmc_fulltext(pmcid)
            time.sleep(rate_delay)

            if full_text:
                text_source = "pmc_oa"
            else:
                full_text = fetch_europepmc_fulltext(pmcid)
                time.sleep(rate_delay)
                if full_text:
                    text_source = "europepmc"

            if full_text:
                paper["full_text"] = full_text
            paper["text_source"] = text_source
        else:
            paper["text_source"] = "abstract_only"

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
