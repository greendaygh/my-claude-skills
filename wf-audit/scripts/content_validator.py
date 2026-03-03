"""Content validation for workflow paper data (post-collection quality check).

Detects content mismatches between paper metadata and full text files:
- Abstract vs title keyword similarity
- Full text file content vs title keyword similarity
- Missing or too-short full text files
- Duplicate DOIs

This module is designed for wf-audit integration (Step 15) and operates
independently of wf-literature/validate_papers.py (which is a pre-collection gate).
"""

from __future__ import annotations

import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

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

MIN_FULLTEXT_CHARS = 200
MAX_FULLTEXT_CHARS = 500_000
ABSTRACT_TITLE_THRESHOLD = 0.05
FULLTEXT_TITLE_THRESHOLD = 0.05


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) > 2]


def _cosine_similarity(tokens_a: list[str], tokens_b: list[str]) -> float:
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
# Main validation
# ---------------------------------------------------------------------------

def validate_paper_content_match(
    paper_list_path: Path | str,
    full_texts_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Validate paper content consistency for a single workflow.

    Checks:
    1. Abstract vs title keyword similarity
    2. Full text file vs title keyword similarity
    3. Full text file existence and length
    4. Duplicate DOIs

    Returns:
        {
            "abstract_title_mismatches": [...],
            "fulltext_title_mismatches": [...],
            "missing_fulltexts": [...],
            "too_short_fulltexts": [...],
            "too_long_fulltexts": [...],
            "duplicate_dois": [...],
            "stats": {
                "total_papers": int,
                "abstract_title_ok": int,
                "fulltext_ok": int,
                "fulltext_missing": int,
                "fulltext_too_short": int,
                "mismatches": int,
            },
        }
    """
    paper_list_path = Path(paper_list_path)
    if full_texts_dir is None:
        full_texts_dir = paper_list_path.parent / "full_texts"
    else:
        full_texts_dir = Path(full_texts_dir)

    result: dict[str, Any] = {
        "abstract_title_mismatches": [],
        "fulltext_title_mismatches": [],
        "missing_fulltexts": [],
        "too_short_fulltexts": [],
        "too_long_fulltexts": [],
        "duplicate_dois": [],
        "stats": {
            "total_papers": 0,
            "abstract_title_ok": 0,
            "fulltext_ok": 0,
            "fulltext_missing": 0,
            "fulltext_too_short": 0,
            "mismatches": 0,
        },
    }

    try:
        data = json.loads(paper_list_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError, OSError):
        return result

    papers = data.get("papers", [])
    if not papers:
        return result

    result["stats"]["total_papers"] = len(papers)

    # --- Abstract-title check ---
    for p in papers:
        pid = p.get("paper_id", "?")
        title = str(p.get("title", "")).strip()
        abstract = str(p.get("abstract", "") or "").strip()

        if not title or len(title) < 5:
            continue

        if abstract and len(abstract) > 20:
            title_tokens = _tokenize(title)
            abstract_tokens = _tokenize(abstract)
            sim = _cosine_similarity(title_tokens, abstract_tokens)
            if sim < ABSTRACT_TITLE_THRESHOLD and title_tokens:
                result["abstract_title_mismatches"].append({
                    "paper_id": pid,
                    "title": title[:100],
                    "abstract_snippet": abstract[:200],
                    "similarity": round(sim, 4),
                })
            else:
                result["stats"]["abstract_title_ok"] += 1

    # --- Full text checks ---
    for p in papers:
        pid = p.get("paper_id", "?")
        title = str(p.get("title", "")).strip()

        ft_path = full_texts_dir / f"{pid}.txt"
        if not ft_path.exists():
            result["missing_fulltexts"].append(pid)
            result["stats"]["fulltext_missing"] += 1
            continue

        try:
            content = ft_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            result["missing_fulltexts"].append(pid)
            result["stats"]["fulltext_missing"] += 1
            continue

        char_count = len(content)

        if char_count < MIN_FULLTEXT_CHARS:
            result["too_short_fulltexts"].append({
                "paper_id": pid,
                "chars": char_count,
            })
            result["stats"]["fulltext_too_short"] += 1
            continue

        if char_count > MAX_FULLTEXT_CHARS:
            result["too_long_fulltexts"].append({
                "paper_id": pid,
                "chars": char_count,
            })

        # Title vs full text snippet similarity
        if title and len(title) > 5:
            title_tokens = _tokenize(title)
            snippet_tokens = _tokenize(content[:2000])
            sim = _cosine_similarity(title_tokens, snippet_tokens)
            if sim < FULLTEXT_TITLE_THRESHOLD and title_tokens:
                result["fulltext_title_mismatches"].append({
                    "paper_id": pid,
                    "title": title[:100],
                    "similarity": round(sim, 4),
                    "fulltext_chars": char_count,
                })
                result["stats"]["mismatches"] += 1
            else:
                result["stats"]["fulltext_ok"] += 1
        else:
            result["stats"]["fulltext_ok"] += 1

    # --- Duplicate DOIs ---
    doi_map: dict[str, list[str]] = {}
    for p in papers:
        doi = str(p.get("doi", "")).strip()
        if doi and doi.upper() not in ("N/A", "NONE", ""):
            doi_map.setdefault(doi, []).append(p.get("paper_id", "?"))
    for doi, pids in doi_map.items():
        if len(pids) > 1:
            result["duplicate_dois"].append({"doi": doi, "paper_ids": pids})

    return result


def suggest_corrections(validation_result: dict) -> list[dict]:
    """Generate correction suggestions from validation results.

    Returns list of actionable suggestions with type, paper_id, and action.
    """
    suggestions: list[dict] = []

    for m in validation_result.get("abstract_title_mismatches", []):
        suggestions.append({
            "type": "abstract_title_mismatch",
            "paper_id": m["paper_id"],
            "severity": "critical",
            "action": "Verify PMID is correct. Re-fetch abstract from PubMed "
                      "or remove this paper and search for replacement.",
            "similarity": m["similarity"],
        })

    for m in validation_result.get("fulltext_title_mismatches", []):
        suggestions.append({
            "type": "fulltext_title_mismatch",
            "paper_id": m["paper_id"],
            "severity": "critical",
            "action": "Re-download full text using fetch_fulltext.py "
                      "or verify PMCID maps to the correct paper.",
            "similarity": m["similarity"],
        })

    for pid in validation_result.get("missing_fulltexts", []):
        suggestions.append({
            "type": "missing_fulltext",
            "paper_id": pid,
            "severity": "warning",
            "action": "Run fetch_fulltext.py with --all flag, or check if "
                      "paper has PMCID for PMC full text access.",
        })

    for m in validation_result.get("too_short_fulltexts", []):
        suggestions.append({
            "type": "too_short_fulltext",
            "paper_id": m["paper_id"],
            "severity": "warning",
            "action": f"Full text only {m['chars']} chars. Re-download or "
                      f"verify PMC access. May be abstract-only.",
        })

    return suggestions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate paper content consistency (wf-audit post-check)"
    )
    parser.add_argument(
        "--paper-list", type=Path, required=True,
        help="Path to paper_list.json",
    )
    parser.add_argument(
        "--full-texts", type=Path,
        help="Path to full_texts/ directory",
    )
    parser.add_argument(
        "--suggest", action="store_true",
        help="Include correction suggestions",
    )
    args = parser.parse_args()

    result = validate_paper_content_match(args.paper_list, args.full_texts)

    total_issues = (
        len(result["abstract_title_mismatches"])
        + len(result["fulltext_title_mismatches"])
        + len(result["missing_fulltexts"])
        + len(result["too_short_fulltexts"])
    )

    status = "PASS" if total_issues == 0 else "ISSUES"
    print(f"[content_validator] {status} — {total_issues} issues found",
          file=sys.stderr)

    output = dict(result)
    if args.suggest:
        output["suggestions"] = suggest_corrections(result)

    json.dump(output, sys.stdout, indent=2, ensure_ascii=False)
    print()
    sys.exit(0 if total_issues == 0 else 1)


if __name__ == "__main__":
    main()
