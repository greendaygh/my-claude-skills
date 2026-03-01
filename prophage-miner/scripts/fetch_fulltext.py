"""PMC/Europe PMC full text acquisition with section splitting.

Downloads full text XML from PMC, parses into sections, and saves
as structured text files. Supports incremental processing (pending-only).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET

import requests

PMC_EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
RATE_LIMIT_DELAY = 0.35

SECTION_MAP = {
    "intro": "INTRODUCTION",
    "introduction": "INTRODUCTION",
    "methods": "METHODS",
    "materials": "METHODS",
    "materials|methods": "METHODS",
    "results": "RESULTS",
    "discussion": "DISCUSSION",
    "conclusions": "DISCUSSION",
}


def parse_sections(xml_text: str) -> dict[str, str]:
    """Parse PMC XML into section-name -> text mapping."""
    if not xml_text or not xml_text.strip():
        return {}

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return {}

    sections: dict[str, str] = {}

    abstract_el = root.find(".//abstract")
    if abstract_el is not None:
        abstract_text = _collect_text(abstract_el)
        if abstract_text.strip():
            sections["ABSTRACT"] = abstract_text.strip()

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
                section_name = title_el.text.upper()
            else:
                continue

        text = _collect_text(sec)
        if text.strip():
            if section_name in sections:
                sections[section_name] += "\n" + text.strip()
            else:
                sections[section_name] = text.strip()

    return sections


def _collect_text(element: ET.Element) -> str:
    """Recursively collect all text content from an element."""
    parts = []
    for el in element.iter():
        if el.tag == "title":
            continue
        if el.text:
            parts.append(el.text.strip())
        if el.tail:
            parts.append(el.tail.strip())
    return " ".join(p for p in parts if p)


def fetch_pmc_xml(pmcid: str) -> str:
    """Fetch full text XML from PMC. Returns empty string on failure."""
    print(f"[fetch_fulltext] Fetching PMC XML for {pmcid}...", file=sys.stderr)
    try:
        time.sleep(RATE_LIMIT_DELAY)
        resp = requests.get(
            PMC_EFETCH,
            params={"db": "pmc", "id": pmcid, "retmode": "xml"},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[fetch_fulltext] PMC fetch failed for {pmcid}: {e}", file=sys.stderr)
        return ""


def fetch_europepmc(pmcid: str) -> str:
    """Fallback: fetch full text XML from Europe PMC."""
    print(f"[fetch_fulltext] Trying Europe PMC for {pmcid}...", file=sys.stderr)
    try:
        time.sleep(RATE_LIMIT_DELAY)
        url = f"{EUROPEPMC_BASE}/{pmcid}/fullTextXML"
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"[fetch_fulltext] Europe PMC failed for {pmcid}: {e}", file=sys.stderr)
        return ""


def save_fulltext(paper_id: str, sections: dict[str, str], output_dir: Path) -> Path:
    """Save sections as structured text file."""
    output_dir = Path(output_dir)
    path = output_dir / "01_papers" / "full_texts" / f"{paper_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)

    ordered_keys = ["ABSTRACT", "INTRODUCTION", "METHODS", "RESULTS", "DISCUSSION"]
    lines = []
    for key in ordered_keys:
        if key in sections:
            lines.append(f"=== {key} ===")
            lines.append(sections[key])
            lines.append("")

    for key in sorted(sections.keys()):
        if key not in ordered_keys:
            lines.append(f"=== {key} ===")
            lines.append(sections[key])
            lines.append("")

    path.write_text("\n".join(lines))
    print(f"[fetch_fulltext] Saved {paper_id}.txt ({len(sections)} sections)", file=sys.stderr)
    return path


def process_papers(
    paper_list_path: Path,
    output_dir: Path,
    pending_only: bool = True,
) -> dict:
    """Process papers from paper_list.json: fetch full text and update flags."""
    paper_list_path = Path(paper_list_path)
    output_dir = Path(output_dir)
    data = json.loads(paper_list_path.read_text())

    stats = {"processed": 0, "skipped": 0, "failed": 0}

    for paper in data["papers"]:
        if pending_only and paper.get("has_full_text", False):
            stats["skipped"] += 1
            continue

        pmcid = paper.get("pmcid")
        if not pmcid:
            print(f"[fetch_fulltext] {paper['paper_id']}: No PMCID, skipping", file=sys.stderr)
            stats["skipped"] += 1
            continue

        xml = fetch_pmc_xml(pmcid)
        if not xml:
            xml = fetch_europepmc(pmcid)

        if not xml:
            print(f"[fetch_fulltext] {paper['paper_id']}: Could not get full text", file=sys.stderr)
            stats["failed"] += 1
            continue

        sections = parse_sections(xml)
        if not sections:
            print(f"[fetch_fulltext] {paper['paper_id']}: No sections extracted", file=sys.stderr)
            stats["failed"] += 1
            continue

        save_fulltext(paper["paper_id"], sections, output_dir)
        paper["has_full_text"] = True
        stats["processed"] += 1

    paper_list_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    print(
        f"[fetch_fulltext] Done: {stats['processed']} processed, "
        f"{stats['skipped']} skipped, {stats['failed']} failed",
        file=sys.stderr,
    )
    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch PMC full text for papers")
    parser.add_argument("--input", type=Path, required=True, help="Path to paper_list.json")
    parser.add_argument("--output", type=Path, help="Output directory (defaults to input parent parent)")
    parser.add_argument("--pending-only", action="store_true", default=True)
    args = parser.parse_args()

    output = args.output or args.input.parent.parent
    process_papers(args.input, output, pending_only=args.pending_only)


if __name__ == "__main__":
    main()
