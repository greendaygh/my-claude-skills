"""Generate a deterministic RunManifest for the executor subagent.

CLI:
    python -m scripts.plan_run \
      --wf-id WB030 \
      --root-dir ~/dev/wf-mining \
      --assets ~/.claude/skills/wf-paper-mining/assets \
      --output ~/dev/wf-mining/WB030/runs/

Output: {output}/run_manifest_{run_id}.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .run_tracker import RunTracker
from .models.manifest import (
    RunManifest, PhaseConfig, PanelDecision, PanelConfig,
    SearchConfig, FilePaths, SessionContext,
)


def _find_category(workflow_catalog: dict, wf_id: str) -> str:
    """Get workflow category (Design/Build/Test/Learn) from workflow_catalog."""
    wf = workflow_catalog.get("workflows", {}).get(wf_id, {})
    return wf.get("category", "unknown").lower()


def _get_wf_description(workflow_catalog: dict, wf_id: str) -> str:
    wf = workflow_catalog.get("workflows", {}).get(wf_id, {})
    name = wf.get("name", wf_id)
    desc = wf.get("description", "")
    return f"{name}: {desc}" if desc else name


def _get_uo_candidates(uo_catalog: dict) -> list[str]:
    return sorted(uo_catalog.get("unit_operations", {}).keys())


def _collect_pending(tracker: RunTracker) -> tuple[list[str], list[str]]:
    """Split into pending_papers (need fetch) and pending_extractions (need extract)."""
    pending_papers = [
        pid for pid, ps in tracker._state.paper_status.items()
        if ps.status == "pending"
    ]
    pending_extractions = [
        pid for pid, ps in tracker._state.paper_status.items()
        if ps.status == "fetched"
    ]
    return pending_papers, pending_extractions


def _build_file_paths(assets_dir: Path, wf_output_dir: Path) -> FilePaths:
    return FilePaths(
        extraction_guide=str(assets_dir / "uo_catalog.json"),
        panel_protocol=str(assets_dir / "panel_configs.json"),
        extraction_template=str(assets_dir / "extraction_template.json"),
        panel_configs=str(assets_dir / "panel_configs.json"),
        wf_output_dir=str(wf_output_dir),
        domain_context=str(assets_dir / "extraction_config.json"),
    )


def _generate_seed() -> int:
    seed = int(time.time() * 1000) % (2**31 - 1)
    return max(seed, 1)


def _build_skip_manifest(
    wf_id: str,
    run_id: int,
    reason: str,
    file_paths: FilePaths,
    session_context: SessionContext,
) -> RunManifest:
    skip_panel = PanelDecision(run=False, mode="skip", reason="action_skip")
    return RunManifest(
        workflow_id=wf_id,
        run_id=run_id,
        action="skip",
        reason=reason,
        phases=PhaseConfig(
            phase2_search=False,
            phase3_fetch=False,
            phase4_extract=False,
            phase4_5_aggregate=False,
        ),
        panels=PanelConfig(
            panel_b=skip_panel,
            panel_c=skip_panel,
        ),
        file_paths=file_paths,
        session_context=session_context,
    )


def plan_run(
    wf_id: str,
    root_dir: Path,
    assets_dir: Path,
    output_dir: Path,
) -> Path:
    tracker = RunTracker(root_dir, wf_id)

    exec_info = tracker.determine_execution()
    action = exec_info["action"]
    is_first_run = exec_info.get("is_first_run", False)
    run_count = exec_info.get("run_count", 0)
    run_id = run_count + 1

    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / f"run_manifest_{run_id}.json"

    wf_output_dir = output_dir.parent

    extraction_config = json.loads((assets_dir / "extraction_config.json").read_text())
    workflow_catalog = json.loads((assets_dir / "workflow_catalog.json").read_text())
    uo_catalog = json.loads((assets_dir / "uo_catalog.json").read_text())

    category = _find_category(workflow_catalog, wf_id)
    uo_candidates = _get_uo_candidates(uo_catalog)
    wf_description = _get_wf_description(workflow_catalog, wf_id)

    file_paths = _build_file_paths(assets_dir, wf_output_dir)
    session_context = SessionContext(
        domain=category,
        uo_candidates=uo_candidates,
        wf_description=wf_description,
    )

    if action == "skip":
        manifest = _build_skip_manifest(
            wf_id, run_id,
            exec_info.get("reason", "saturated"),
            file_paths, session_context,
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2))
        return manifest_path

    # Register placeholder RunRecord in wf_state so that papers added
    # with this run_id pass the _validate_run_id_references validator.
    tracker.start_run(domain=category)

    panel_mode = tracker.determine_panel_mode()
    saturation_action = exec_info.get("saturation_action", "search")
    is_saturated = saturation_action == "skip"

    phases = PhaseConfig(
        phase2_search=not is_saturated,
        phase3_fetch=not is_saturated,
        phase4_extract=not is_saturated,
        phase4_5_aggregate=True,
    )

    panels = PanelConfig(
        panel_b=PanelDecision(
            run=not is_saturated,
            mode=panel_mode if not is_saturated else "skip",
            reason="new_papers" if not is_saturated else "saturated",
        ),
        panel_c=PanelDecision(
            run=not is_saturated,
            mode=panel_mode if not is_saturated else "skip",
            reason="new_extractions" if not is_saturated else "saturated",
        ),
    )

    pending_papers, pending_extractions = _collect_pending(tracker)

    search_settings = extraction_config.get("search_settings", {})
    search_config = SearchConfig(
        exclude_dois=tracker.get_known_dois(),
        select_n=search_settings.get("default_select_n", 10),
        seed=_generate_seed(),
    )

    manifest = RunManifest(
        workflow_id=wf_id,
        run_id=run_id,
        action="execute",
        phases=phases,
        panels=panels,
        search_config=search_config,
        pending_papers=pending_papers,
        pending_extractions=pending_extractions,
        file_paths=file_paths,
        session_context=session_context,
    )

    manifest_path.write_text(manifest.model_dump_json(indent=2))
    return manifest_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="plan_run",
        description="Generate a deterministic RunManifest for the executor agent.",
    )
    parser.add_argument("--wf-id", required=True)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--root-dir", help="Root directory (v2)")
    g.add_argument("--registry", help="Legacy registry file path (auto-detects root)")
    parser.add_argument("--assets", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.root_dir:
        root = Path(args.root_dir).expanduser().resolve()
    else:
        root = Path(args.registry).expanduser().resolve().parent

    manifest_path = plan_run(
        wf_id=args.wf_id,
        root_dir=root,
        assets_dir=Path(args.assets).expanduser().resolve(),
        output_dir=Path(args.output).expanduser().resolve(),
    )

    print(json.dumps({"manifest_path": str(manifest_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
