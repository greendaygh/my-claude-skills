"""Referential integrity checks across workflow files."""

import json
import re
import urllib.request
import urllib.error
from pathlib import Path
from canonical_schemas import CASE_ID_PATTERN


# --- DOI resolution cache (session-level) ---
_doi_resolve_cache: dict[str, bool] = {}


def _normalize_doi(doi: str) -> str:
    """Strip URL prefix from DOI, returning bare '10.XXXX/...' form."""
    if not doi or not isinstance(doi, str):
        return ""
    doi = doi.strip()
    # Strip common URL prefixes
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "http://dx.doi.org/"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):]
            break
    return doi


def _is_valid_doi_format(doi: str) -> bool:
    """Check if a string looks like a valid DOI format (10.XXXX/...)."""
    doi = _normalize_doi(doi)
    if not doi:
        return False
    # Must start with 10. and contain a slash
    return bool(re.match(r'^10\.\d{4,}/', doi))


def _doi_resolves(doi: str, timeout: int = 15, max_retries: int = 2) -> bool:
    """Check if a DOI resolves to a real resource via doi.org.

    Uses HEAD request first, falls back to GET on 403/429.
    Results are cached for the session to avoid redundant requests.
    Non-DOI strings (e.g., 'N/A', '') are treated as non-resolving.
    Retries on rate-limit (429) or transient errors with backoff.
    """
    doi = _normalize_doi(doi)
    if not _is_valid_doi_format(doi):
        return False

    if doi in _doi_resolve_cache:
        return _doi_resolve_cache[doi]

    import time
    import urllib.parse

    # URL-encode special characters in DOI suffix (e.g., parentheses)
    encoded_doi = urllib.parse.quote(doi, safe='/:@')
    url = f"https://doi.org/{encoded_doi}"
    for attempt in range(max_retries + 1):
        if attempt > 0:
            time.sleep(1.0 * attempt)  # backoff: 1s, 2s, ...

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
                    continue  # retry with GET
                if e.code == 429:
                    break  # rate limited — retry after backoff
                if e.code in (404, 410):
                    _doi_resolve_cache[doi] = False
                    return False
                # Other HTTP errors (500, 503, etc.) — assume real but unavailable
                _doi_resolve_cache[doi] = True
                return True
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt < max_retries:
                    break  # retry after backoff
                # Final attempt failed — assume real to avoid false positives
                _doi_resolve_cache[doi] = True
                return True

    # All retries exhausted — assume real to avoid false positives from rate limiting
    _doi_resolve_cache[doi] = True
    return True


