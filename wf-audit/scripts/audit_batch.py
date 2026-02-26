"""Batch audit of workflow compositions (CLI entry point)."""

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add scripts dir to path for bare imports
sys.path.insert(0, str(Path(__file__).parent))

from audit_workflow import audit_single_workflow, get_migration_priority
from canonical_schemas import SCHEMA_VERSION, COMPOSITION_DATA


def discover_workflows(base_dir: Path) -> list:
    """Return sorted list of workflow dirs under base_dir.

    Globs for W*/composition_data.json and returns parent dirs.
    Excludes any path containing '_versions' in its parts.
    """
    base_dir = Path(base_dir)
    found = []
    for comp_json in sorted(base_dir.glob("W*/composition_data.json")):
        # Exclude paths inside _versions directories
        if "_versions" in comp_json.parts:
            continue
        found.append(comp_json.parent)
    return found


def audit_all_workflows(base_dir: Path, targets: list = None, catalog: dict = None) -> dict:
    """Audit all (or targeted) workflow dirs under base_dir.

    Args:
        base_dir: Root directory containing W* workflow folders.
        targets: Optional list of workflow ID prefixes to filter (e.g. ["WB005"]).
        catalog: Optional catalog dict passed to audit_single_workflow.

    Returns:
        Dict keyed by workflow_id -> audit result dict.
    """
    base_dir = Path(base_dir)
    wf_dirs = discover_workflows(base_dir)

    if targets:
        wf_dirs = [
            d for d in wf_dirs
            if any(d.name.startswith(t) for t in targets)
        ]

    results = {}
    for wf_dir in wf_dirs:
        result = audit_single_workflow(wf_dir, catalog)
        wf_id = result.get("workflow_id", wf_dir.name)
        results[wf_id] = result

    return results


def detect_cross_workflow_drift(results: dict, base_dir: Path = None) -> list:
    """Detect cross-workflow inconsistencies from audit results.

    Looks at composition_data violation messages for deprecated statistics
    key usage. Returns list of drift entries.
    """
    dep_map = COMPOSITION_DATA.get("statistics_deprecated_map", {})
    stats_deprecated_usage = defaultdict(list)  # deprecated_name -> [workflow_ids]

    for wf_id, result in results.items():
        comp_violations = (
            result.get("scores", {})
            .get("composition_data", {})
            .get("violations", [])
        )
        for v in comp_violations:
            if "deprecated statistics key" in v:
                for dep_key in dep_map:
                    if dep_key in v:
                        stats_deprecated_usage[dep_key].append(wf_id)

    drifts = []
    for dep_name, wf_ids in stats_deprecated_usage.items():
        canonical = dep_map.get(dep_name, dep_name)
        drifts.append({
            "drift_type": "statistics_field",
            "canonical_name": canonical,
            "found_names": [dep_name],
            "affected_workflows": sorted(wf_ids),
        })

    return drifts


def generate_batch_summary(results: dict, drifts: list) -> dict:
    """Generate a batch summary dict from audit results and drift analysis."""
    if not results:
        return {
            "audit_version": SCHEMA_VERSION,
            "audited_at": datetime.now(timezone.utc).isoformat(),
            "total_workflows": 0,
            "mean_conformance": 0.0,
            "schema_era_distribution": {},
            "conformance_histogram": {
                "0.9-1.0": 0, "0.7-0.9": 0, "0.5-0.7": 0,
                "0.3-0.5": 0, "0.0-0.3": 0,
            },
            "cross_workflow_drift": drifts,
            "migration_candidates": [],
            "top_common_violations": [],
        }

    scores = [r["conformance_score"] for r in results.values()]
    mean_conf = round(sum(scores) / len(scores), 4)

    # Schema era distribution: era -> [workflow_ids]
    era_dist = defaultdict(list)
    for wf_id, result in results.items():
        era = result.get("schema_era", "unknown")
        era_dist[era].append(wf_id)

    # Conformance histogram
    histogram = {"0.9-1.0": 0, "0.7-0.9": 0, "0.5-0.7": 0, "0.3-0.5": 0, "0.0-0.3": 0}
    for s in scores:
        if s >= 0.9:
            histogram["0.9-1.0"] += 1
        elif s >= 0.7:
            histogram["0.7-0.9"] += 1
        elif s >= 0.5:
            histogram["0.5-0.7"] += 1
        elif s >= 0.3:
            histogram["0.3-0.5"] += 1
        else:
            histogram["0.0-0.3"] += 1

    # Migration candidates: workflows where priority != "none", sorted by score asc
    migration_candidates = []
    for wf_id, result in results.items():
        score = result["conformance_score"]
        priority = get_migration_priority(score)
        if priority != "none":
            migration_candidates.append({
                "workflow_id": wf_id,
                "score": score,
                "priority": priority,
            })
    migration_candidates.sort(key=lambda x: x["score"])

    # Fake paper suspects
    fake_paper_suspects = []
    for wf_id, result in results.items():
        pv = result.get("paper_validity", {})
        if pv.get("suspect_count", 0) > 0:  # any fake DOI → flag
            fake_paper_suspects.append({
                "workflow_id": wf_id,
                "suspect_count": pv.get("suspect_count", 0),
                "total_papers": pv.get("total_papers", 0),
                "fake_ratio": pv.get("fake_ratio", 0),
            })
    fake_paper_suspects.sort(key=lambda x: x["fake_ratio"], reverse=True)

    # Top common violations across all workflows
    violation_counter: Counter = Counter()
    for result in results.values():
        for section_data in result.get("scores", {}).values():
            if isinstance(section_data, dict):
                for v in section_data.get("violations", []):
                    if v:
                        violation_counter[v] += 1
    top_violations = [v for v, _ in violation_counter.most_common(10)]

    return {
        "audit_version": SCHEMA_VERSION,
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "total_workflows": len(results),
        "mean_conformance": mean_conf,
        "schema_era_distribution": dict(era_dist),
        "conformance_histogram": histogram,
        "cross_workflow_drift": drifts,
        "migration_candidates": migration_candidates,
        "fake_paper_suspects": fake_paper_suspects,
        "top_common_violations": top_violations,
    }


def main(args=None):
    """CLI entry point for batch workflow audit."""
    parser = argparse.ArgumentParser(description="Batch audit workflow compositions")
    parser.add_argument("base_dir", type=Path, help="Base directory with workflow folders")
    parser.add_argument("--targets", nargs="*", help="Specific workflow IDs to audit")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip saving individual audit reports",
    )
    parsed = parser.parse_args(args)

    results = audit_all_workflows(parsed.base_dir, targets=parsed.targets)
    drifts = detect_cross_workflow_drift(results)
    summary = generate_batch_summary(results, drifts)

    if not parsed.summary_only:
        # Save individual audit reports
        for wf_id, result in results.items():
            for wf_dir in discover_workflows(parsed.base_dir):
                if wf_dir.name.startswith(wf_id):
                    out_path = wf_dir / "00_metadata" / "audit_report.json"
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(out_path, "w") as f:
                        json.dump(result, f, indent=2)
                    break

    # Save batch summary
    summary_path = parsed.base_dir / "audit_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Audited {summary['total_workflows']} workflows")
    print(f"Mean conformance: {summary['mean_conformance']}")
    print(f"Migration candidates: {len(summary['migration_candidates'])}")
    return summary


if __name__ == "__main__":
    main()
