"""Paper data validation with Pydantic v2 models and content cross-checking.

Validates paper_list.json schema conformance, checks title-abstract
keyword relevance, verifies full text file consistency, and optionally
cross-validates PMID-title mapping against PubMed.

Severity levels:
  - critical: abstract-title complete mismatch, PMID-title mismatch (auto-reject)
  - warning: short full text, missing abstract (proceed with logging)
  - info: informational notes
"""

from __future__ import annotations

import json
import math
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Optional
from xml.etree import ElementTree as ET

try:
    from pydantic import BaseModel, Field, model_validator
    _HAS_PYDANTIC = True
except ImportError:
    _HAS_PYDANTIC = False
    BaseModel = object  # type: ignore[misc,assignment]

_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
_NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_USER_AGENT = "wf-literature/3.0 (purpose: validate-papers)"
_REQUEST_DELAY = 0.15 if _NCBI_API_KEY else 0.4

STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "we", "our", "their", "than", "as",
    "not", "no", "nor", "so", "if", "then", "into", "up", "out", "about",
    "after", "before", "between", "through", "during", "above", "below",
    "each", "all", "both", "few", "more", "most", "other", "some", "such",
    "only", "own", "same", "also", "using", "used", "based", "via",
})


# ---------------------------------------------------------------------------
# Text similarity helpers
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> list[str]:
    """Lowercase, strip punctuation, remove stop words."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def _cosine_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
    """Counter-based cosine similarity between two token lists."""
    if not tokens_a or not tokens_b:
        return 0.0
    ca, cb = Counter(tokens_a), Counter(tokens_b)
    keys = set(ca) | set(cb)
    dot = sum(ca.get(k, 0) * cb.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v * v for v in ca.values()))
    mag_b = math.sqrt(sum(v * v for v in cb.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ---------------------------------------------------------------------------
# Pydantic models (optional - graceful degradation if pydantic unavailable)
# ---------------------------------------------------------------------------

if _HAS_PYDANTIC:
    class ValidatedPaper(BaseModel):
        model_config = {"extra": "allow"}

        paper_id: str = Field(pattern=r"^P\d{3,}$")
        doi: str = ""
        title: str = Field(min_length=5)
        authors: Any = ""
        year: Any = None
        journal: str = ""
        pmid: Optional[str] = None
        pmcid: Optional[str] = None
        abstract: Optional[str] = None

        @model_validator(mode="after")
        def check_abstract_title_relevance(self):
            if not self.abstract or len(self.abstract) < 20:
                return self
            if not self.title or len(self.title) < 5:
                return self
            sim = _cosine_similarity(
                _tokenize(self.title), _tokenize(self.abstract)
            )
            if sim < 0.05:
                raise ValueError(
                    f"abstract-title keyword similarity too low ({sim:.3f}): "
                    f"possible mismatch for {self.paper_id}"
                )
            return self

    class ValidatedPaperList(BaseModel):
        model_config = {"extra": "allow"}
        papers: list[ValidatedPaper]


# ---------------------------------------------------------------------------
# HTTP helper for PMID cross-validation
# ---------------------------------------------------------------------------

def _ncbi_url(url: str) -> str:
    if _NCBI_API_KEY and "ncbi.nlm.nih.gov" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={_NCBI_API_KEY}"
    return url


def _http_get(url: str, timeout: int = 15) -> str:
    url = _ncbi_url(url)
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return ""
    finally:
        socket.setdefaulttimeout(old_timeout)


def fetch_pubmed_title(pmid: str) -> str:
    """Fetch the title for a given PMID from PubMed."""
    if not pmid:
        return ""
    url = (f"{_NCBI_EUTILS_BASE}/efetch.fcgi?"
           f"db=pubmed&id={pmid}&rettype=xml&retmode=xml")
    time.sleep(_REQUEST_DELAY)
    xml_text = _http_get(url)
    if not xml_text:
        return ""
    try:
        root = ET.fromstring(xml_text)
        title_el = root.find(".//ArticleTitle")
        if title_el is not None and title_el.text:
            return title_el.text.strip()
    except ET.ParseError:
        pass
    return ""


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def validate_paper_list(paper_list_path: Path) -> dict:
    """Validate paper_list.json with Pydantic schema + content checks.

    Returns:
        {"valid": bool, "critical": [...], "warnings": [...], "info": [...]}
    """
    path = Path(paper_list_path)
    result: dict = {"valid": True, "critical": [], "warnings": [], "info": []}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as e:
        result["valid"] = False
        result["critical"].append(f"Cannot read paper_list.json: {e}")
        return result

    papers = data.get("papers", [])
    if not papers:
        result["warnings"].append("No papers found in paper_list.json")
        return result

    result["info"].append(f"Total papers: {len(papers)}")

    if _HAS_PYDANTIC:
        try:
            ValidatedPaperList.model_validate(data)
        except Exception as exc:
            errors_fn = getattr(exc, "errors", None)
            err_list = errors_fn() if callable(errors_fn) else [str(exc)]
            for err in err_list:
                try:
                    err_str = str(err)
                except Exception:
                    err_str = repr(err)
                if "similarity too low" in err_str:
                    result["critical"].append(err_str)
                else:
                    result["warnings"].append(err_str)

    # Content-level checks (no Pydantic dependency)
    seen_dois: dict[str, list[str]] = {}
    for i, p in enumerate(papers):
        pid = p.get("paper_id", f"papers[{i}]")

        # Check title presence
        title = str(p.get("title", "")).strip()
        if len(title) < 5:
            result["warnings"].append(f"{pid}: title too short or missing")

        # Check DOI duplicates
        doi = str(p.get("doi", "")).strip()
        if doi and doi.upper() not in ("N/A", "NONE", ""):
            seen_dois.setdefault(doi, []).append(pid)

        # Check abstract-title relevance (non-Pydantic fallback)
        abstract = str(p.get("abstract", "") or "").strip()
        if abstract and len(abstract) > 20 and title and len(title) > 5:
            sim = _cosine_similarity(_tokenize(title), _tokenize(abstract))
            if sim < 0.05:
                msg = f"{pid}: abstract-title similarity very low ({sim:.3f})"
                if msg not in [c for c in result["critical"]]:
                    result["critical"].append(msg)

        # Missing abstract
        if not abstract or len(abstract) < 20:
            result["warnings"].append(f"{pid}: abstract missing or very short")

    # Duplicate DOIs
    for doi, pids in seen_dois.items():
        if len(pids) > 1:
            result["warnings"].append(
                f"Duplicate DOI {doi} in papers: {', '.join(pids)}"
            )

    if result["critical"]:
        result["valid"] = False

    return result


def validate_fulltext_match(
    paper_list_path: Path,
    full_texts_dir: Path,
) -> dict:
    """Validate full text file content against paper titles.

    Returns:
        {"mismatches": [...], "missing": [...], "too_short": [...], "stats": {...}}
    """
    path = Path(paper_list_path)
    ft_dir = Path(full_texts_dir)
    result: dict = {
        "mismatches": [],
        "missing": [],
        "too_short": [],
        "ok": [],
        "stats": {"total": 0, "matched": 0, "mismatched": 0,
                  "missing": 0, "too_short": 0},
    }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return result

    papers = data.get("papers", [])
    result["stats"]["total"] = len(papers)

    for p in papers:
        pid = p.get("paper_id", "")
        title = str(p.get("title", "")).strip()
        ft_path = ft_dir / f"{pid}.txt"

        if not ft_path.exists():
            result["missing"].append(pid)
            result["stats"]["missing"] += 1
            continue

        content = ft_path.read_text(encoding="utf-8", errors="replace")

        if len(content) < 200:
            result["too_short"].append({
                "paper_id": pid,
                "chars": len(content),
            })
            result["stats"]["too_short"] += 1
            continue

        # Compare title keywords vs first 2000 chars of full text
        snippet = content[:2000]
        title_tokens = _tokenize(title)
        snippet_tokens = _tokenize(snippet)
        sim = _cosine_similarity(title_tokens, snippet_tokens)

        if sim < 0.05 and title_tokens:
            result["mismatches"].append({
                "paper_id": pid,
                "title": title,
                "similarity": round(sim, 4),
            })
            result["stats"]["mismatched"] += 1
        else:
            result["ok"].append(pid)
            result["stats"]["matched"] += 1

    return result


def validate_pmid_title_match(
    paper_list_path: Path,
    max_checks: int = 10,
) -> dict:
    """Cross-validate PMID → PubMed title vs paper_list title.

    Only checks papers that have a PMID. Limited to max_checks to avoid
    excessive API calls.

    Returns:
        {"checked": int, "matched": int, "mismatched": [...]}
    """
    path = Path(paper_list_path)
    result: dict = {"checked": 0, "matched": 0, "mismatched": []}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return result

    papers = data.get("papers", [])
    checked = 0

    for p in papers:
        if checked >= max_checks:
            break

        pmid = str(p.get("pmid", "") or "").strip()
        if not pmid:
            continue

        title = str(p.get("title", "")).strip()
        if not title:
            continue

        pubmed_title = fetch_pubmed_title(pmid)
        if not pubmed_title:
            continue

        checked += 1
        sim = _cosine_similarity(_tokenize(title), _tokenize(pubmed_title))

        if sim < 0.3:
            result["mismatched"].append({
                "paper_id": p.get("paper_id", ""),
                "pmid": pmid,
                "expected_title": title,
                "pubmed_title": pubmed_title,
                "similarity": round(sim, 4),
            })
        else:
            result["matched"] += 1

    result["checked"] = checked
    return result


def run_full_validation(
    paper_list_path: Path,
    full_texts_dir: Path | None = None,
    check_pmid: bool = False,
    max_pmid_checks: int = 10,
) -> dict:
    """Run all validation steps and return combined report.

    Returns:
        {
            "paper_list": {...},
            "fulltext_match": {...},
            "pmid_match": {...},
            "overall_valid": bool,
            "critical_count": int,
            "warning_count": int,
        }
    """
    paper_list_path = Path(paper_list_path)

    if full_texts_dir is None:
        full_texts_dir = paper_list_path.parent / "full_texts"

    report: dict = {
        "paper_list": validate_paper_list(paper_list_path),
        "fulltext_match": validate_fulltext_match(paper_list_path, full_texts_dir),
        "pmid_match": {},
        "overall_valid": True,
        "critical_count": 0,
        "warning_count": 0,
    }

    if check_pmid:
        report["pmid_match"] = validate_pmid_title_match(
            paper_list_path, max_checks=max_pmid_checks
        )

    # Aggregate
    report["critical_count"] = (
        len(report["paper_list"].get("critical", []))
        + len(report["fulltext_match"].get("mismatches", []))
        + len(report.get("pmid_match", {}).get("mismatched", []))
    )
    report["warning_count"] = (
        len(report["paper_list"].get("warnings", []))
        + len(report["fulltext_match"].get("too_short", []))
        + len(report["fulltext_match"].get("missing", []))
    )
    report["overall_valid"] = report["critical_count"] == 0

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate paper_list.json and full text files"
    )
    parser.add_argument(
        "--paper-list", type=Path, required=True,
        help="Path to paper_list.json",
    )
    parser.add_argument(
        "--full-texts", type=Path,
        help="Path to full_texts/ directory (default: sibling of paper_list)",
    )
    parser.add_argument(
        "--check-pmid", action="store_true",
        help="Cross-validate PMIDs against PubMed (requires network)",
    )
    parser.add_argument(
        "--max-pmid-checks", type=int, default=10,
        help="Max PMID cross-validation checks (default: 10)",
    )
    args = parser.parse_args()

    report = run_full_validation(
        args.paper_list,
        full_texts_dir=args.full_texts,
        check_pmid=args.check_pmid,
        max_pmid_checks=args.max_pmid_checks,
    )

    status = "PASS" if report["overall_valid"] else "FAIL"
    print(f"[validate_papers] {status} — "
          f"{report['critical_count']} critical, "
          f"{report['warning_count']} warnings",
          file=sys.stderr)

    for c in report["paper_list"].get("critical", []):
        print(f"  CRITICAL: {c}", file=sys.stderr)
    for m in report["fulltext_match"].get("mismatches", []):
        print(f"  CRITICAL: fulltext mismatch {m['paper_id']} "
              f"(sim={m['similarity']})", file=sys.stderr)
    for m in report.get("pmid_match", {}).get("mismatched", []):
        print(f"  CRITICAL: PMID mismatch {m['paper_id']} "
              f"(sim={m['similarity']})", file=sys.stderr)

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    print()
    sys.exit(0 if report["overall_valid"] else 1)


if __name__ == "__main__":
    main()
