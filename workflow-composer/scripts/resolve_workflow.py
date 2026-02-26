#!/usr/bin/env python3
"""
resolve_workflow.py — Parse workflow ID/name and create output directory structure.

v2.0.0: Simplified to 2 modes (New/Update), removed upgrade_manager dependency.
"""

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"


def load_catalog():
    """Load workflow catalog from assets."""
    catalog_path = ASSETS_DIR / "workflow_catalog.json"
    with open(catalog_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_domain_classification():
    """Load domain classification from assets."""
    domain_path = ASSETS_DIR / "domain_classification.json"
    with open(domain_path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_uo_catalog():
    """Load unit operation catalog from assets."""
    uo_path = ASSETS_DIR / "uo_catalog.json"
    with open(uo_path, "r", encoding="utf-8") as f:
        return json.load(f)


def parse_workflow_input(user_input: str, catalog: dict) -> dict:
    """
    Parse user input to resolve workflow ID and name.

    Accepts:
      - "WB030" (ID only)
      - "DNA Assembly" (name only)
      - "WB030 DNA Assembly" (ID + name)

    Returns:
      {"id": "WB030", "name": "DNA Assembly", "description": "...", "category": "Build"}
    """
    user_input = user_input.strip()
    workflows = catalog.get("workflows", {})

    # Try exact ID match
    id_match = re.match(r"^(W[DBTL]\d{3})", user_input, re.IGNORECASE)
    if id_match:
        wf_id = id_match.group(1).upper()
        if wf_id in workflows:
            return workflows[wf_id]

    # Try name match (case-insensitive, partial)
    name_part = re.sub(r"^W[DBTL]\d{3}\s*", "", user_input, flags=re.IGNORECASE).strip()
    if not name_part:
        name_part = user_input

    for wf_id, wf_data in workflows.items():
        if name_part.lower() in wf_data["name"].lower():
            return wf_data

    raise ValueError(f"Workflow not found: '{user_input}'. Check workflow_catalog.json.")


def get_domain(workflow_id: str, domain_data: dict) -> dict:
    """Get domain group for a workflow."""
    wf_to_domain = domain_data.get("workflow_to_domain", {})
    domain_name = wf_to_domain.get(workflow_id, "Unknown")
    domain_groups = domain_data.get("domain_groups", {})
    domain_info = domain_groups.get(domain_name, {})
    return {
        "domain_name": domain_name,
        "keywords": domain_info.get("keywords", []),
    }


def sanitize_dirname(name: str) -> str:
    """Convert workflow name to filesystem-safe directory name."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name.replace(" ", "_")).strip("_")


def create_output_directory(workflow_id: str, workflow_name: str, base_dir: str = ".") -> Path:
    """Create the full output directory structure for a workflow."""
    dir_name = f"{workflow_id}_{sanitize_dirname(workflow_name)}"
    wf_dir = Path(base_dir) / "workflow-compositions" / dir_name

    subdirs = [
        "00_metadata",
        "01_papers",
        "01_papers/full_texts",
        "02_cases",
        "03_analysis",
        "04_workflow",
        "05_visualization",
        "06_review",
    ]

    for subdir in subdirs:
        (wf_dir / subdir).mkdir(parents=True, exist_ok=True)

    return wf_dir


def create_workflow_context(workflow_data: dict, domain_info: dict, wf_dir: Path) -> dict:
    """Create and save workflow_context.json."""
    context = {
        "workflow_id": workflow_data["id"],
        "workflow_name": workflow_data["name"],
        "category": workflow_data["category"],
        "description": workflow_data["description"],
        "domain": domain_info["domain_name"],
        "domain_keywords": domain_info.get("keywords", []),
        "output_directory": str(wf_dir),
    }

    context_path = wf_dir / "00_metadata" / "workflow_context.json"
    with open(context_path, "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    return context


def _detect_mode(user_input: str, base_dir: str) -> dict:
    """
    Detect composition mode from user input and existing files.

    2 modes only: New / Update.
    --fresh flag = backup existing + run as New.

    Returns: {"mode": "new"|"update", "wf_input": str, "existing_dir": Path|None, "fresh": bool}
    """
    fresh = "--fresh" in user_input
    wf_input = user_input.replace("--fresh", "").strip()

    # Find existing composition directory
    compositions_dir = Path(base_dir) / "workflow-compositions"
    existing_dir = None

    if compositions_dir.exists():
        id_match = re.match(r"^(W[DBTL]\d{3})", wf_input, re.IGNORECASE)
        if id_match:
            wf_id = id_match.group(1).upper()
            matches = list(compositions_dir.glob(f"{wf_id}_*/composition_data.json"))
            if matches:
                existing_dir = matches[0].parent

    if fresh or existing_dir is None:
        return {"mode": "new", "wf_input": wf_input, "existing_dir": existing_dir, "fresh": fresh}
    else:
        return {"mode": "update", "wf_input": wf_input, "existing_dir": existing_dir, "fresh": False}


def _create_backup(wf_dir: Path) -> Path:
    """Create a timestamped backup of the existing workflow directory."""
    versions_dir = wf_dir / "_versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = versions_dir / f"backup_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Copy key files to backup
    for pattern in ["composition_data.json", "composition_report.md",
                    "composition_workflow.md", "02_cases/case_summary.json"]:
        for src in wf_dir.glob(pattern):
            dst = backup_dir / src.relative_to(wf_dir)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    return backup_dir


def _get_known_papers(wf_dir: Path) -> set:
    """Get DOIs/PMIDs of papers already in paper_list.json."""
    paper_list_path = wf_dir / "01_papers" / "paper_list.json"
    known = set()
    if paper_list_path.exists():
        with open(paper_list_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for paper in data.get("papers", []):
            if paper.get("doi"):
                known.add(paper["doi"].lower())
            if paper.get("pmid"):
                known.add(str(paper["pmid"]))
    return known


def resolve_and_setup(user_input: str, base_dir: str = ".") -> dict:
    """
    Main entry point: parse input, resolve workflow, create directories, save context.

    2 modes:
      - New: no existing composition (or --fresh flag) → create from scratch
      - Update: existing composition found → backup, add new papers, re-analyze

    --fresh flag: backup existing directory, then proceed as New.

    Returns the workflow context dict with 'composition_mode' field.
    """
    catalog = load_catalog()
    domain_data = load_domain_classification()

    mode_info = _detect_mode(user_input, base_dir)
    wf_input = mode_info["wf_input"]
    mode = mode_info["mode"]

    workflow_data = parse_workflow_input(wf_input, catalog)
    domain_info = get_domain(workflow_data["id"], domain_data)

    if mode == "update":
        wf_dir = mode_info["existing_dir"]
        backup_path = _create_backup(wf_dir)

        # Ensure all subdirs exist (in case of older structure)
        for subdir in ["01_papers/full_texts", "05_visualization", "06_review"]:
            (wf_dir / subdir).mkdir(parents=True, exist_ok=True)

        known_papers = _get_known_papers(wf_dir)

        context = create_workflow_context(workflow_data, domain_info, wf_dir)
        context["composition_mode"] = "update"
        context["update_info"] = {
            "backup_path": str(backup_path),
            "known_paper_count": len(known_papers),
            "known_papers": list(known_papers),
        }

    else:
        # New mode (includes --fresh: backup first, then create fresh)
        if mode_info["fresh"] and mode_info["existing_dir"] is not None:
            _create_backup(mode_info["existing_dir"])

        wf_dir = create_output_directory(workflow_data["id"], workflow_data["name"], base_dir)
        context = create_workflow_context(workflow_data, domain_info, wf_dir)
        context["composition_mode"] = "new"

    return context


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python resolve_workflow.py <workflow_id_or_name> [--fresh]")
        sys.exit(1)

    user_input = " ".join(sys.argv[1:])
    context = resolve_and_setup(user_input)
    print(json.dumps(context, indent=2, ensure_ascii=False))
