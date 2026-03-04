"""Target resolution + domain grouping for workflow paper mining.

CLI:
    python -m scripts.resolve_target \\
      --target "WB030" \\
      --assets ~/.claude/skills/wf-paper-mining/assets \\
      --output ~/dev/wf-mining
"""
from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path


def _resolve_target(target: str, catalog_wf_ids: list[str]) -> list[str]:
    if target.lower() == "all":
        return sorted(catalog_wf_ids)
    if "*" in target:
        return sorted(w for w in catalog_wf_ids if fnmatch.fnmatch(w, target))
    if target in catalog_wf_ids:
        return [target]
    return []


def _get_uo_candidates(uo_catalog: dict) -> list[str]:
    return sorted(uo_catalog.get("unit_operations", {}).keys())


def _find_domain_for_workflow(extraction_config: dict, wf_id: str) -> str:
    for domain_name, group in extraction_config.get("domain_groups", {}).items():
        if wf_id in group.get("workflows", []):
            return domain_name
    return "unknown"


def _build_domain_groups(
    wf_ids: list[str],
    workflow_catalog: dict,
    uo_catalog: dict,
    extraction_config: dict,
) -> list[dict]:
    domain_to_wfs: dict[str, list[str]] = {}
    for wf_id in wf_ids:
        domain = _find_domain_for_workflow(extraction_config, wf_id)
        domain_to_wfs.setdefault(domain, []).append(wf_id)

    dg_config = extraction_config.get("domain_groups", {})
    order_map = {
        d: g.get("execution_order", 999)
        for d, g in dg_config.items()
    }
    order_map.setdefault("unknown", 999)

    uo_candidates = _get_uo_candidates(uo_catalog)
    workflows_data = workflow_catalog.get("workflows", {})

    domains_with_wfs = [d for d in domain_to_wfs if domain_to_wfs[d]]
    domains_sorted = sorted(domains_with_wfs, key=lambda d: (order_map.get(d, 999), d))

    groups = []
    for domain in domains_sorted:
        wf_list = domain_to_wfs.get(domain, [])
        exec_order = order_map.get(domain, 999)
        workflows = []
        for wf_id in sorted(wf_list):
            wf = workflows_data.get(wf_id, {})
            workflows.append({
                "wf_id": wf_id,
                "name": wf.get("name", wf_id),
                "description": wf.get("description", ""),
                "uo_candidates": uo_candidates,
            })
        groups.append({
            "domain": domain,
            "execution_order": exec_order,
            "workflows": workflows,
        })
    return groups


def _ordered_workflows_from_groups(groups: list[dict]) -> list[str]:
    out = []
    for g in groups:
        for w in g.get("workflows", []):
            out.append(w["wf_id"])
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve target workflows and group by domain")
    parser.add_argument("--target", required=True)
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    assets = args.assets.expanduser().resolve()
    output_dir = args.output.expanduser().resolve()

    workflow_catalog = json.loads((assets / "workflow_catalog.json").read_text())
    uo_catalog = json.loads((assets / "uo_catalog.json").read_text())
    extraction_config = json.loads((assets / "extraction_config.json").read_text())

    catalog_wf_ids = list(workflow_catalog.get("workflows", {}).keys())
    resolved = _resolve_target(args.target, catalog_wf_ids)

    if not resolved:
        result = {
            "target": args.target,
            "total_workflows": 0,
            "ordered_workflows": [],
            "domain_groups": [],
        }
    else:
        groups = _build_domain_groups(
            resolved, workflow_catalog, uo_catalog, extraction_config
        )
        ordered = _ordered_workflows_from_groups(groups)
        result = {
            "target": args.target,
            "total_workflows": len(resolved),
            "ordered_workflows": ordered,
            "domain_groups": groups,
        }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "resolve_result.json"
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

    summary = {
        "target": args.target,
        "total_workflows": result["total_workflows"],
        "ordered_workflows": result["ordered_workflows"],
        "output_path": str(out_path),
    }
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
