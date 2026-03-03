"""Repair corrupted paper metadata in paper_list.json.

Detects abstract-title mismatches caused by wrong PMID resolution,
re-resolves correct metadata from DOI, and clears contaminated fields
when correction is not possible.

Usage:
    python3 repair_paper_metadata.py --paper-list path/to/paper_list.json [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET

_NCBI_API_KEY = os.environ.get("NCBI_API_KEY", "")
_NCBI_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_ID_CONVERTER = "https://www.ncbi.nlm.nih.gov/pmc/utils/idconv/v1.0/"
_USER_AGENT = "wf-literature/3.0 (purpose: repair-paper-metadata)"
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

MISMATCH_THRESHOLD = 0.05


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


def _http_get(url: str, timeout: int = 15) -> str:
    if _NCBI_API_KEY and "ncbi.nlm.nih.gov" in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}api_key={_NCBI_API_KEY}"
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


def resolve_pmid_from_doi(doi: str) -> dict:
    if not doi:
        return {"pmid": "", "pmcid": ""}
    doi = doi.strip()
    if doi.startswith("http"):
        doi = re.sub(r"https?://doi\.org/", "", doi)
    url = f"{_NCBI_ID_CONVERTER}?ids={urllib.parse.quote(doi)}&format=json"
    text = _http_get(url)
    if not text:
        return {"pmid": "", "pmcid": ""}
    try:
        data = json.loads(text)
        records = data.get("records", [])
        if records:
            return {
                "pmid": records[0].get("pmid", ""),
                "pmcid": records[0].get("pmcid", ""),
            }
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return {"pmid": "", "pmcid": ""}


def fetch_pubmed_details(pmid: str) -> dict:
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
    result: dict = {}
    title_el = article.find(".//ArticleTitle")
    if title_el is not None and title_el.text:
        result["title"] = title_el.text.strip()
    abstract_parts = article.findall(".//AbstractText")
    if abstract_parts:
        abstract_text = " ".join((a.text or "") for a in abstract_parts).strip()
        if abstract_text:
            result["abstract"] = abstract_text
    mesh_headings = article.findall(".//MeshHeading/DescriptorName")
    if mesh_headings:
        result["mesh_terms"] = [m.text.strip() for m in mesh_headings if m.text]
    return result


def repair_paper_list(
    paper_list_path: Path,
    dry_run: bool = False,
    verbose: bool = True,
) -> dict:
    """Scan paper_list.json for abstract-title mismatches and repair them.

    Returns summary dict with counts and per-paper actions.
    """
    path = Path(paper_list_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    papers = data.get("papers", [])

    stats = {
        "total": len(papers),
        "checked": 0,
        "clean": 0,
        "repaired": 0,
        "cleared": 0,
        "no_abstract": 0,
        "actions": [],
    }

    for i, paper in enumerate(papers):
        pid = paper.get("paper_id", f"papers[{i}]")
        title = str(paper.get("title", "")).strip()
        abstract = str(paper.get("abstract", "") or "").strip()

        if not abstract or len(abstract) < 20:
            stats["no_abstract"] += 1
            continue

        if not title or len(title) < 5:
            stats["no_abstract"] += 1
            continue

        stats["checked"] += 1
        sim = _cosine_similarity(_tokenize(title), _tokenize(abstract))

        if sim >= MISMATCH_THRESHOLD:
            stats["clean"] += 1
            continue

        if verbose:
            print(f"  [{pid}] MISMATCH (sim={sim:.3f}): "
                  f"title='{title[:60]}...' abstract='{abstract[:60]}...'",
                  flush=True)

        doi = str(paper.get("doi", "")).strip()
        action = {"paper_id": pid, "similarity": round(sim, 4), "action": ""}

        if doi and doi.upper() not in ("N/A", "NONE", ""):
            time.sleep(_REQUEST_DELAY)
            id_result = resolve_pmid_from_doi(doi)
            resolved_pmid = id_result.get("pmid", "")

            if resolved_pmid:
                resolved_pmid = str(resolved_pmid)
                time.sleep(_REQUEST_DELAY)
                details = fetch_pubmed_details(resolved_pmid)
                pubmed_title = details.get("title", "")

                if pubmed_title:
                    title_sim = _cosine_similarity(
                        _tokenize(title), _tokenize(pubmed_title)
                    )

                    if title_sim >= 0.3:
                        new_abstract = details.get("abstract", "")
                        new_mesh = details.get("mesh_terms", [])

                        if new_abstract:
                            action["action"] = "repaired"
                            action["old_abstract_snippet"] = abstract[:80]
                            action["new_abstract_snippet"] = new_abstract[:80]
                            if verbose:
                                print(f"    -> REPAIR: DOI→PMID {resolved_pmid}, "
                                      f"title match (sim={title_sim:.3f})", flush=True)
                            if not dry_run:
                                paper["abstract"] = new_abstract
                                paper["pmid"] = str(resolved_pmid)
                                if new_mesh:
                                    paper["mesh_terms"] = new_mesh
                                if id_result.get("pmcid"):
                                    paper["pmcid"] = str(id_result["pmcid"])
                                paper.pop("pmid_title_mismatch", None)
                                paper["_repair_status"] = "metadata_corrected"
                            stats["repaired"] += 1
                        else:
                            action["action"] = "cleared"
                            if verbose:
                                print(f"    -> CLEAR: title matched but no abstract from PubMed",
                                      flush=True)
                            if not dry_run:
                                paper["abstract"] = ""
                                paper["mesh_terms"] = []
                                paper["_repair_status"] = "abstract_cleared"
                            stats["cleared"] += 1
                    else:
                        action["action"] = "cleared"
                        if verbose:
                            print(f"    -> CLEAR: DOI→PMID {resolved_pmid} title still "
                                  f"mismatches (sim={title_sim:.3f})", flush=True)
                        if not dry_run:
                            paper["abstract"] = ""
                            paper["mesh_terms"] = []
                            paper["pmid_title_mismatch"] = True
                            paper["_repair_status"] = "abstract_cleared"
                        stats["cleared"] += 1
                else:
                    action["action"] = "cleared"
                    if verbose:
                        print(f"    -> CLEAR: PubMed returned no title for PMID {resolved_pmid}",
                              flush=True)
                    if not dry_run:
                        paper["abstract"] = ""
                        paper["mesh_terms"] = []
                        paper["_repair_status"] = "abstract_cleared"
                    stats["cleared"] += 1
            else:
                action["action"] = "cleared"
                if verbose:
                    print(f"    -> CLEAR: DOI could not resolve to PMID", flush=True)
                if not dry_run:
                    paper["abstract"] = ""
                    paper["mesh_terms"] = []
                    paper["_repair_status"] = "abstract_cleared"
                stats["cleared"] += 1
        else:
            action["action"] = "cleared"
            if verbose:
                print(f"    -> CLEAR: no DOI available for re-resolution", flush=True)
            if not dry_run:
                paper["abstract"] = ""
                paper["mesh_terms"] = []
                paper["_repair_status"] = "abstract_cleared"
            stats["cleared"] += 1

        stats["actions"].append(action)

    if not dry_run and (stats["repaired"] > 0 or stats["cleared"] > 0):
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
        if verbose:
            print(f"  Saved updated paper_list.json", flush=True)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Repair corrupted paper metadata (abstract-title mismatches)")
    parser.add_argument("--paper-list", required=True,
                        help="Path to paper_list.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress per-paper messages")
    args = parser.parse_args()

    path = Path(args.paper_list)
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)

    mode = "DRY-RUN" if args.dry_run else "LIVE"
    print(f"[repair_paper_metadata] {mode} — {path}", flush=True)

    stats = repair_paper_list(path, dry_run=args.dry_run, verbose=not args.quiet)

    print(f"\n[SUMMARY] total={stats['total']} checked={stats['checked']} "
          f"clean={stats['clean']} repaired={stats['repaired']} "
          f"cleared={stats['cleared']} no_abstract={stats['no_abstract']}",
          flush=True)

    if args.dry_run and stats["actions"]:
        print(f"\n  {len(stats['actions'])} papers would be modified. "
              f"Run without --dry-run to apply.", flush=True)


if __name__ == "__main__":
    main()
