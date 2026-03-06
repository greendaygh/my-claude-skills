"""Migrate legacy run_registry.json to per-workflow wf_state.json files.

CLI:
    python -m scripts.migrate_registry \
        --old-registry ~/dev/wf-mining/run_registry.json \
        --root-dir ~/dev/wf-mining/
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from .models.state import (
    RegistryIndex, RunRegistry, WorkflowIndexEntry, WorkflowState,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(old_registry_path: Path, root_dir: Path) -> dict:
    """Convert single run_registry.json into per-workflow wf_state.json files.

    Returns a summary dict with counts and any warnings.
    """
    data = json.loads(old_registry_path.read_text(encoding="utf-8"))
    old = RunRegistry.model_validate(data)

    migrated = 0
    skipped = 0
    warnings: list[str] = []

    index = RegistryIndex(
        created=old.created or _now(),
        last_updated=_now(),
    )

    for wf_id, wf_entry in old.workflows.items():
        wf_dir = root_dir / wf_id
        state_path = wf_dir / "wf_state.json"

        if state_path.exists():
            warnings.append(f"{wf_id}: wf_state.json already exists, skipping")
            skipped += 1
            continue

        wf_state = WorkflowState(
            workflow_id=wf_id,
            domain=wf_entry.domain,
            runs=wf_entry.runs,
            paper_status=wf_entry.paper_status,
            known_dois=wf_entry.known_dois,
            saturation=wf_entry.saturation,
            stable_cache=wf_entry.stable_cache,
            last_error=wf_entry.last_error,
        )

        # Validate the converted state
        try:
            WorkflowState.model_validate(wf_state.model_dump())
        except Exception as e:
            warnings.append(f"{wf_id}: validation failed: {e}")
            skipped += 1
            continue

        wf_dir.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            wf_state.model_dump_json(indent=2), encoding="utf-8",
        )
        migrated += 1

        # Update index entry
        extracted = sum(
            1 for ps in wf_entry.paper_status.values()
            if ps.status == "extracted"
        )
        index.workflows[wf_id] = WorkflowIndexEntry(
            domain=wf_entry.domain,
            run_count=len(wf_entry.runs),
            paper_count=len(wf_entry.paper_status),
            extracted_count=extracted,
            last_updated=_now(),
        )

    # Write index
    index_path = root_dir / "registry_index.json"
    index_path.write_text(
        index.model_dump_json(indent=2), encoding="utf-8",
    )

    # Validate the index
    RegistryIndex.model_validate(json.loads(index_path.read_text()))

    # Backup old registry
    backup_path = old_registry_path.with_suffix(".json.bak")
    if not backup_path.exists():
        shutil.copy2(old_registry_path, backup_path)

    return {
        "migrated": migrated,
        "skipped": skipped,
        "warnings": warnings,
        "index_path": str(index_path),
        "backup_path": str(backup_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate legacy run_registry.json to per-workflow wf_state.json"
    )
    parser.add_argument("--old-registry", type=Path, required=True,
                        help="Path to existing run_registry.json")
    parser.add_argument("--root-dir", type=Path, required=True,
                        help="Root output directory (e.g. ~/dev/wf-mining)")
    args = parser.parse_args()

    old_path = args.old_registry.expanduser().resolve()
    root = args.root_dir.expanduser().resolve()

    if not old_path.exists():
        print(json.dumps({"error": f"{old_path} not found"}))
        sys.exit(1)

    result = migrate(old_path, root)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0 if not result["warnings"] else 0)


if __name__ == "__main__":
    main()
