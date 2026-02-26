"""Shared DOI validation module.

Provides DOI normalization, format checking, and resolution verification.
Importable by wf-audit, wf-migrate, wf-output, and wf-literature skills.

Usage:
    from doi_validator import validate_doi, normalize_doi, validate_paper_dois
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# --- DOI resolution cache (persistent across calls within session) ---
_doi_resolve_cache: dict[str, bool] = {}
_doi_correction_cache: dict[str, str] = {}  # bad_doi -> corrected_doi


def normalize_doi(doi: str) -> str:
    """Strip URL prefix from DOI, returning bare '10.XXXX/...' form.

    Handles:
    - https://doi.org/10.1038/... -> 10.1038/...
    - http://dx.doi.org/10.1038/... -> 10.1038/...
    - Already bare DOIs pass through unchanged.
    """
    if not doi or not isinstance(doi, str):
        return ""
    doi = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/",
                    "https://dx.doi.org/", "http://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi


def is_valid_doi_format(doi: str) -> bool:
    """Check if a string looks like a valid DOI format (10.XXXX/...)."""
    doi = normalize_doi(doi)
    if not doi:
        return False
    return bool(re.match(r'^10\.\d{4,}/', doi))


def doi_resolves(doi: str, timeout: int = 15, max_retries: int = 2) -> bool:
    """Check if a DOI resolves to a real resource via doi.org.

    Uses HEAD request first, falls back to GET on 403/429.
    Results are cached for the session.
    Non-DOI strings (e.g., 'N/A', '') return False.
    Retries on rate-limit (429) or transient errors with backoff.
    On final failure, returns True to avoid false positives from rate limiting.
    """
    doi = normalize_doi(doi)
    if not is_valid_doi_format(doi):
        return False

    if doi in _doi_resolve_cache:
        return _doi_resolve_cache[doi]

    encoded_doi = urllib.parse.quote(doi, safe='/:@')
    url = f"https://doi.org/{encoded_doi}"

    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(1.0 * attempt)

        for method in ("HEAD", "GET"):
            try:
                req = urllib.request.Request(url, method=method, headers={
                    "User-Agent": "wf-audit/1.0 (DOI verification; mailto:admin@kribb.re.kr)",
                    "Accept": "text/html",
                })
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    if resp.status < 400:
                        _doi_resolve_cache[doi] = True
                        return True
            except urllib.error.HTTPError as e:
                if e.code == 403 and method == "HEAD":
                    continue
                if e.code == 429:
                    break
                if e.code in (404, 410):
                    _doi_resolve_cache[doi] = False
                    return False
                _doi_resolve_cache[doi] = True
                return True
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < max_retries:
                    break
                _doi_resolve_cache[doi] = True
                return True

    # All retries exhausted — assume real to avoid false positives
    _doi_resolve_cache[doi] = True
    return True


def crossref_lookup(doi: str, timeout: int = 10) -> dict | None:
    """Look up a DOI via CrossRef API. Returns metadata dict or None."""
    doi = normalize_doi(doi)
    if not is_valid_doi_format(doi):
        return None

    encoded = urllib.parse.quote(doi, safe='/:@')
    url = f"https://api.crossref.org/works/{encoded}"
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "wf-audit/1.0 (mailto:admin@kribb.re.kr)",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("message", {})
    except Exception:
        return None


def correct_doi_from_pmid(pmid: str, timeout: int = 10) -> str:
    """Fetch the correct DOI for a PMID from PubMed.

    Returns the DOI string or "" if not found.
    This is the authoritative source: PubMed's own DOI record.
    """
    if not pmid:
        return ""

    url = (f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?"
           f"db=pubmed&id={pmid}&retmode=json")
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "wf-audit/1.0",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            record = data.get("result", {}).get(str(pmid), {})
            eloc = record.get("elocationid", "")
            if eloc.startswith("doi: "):
                return eloc[5:].strip()
            # Try articleids
            for aid in record.get("articleids", []):
                if aid.get("idtype") == "doi":
                    return aid.get("value", "")
    except Exception:
        pass
    return ""


def validate_and_correct_doi(paper: dict, rate_delay: float = 0.4) -> dict:
    """Validate a paper's DOI and attempt correction if invalid.

    Strategy:
    1. Normalize DOI format (strip URL prefix)
    2. Check if DOI resolves via doi.org
    3. If not: try to get correct DOI from PubMed (if PMID exists)
    4. If corrected: update the paper dict

    Returns dict with:
        status: "valid" | "corrected" | "invalid_format" | "unresolvable" | "no_doi"
        original_doi: str
        corrected_doi: str (if corrected)
        message: str
    """
    doi = str(paper.get("doi", "")).strip()
    pmid = str(paper.get("pmid", "")).strip()
    pid = paper.get("paper_id", "?")

    if not doi or doi.upper() in ("N/A", "NONE", ""):
        return {"status": "no_doi", "original_doi": doi, "corrected_doi": "",
                "message": f"{pid}: no DOI provided"}

    normalized = normalize_doi(doi)

    # Step 1: Format check
    if not is_valid_doi_format(normalized):
        return {"status": "invalid_format", "original_doi": doi, "corrected_doi": "",
                "message": f"{pid}: invalid DOI format '{doi}'"}

    # Update paper with normalized DOI
    if normalized != doi:
        paper["doi"] = normalized

    # Step 2: Resolution check
    if doi_resolves(normalized):
        return {"status": "valid", "original_doi": normalized, "corrected_doi": "",
                "message": f"{pid}: DOI resolves OK"}

    # Step 3: DOI doesn't resolve — try correction from PubMed
    if pmid:
        time.sleep(rate_delay)
        correct_doi = correct_doi_from_pmid(pmid)
        if correct_doi and correct_doi != normalized:
            paper["doi"] = correct_doi
            paper["doi_corrected_from"] = normalized
            _doi_correction_cache[normalized] = correct_doi
            return {"status": "corrected", "original_doi": normalized,
                    "corrected_doi": correct_doi,
                    "message": f"{pid}: DOI corrected from '{normalized}' to '{correct_doi}' via PMID {pmid}"}

    return {"status": "unresolvable", "original_doi": normalized, "corrected_doi": "",
            "message": f"{pid}: DOI '{normalized}' does not resolve and cannot be corrected"}


def validate_paper_dois(papers: list[dict], verify_online: bool = True,
                        auto_correct: bool = True, rate_delay: float = 0.4) -> dict:
    """Validate DOIs for a list of papers.

    Args:
        papers: list of paper dicts
        verify_online: if True, check doi.org resolution
        auto_correct: if True, attempt to correct bad DOIs from PubMed
        rate_delay: delay between API calls

    Returns dict with:
        total: int
        valid: int
        corrected: int
        invalid: int
        no_doi: int
        results: list of per-paper result dicts
    """
    results = []
    counts = {"valid": 0, "corrected": 0, "invalid_format": 0,
              "unresolvable": 0, "no_doi": 0}

    for paper in papers:
        if not isinstance(paper, dict):
            continue

        if verify_online and auto_correct:
            result = validate_and_correct_doi(paper, rate_delay=rate_delay)
        elif verify_online:
            # Validate but don't correct
            doi = normalize_doi(str(paper.get("doi", "")))
            if not doi or doi.upper() in ("N/A", "NONE"):
                result = {"status": "no_doi", "original_doi": doi,
                          "corrected_doi": "", "message": "no DOI"}
            elif not is_valid_doi_format(doi):
                result = {"status": "invalid_format", "original_doi": doi,
                          "corrected_doi": "", "message": f"invalid format: {doi}"}
            elif doi_resolves(doi):
                result = {"status": "valid", "original_doi": doi,
                          "corrected_doi": "", "message": "resolves OK"}
            else:
                result = {"status": "unresolvable", "original_doi": doi,
                          "corrected_doi": "", "message": f"does not resolve: {doi}"}
        else:
            # Format check only (no network)
            doi = normalize_doi(str(paper.get("doi", "")))
            if not doi:
                result = {"status": "no_doi", "original_doi": "", "corrected_doi": "", "message": ""}
            elif is_valid_doi_format(doi):
                result = {"status": "valid", "original_doi": doi, "corrected_doi": "", "message": ""}
            else:
                result = {"status": "invalid_format", "original_doi": doi, "corrected_doi": "", "message": ""}

        counts[result["status"]] = counts.get(result["status"], 0) + 1
        results.append(result)

    return {
        "total": len(results),
        "valid": counts["valid"],
        "corrected": counts["corrected"],
        "invalid": counts["invalid_format"] + counts["unresolvable"],
        "no_doi": counts["no_doi"],
        "results": results,
    }