def _load_json(path: Path) -> dict | list | None:
    """Load JSON file, return None if missing or invalid."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _normalize_case_ref(ref: str) -> str:
    """Strip workflow prefix from case ref, returning bare 'C001' form."""
    # If ref looks like "WB005-C001", extract "C001"
    match = re.match(r'^W[BTDL]\d{3}-(C\d{3,})$', ref)
    if match:
        return match.group(1)
    return ref


def check_case_variant_refs(wf_dir: Path) -> list[str]:
    """Check that all case refs in variant files exist in 02_cases/."""
    violations: list[str] = []
    variant_dir = wf_dir / "04_workflow"
    cases_dir = wf_dir / "02_cases"

    if not variant_dir.exists():
        return violations

    # Build set of known case suffixes (e.g. "C001")
    known = set()
    if cases_dir.exists():
        for f in cases_dir.glob("case_C*.json"):
            # filename: case_C001.json -> "C001"
            known.add(f.stem[len("case_"):])  # strip "case_" prefix

    for vfile in sorted(variant_dir.glob("variant_*.json")):
        data = _load_json(vfile)
        if not isinstance(data, dict):
            continue
        refs = data.get("supporting_cases") or data.get("case_ids") or []
        for ref in refs:
            normalized = _normalize_case_ref(ref)
            if normalized not in known:
                violations.append(
                    f"{vfile.name}: case ref '{ref}' not found in 02_cases/"
                )
    return violations


def check_uo_catalog_refs(wf_dir: Path, catalog: dict) -> list[str]:
    """Check that all uo_ids in variant uo_sequence exist in catalog.

    catalog is expected as {uo_id: {...}, ...}. If the catalog was loaded
    from uo_catalog.json as a list, convert it before passing in (or pass
    the raw list and this function will handle it).
    """
    violations: list[str] = []
    variant_dir = wf_dir / "04_workflow"

    if not variant_dir.exists():
        return violations

    # Handle list-format catalog (convert to dict keyed by uo_id)
    if isinstance(catalog, list):
        catalog = {item["uo_id"]: item for item in catalog if "uo_id" in item}

    for vfile in sorted(variant_dir.glob("variant_*.json")):
        data = _load_json(vfile)
        if not isinstance(data, dict):
            continue
        for step in data.get("uo_sequence", []):
            uo_id = step.get("uo_id")
            if uo_id and uo_id not in catalog:
                violations.append(
                    f"{vfile.name}: uo_id '{uo_id}' not found in UO catalog"
                )
    return violations


def check_paper_case_refs(wf_dir: Path) -> list[str]:
    """Check that pmids referenced in case cards exist in paper_list.json."""
    violations: list[str] = []

    # Load paper list — support both {"papers": [...]} and flat [...]
    paper_list_path = wf_dir / "01_literature" / "paper_list.json"
    raw = _load_json(paper_list_path)
    if raw is None:
        return violations

    if isinstance(raw, dict):
        papers = raw.get("papers", [])
    elif isinstance(raw, list):
        papers = raw
    else:
        papers = []

    known_pmids: set[str] = set()
    known_dois: set[str] = set()
    for p in papers:
        if isinstance(p, dict):
            if pmid := p.get("pmid"):
                known_pmids.add(str(pmid))
            if doi := p.get("doi"):
                known_dois.add(str(doi))

    cases_dir = wf_dir / "02_cases"
    if not cases_dir.exists():
        return violations

    for cfile in sorted(cases_dir.glob("case_C*.json")):
        data = _load_json(cfile)
        if not isinstance(data, dict):
            continue

        # Extract pmid from top-level or metadata.pmid
        pmid = data.get("pmid")
        if pmid is None:
            metadata = data.get("metadata")
            if isinstance(metadata, dict):
                pmid = metadata.get("pmid")

        if pmid is not None:
            if str(pmid) not in known_pmids:
                violations.append(
                    f"{cfile.name}: pmid '{pmid}' not found in paper_list.json"
                )
    return violations


# Word-list approach: known biology/method terms that appear in LLM-fabricated DOI suffixes
# Real DOIs use journal abbreviations + numeric article IDs (e.g., 10.1016/j.biortech.2022.127815)
# Fake DOIs embed descriptive words (e.g., 10.1007/s00449-022-pilot-ecoli)
_FAKE_DOI_WORDS = {
    # Organisms
    'ecoli', 'pichia', 'bacillus', 'mammalian', 'cglut', 'coli',
    'cerevisiae', 'subtilis', 'lactis', 'streptomyces', 'saccharomyces',
    'corynebacterium', 'aspergillus', 'kluyveromyces', 'yarrowia',
    # Scale / process terms (avoid journal names like 'fermentation' from MDPI)
    'pilot', 'bench', 'industrial', 'intensified', 'perfusion',
    'bioreactor', 'scaleup', 'downstream', 'upstream',
    'continuous', 'fedbatch', 'chemostat',
    # Product terms
    'multiproduct', 'mycoprotein', 'cellulase', 'collagen',
    'monoclonal', 'antibody', 'insulin', 'lysozyme', 'lipase',
    # Biotech methods
    'foundation', 'retro', 'cart', 'mrna', 'crispr', 'transfection',
    'electroporation', 'lentiviral', 'adenoviral',
    # Generic descriptive
    'optimization', 'purification', 'extraction', 'quantification',
    'multiplexing', 'assembly', 'cloning', 'sequencing',
}
_DOI_SUFFIX_TOKENS_RE = re.compile(r'[a-z]{3,}', re.IGNORECASE)


def _is_suspicious_doi(doi: str) -> bool:
    """Check if a DOI looks fabricated based on descriptive words in suffix."""
    doi = _normalize_doi(doi)
    if not doi:
        return False
    parts = doi.split('/', 1)
    if len(parts) < 2:
        return False
    suffix = parts[1]
    # Extract all 3+ letter tokens from suffix
    tokens = [t.lower() for t in _DOI_SUFFIX_TOKENS_RE.findall(suffix)]
    # Check against known fake-DOI words
    suspicious = [t for t in tokens if t in _FAKE_DOI_WORDS]
    return len(suspicious) >= 1


def check_paper_validity(wf_dir: Path, verify_doi: bool = True) -> dict:
    """Detect fake/placeholder papers in paper_list.json.

    When verify_doi=True (default), suspicious DOIs are verified against
    doi.org before being counted as fake. DOIs that resolve successfully
    are cleared even if their suffix pattern looks suspicious.

    Returns dict with:
        violations: list[str] - human-readable violation messages
        suspect_count: int - number of confirmed fake papers
        total_papers: int - total papers checked
        fake_ratio: float - suspect_count / total_papers
        duplicate_dois: list[dict] - duplicate DOI entries (separate from fakes)
    """
    violations: list[str] = []
    suspect_ids: set[str] = set()
    duplicate_dois: list[dict] = []

    # Load paper list — support both {"papers": [...]} and flat [...]
    paper_data = None
    for paper_subdir in ("01_papers", "01_literature"):
        paper_path = wf_dir / paper_subdir / "paper_list.json"
        if paper_path.exists():
            paper_data = _load_json(paper_path)
            break

    if paper_data is None:
        return {"violations": [], "suspect_count": 0, "total_papers": 0,
                "fake_ratio": 0.0, "duplicate_dois": []}

    if isinstance(paper_data, dict):
        papers = paper_data.get("papers", [])
    elif isinstance(paper_data, list):
        papers = paper_data
    else:
        papers = []

    if not papers:
        return {"violations": [], "suspect_count": 0, "total_papers": 0,
                "fake_ratio": 0.0, "duplicate_dois": []}

    total = len(papers)

    # Check 1: DOI suffix contains descriptive biology/method words
    # If verify_doi=True, confirm via doi.org before marking as fake
    for p in papers:
        if not isinstance(p, dict):
            continue
        pid = p.get("paper_id", "?")
        doi = p.get("doi", "")
        if doi and _is_suspicious_doi(doi):
            if verify_doi and _doi_resolves(doi):
                violations.append(
                    f"paper {pid}: DOI '{doi}' has suspicious suffix but resolves OK (cleared)"
                )
            else:
                violations.append(f"paper {pid}: fake DOI '{doi}' (suspicious suffix, does not resolve)")
                suspect_ids.add(pid)

    # Check 2: 100% enrichment failure (all status == "failed" or "error")
    statuses = [p.get("status", "") for p in papers if isinstance(p, dict)]
    failed_statuses = {"failed", "error", "not_found"}
    if statuses and all(s in failed_statuses for s in statuses if s):
        non_empty = [s for s in statuses if s]
        if len(non_empty) == total:
            violations.append(f"all {total} papers have failed enrichment status")
            for p in papers:
                if isinstance(p, dict):
                    suspect_ids.add(p.get("paper_id", "?"))

    # Check 3: All PMIDs empty
    pmids = [p.get("pmid", "") for p in papers if isinstance(p, dict)]
    if pmids and all(not pm for pm in pmids):
        violations.append(f"all {total} papers have empty PMID")
        for p in papers:
            if isinstance(p, dict):
                suspect_ids.add(p.get("paper_id", "?"))

    # Check 4: Duplicate DOIs — reported as warning, NOT added to suspects
    seen_dois: dict[str, list[str]] = {}
    for p in papers:
        if not isinstance(p, dict):
            continue
        doi = p.get("doi", "")
        if doi:
            pid = p.get("paper_id", "?")
            seen_dois.setdefault(doi, []).append(pid)
    for doi, pids in seen_dois.items():
        if len(pids) > 1:
            violations.append(f"duplicate DOI '{doi}' in papers: {', '.join(pids)} (data entry error, not fake)")
            duplicate_dois.append({"doi": doi, "paper_ids": pids})

    # Check 5: Verify all DOIs resolve (skip already-suspected and invalid formats)
    for p in papers:
        if not isinstance(p, dict):
            continue
        pid = p.get("paper_id", "?")
        doi = p.get("doi", "")
        if not doi or pid in suspect_ids:
            continue
        if not _is_valid_doi_format(doi):
            violations.append(f"paper {pid}: invalid DOI format '{doi}'")
            suspect_ids.add(pid)
        elif verify_doi and not _is_suspicious_doi(doi) and not _doi_resolves(doi):
            violations.append(f"paper {pid}: DOI '{doi}' does not resolve (confirmed 404/410)")
            suspect_ids.add(pid)

    # Check 6: All abstracts empty
    abstracts = [p.get("abstract", "") for p in papers if isinstance(p, dict)]
    if abstracts and all(not ab for ab in abstracts):
        violations.append(f"all {total} papers have empty abstract")
        # Weak evidence alone; don't add to suspects unless combined with other signals

    suspect_count = len(suspect_ids)
    fake_ratio = round(suspect_count / total, 4) if total > 0 else 0.0

    return {
        "violations": violations,
        "suspect_count": suspect_count,
        "total_papers": total,
        "fake_ratio": fake_ratio,
        "duplicate_dois": duplicate_dois,
    }


def check_statistics_consistency(wf_dir: Path) -> list[str]:
    """Check statistics in composition_data.json vs actual file counts."""
    violations: list[str] = []

    comp_path = wf_dir / "composition_data.json"
    data = _load_json(comp_path)
    if not isinstance(data, dict):
        return violations

    stats = data.get("statistics", {})
    if not isinstance(stats, dict):
        return violations

    cases_dir = wf_dir / "02_cases"
    actual_cases = len(list(cases_dir.glob("case_C*.json"))) if cases_dir.exists() else 0
    expected_cases = stats.get("cases_collected")
    if expected_cases is not None and int(expected_cases) != actual_cases:
        violations.append(
            f"statistics.cases_collected={expected_cases} but found {actual_cases} case files"
        )

    variant_dir = wf_dir / "04_workflow"
    actual_variants = len(list(variant_dir.glob("variant_*.json"))) if variant_dir.exists() else 0
    expected_variants = stats.get("variants_identified")
    if expected_variants is not None and int(expected_variants) != actual_variants:
        violations.append(
            f"statistics.variants_identified={expected_variants} but found {actual_variants} variant files"
        )

    return violations


def check_case_id_format(wf_dir: Path) -> list[str]:
    """Check that case_id in each case file matches CASE_ID_PATTERN."""
    violations: list[str] = []
    cases_dir = wf_dir / "02_cases"
    if not cases_dir.exists():
        return violations

    pattern = re.compile(CASE_ID_PATTERN)
    for cfile in sorted(cases_dir.glob("case_C*.json")):
        data = _load_json(cfile)
        if not isinstance(data, dict):
            continue
        case_id = data.get("case_id", "")
        if not pattern.match(str(case_id)):
            violations.append(
                f"{cfile.name}: case_id '{case_id}' does not match pattern {CASE_ID_PATTERN}"
            )
    return violations


def run_all(wf_dir: Path, catalog: dict = None) -> dict[str, list[str]]:
    """Run all referential integrity checks. Returns {check_name: [violations]}."""
    if catalog is None:
        catalog_path = Path.home() / ".claude/skills/workflow-composer/assets/uo_catalog.json"
        raw = _load_json(catalog_path)
        if isinstance(raw, dict):
            # Format: {"unit_operations": {"UHW010": {...}, ...}}
            uo_section = raw.get("unit_operations", raw)
            catalog = uo_section if isinstance(uo_section, dict) else {}
        elif isinstance(raw, list):
            catalog = {item["uo_id"]: item for item in raw if "uo_id" in item}
        else:
            catalog = {}

    return {
        "case_variant_refs": check_case_variant_refs(wf_dir),
        "uo_catalog_refs": check_uo_catalog_refs(wf_dir, catalog),
        "paper_case_refs": check_paper_case_refs(wf_dir),
        "paper_validity": check_paper_validity(wf_dir),
        "statistics_consistency": check_statistics_consistency(wf_dir),
        "case_id_format": check_case_id_format(wf_dir),
    }
