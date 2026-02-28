"""Audit-driven targeted fix module for wf-migrate.

Reads audit_report.json, filters pending violations, applies type-specific
fixes, and records fix_status/fix_action/fix_timestamp back into the report.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

_MIGRATION_VERSION = "2.2.0"


def load_pending_violations(wf_dir: Path) -> dict[str, list[dict]]:
    """Load unresolved violations from audit_report.json.

    Filters out violations with fix_status == "resolved".
    Groups by score section key (e.g. "composition_data", "case_cards").

    Returns:
        {section_key: [violation_dict, ...]}
        Empty dict if no audit_report.json or no pending violations.
    """
    report_path = wf_dir / "00_metadata" / "audit_report.json"
    if not report_path.exists():
        return {}

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    scores = report.get("scores", {})
    pending: dict[str, list[dict]] = {}

    for section_key, section_data in scores.items():
        if not isinstance(section_data, dict):
            continue
        detailed = section_data.get("detailed_violations", [])
        section_pending = [
            v for v in detailed
            if isinstance(v, dict) and v.get("fix_status") not in ("resolved", "skipped")
        ]
        if section_pending:
            pending[section_key] = section_pending

    return pending


def get_case_violation_map(pending: dict[str, list[dict]]) -> dict[str, bool]:
    """Build a map of case filenames that have pending violations.

    Returns: {"case_C001.json": True, ...}
    """
    case_violations: dict[str, bool] = {}
    case_section = pending.get("case_cards", [])
    for v in case_section:
        fname = v.get("file", "")
        if fname.startswith("02_cases/"):
            case_violations[fname.split("/")[-1]] = True
    return case_violations


def _set_value_at_path(data: dict, path: str, value) -> bool:
    """Set a value in nested dict at dot-separated path. Returns True if set."""
    parts = path.split(".")
    obj = data
    for part in parts[:-1]:
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return False
        else:
            return False
    last = parts[-1]
    if isinstance(obj, dict):
        obj[last] = value
        return True
    if isinstance(obj, list):
        try:
            idx = int(last)
            obj[idx] = value
            return True
        except (ValueError, IndexError):
            return False
    return False


def _get_value_at_path(data: dict, path: str):
    """Get value at dot-separated path, or None if not found."""
    obj = data
    for part in path.split("."):
        if isinstance(obj, dict) and part in obj:
            obj = obj[part]
        elif isinstance(obj, list):
            try:
                obj = obj[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return obj


def _fix_wrong_type(data: dict, violation: dict) -> tuple[str | None, str | None]:
    """Attempt to fix a wrong_type violation. Returns (fix_action, fix_status)."""
    path = violation.get("path", "")
    error_msg = violation.get("error", "")

    current_val = _get_value_at_path(data, path)
    if current_val is None:
        return None, "unresolved"

    if "valid string" in error_msg:
        if isinstance(current_val, dict) and "name" in current_val:
            _set_value_at_path(data, path, current_val["name"])
            return "object-to-string: name field extracted", "resolved"
        _set_value_at_path(data, path, str(current_val))
        return f"cast to string from {type(current_val).__name__}", "resolved"

    if "valid integer" in error_msg:
        try:
            _set_value_at_path(data, path, int(current_val))
            return f"cast to int from '{current_val}'", "resolved"
        except (ValueError, TypeError):
            return None, "unresolved"

    if "valid number" in error_msg or "valid float" in error_msg:
        try:
            _set_value_at_path(data, path, float(current_val))
            return f"cast to float from '{current_val}'", "resolved"
        except (ValueError, TypeError):
            return None, "unresolved"

    return None, "unresolved"


def _fix_missing(data: dict, violation: dict, wf_dir: Path = None) -> tuple[str | None, str | None]:
    """Attempt to fix a missing field violation. Returns (fix_action, fix_status)."""
    path = violation.get("path", "")

    if path.endswith(".score") and "completeness" in path:
        parent_path = path.rsplit(".", 1)[0]
        parent = _get_value_at_path(data, parent_path)
        if isinstance(parent, dict):
            parent["score"] = 0.0
            return "added completeness.score default 0.0", "resolved"

    if path.endswith(".workflow_id") and "workflow_context" in path:
        parent_path = path.rsplit(".", 1)[0]
        parent = _get_value_at_path(data, parent_path)
        wf_id = ""
        if wf_dir:
            comp_path = wf_dir / "composition_data.json"
            if comp_path.exists():
                try:
                    comp = json.loads(comp_path.read_text(encoding="utf-8"))
                    wf_id = comp.get("workflow_id", "")
                except (json.JSONDecodeError, OSError):
                    pass
        if isinstance(parent, dict):
            parent["workflow_id"] = wf_id
            return f"added workflow_context.workflow_id='{wf_id}'", "resolved"

    stat_match = re.match(r"statistics\.(\w+)$", path)
    if stat_match:
        field = stat_match.group(1)
        stats = data.get("statistics", {})
        if isinstance(stats, dict) and field not in stats:
            stats[field] = 0
            return f"added statistics.{field} default 0", "resolved"

    return None, "unresolved"


def apply_targeted_fixes(wf_dir: Path, pending: dict[str, list[dict]],
                         dry_run: bool = False) -> list[dict]:
    """Apply error_type-based fixes to actual JSON files.

    Returns list of fix result dicts (one per violation, with fix_status added).
    """
    now = datetime.now(timezone.utc).isoformat()
    fix_results: list[dict] = []
    files_to_write: dict[str, tuple[Path, dict]] = {}

    for section_key, violations in pending.items():
        for v in violations:
            result = dict(v)
            rel_file = v.get("file", "")
            if not rel_file:
                result["fix_status"] = "unresolved"
                result["fix_action"] = "no file path in violation"
                result["fix_timestamp"] = now
                fix_results.append(result)
                continue

            abs_path = wf_dir / rel_file
            cache_key = str(abs_path)

            if cache_key not in files_to_write:
                if abs_path.exists():
                    try:
                        data = json.loads(abs_path.read_text(encoding="utf-8"))
                        files_to_write[cache_key] = (abs_path, data)
                    except (json.JSONDecodeError, OSError):
                        result["fix_status"] = "unresolved"
                        result["fix_action"] = "failed to read file"
                        result["fix_timestamp"] = now
                        fix_results.append(result)
                        continue
                else:
                    result["fix_status"] = "unresolved"
                    result["fix_action"] = "file not found"
                    result["fix_timestamp"] = now
                    fix_results.append(result)
                    continue

            _, data = files_to_write[cache_key]
            error_type = v.get("error_type", "")

            fix_action, fix_status = None, "unresolved"
            if error_type == "wrong_type":
                fix_action, fix_status = _fix_wrong_type(data, v)
            elif error_type == "missing":
                fix_action, fix_status = _fix_missing(data, v, wf_dir=wf_dir)

            if dry_run and fix_status == "resolved":
                fix_status = "skipped"

            result["fix_status"] = fix_status
            result["fix_action"] = fix_action or "no auto-fix available"
            result["fix_timestamp"] = now
            fix_results.append(result)

    if not dry_run:
        for cache_key, (abs_path, data) in files_to_write.items():
            with open(abs_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

    return fix_results


def update_audit_report(wf_dir: Path, fix_results: list[dict],
                        pre_score: float = 0.0) -> dict:
    """Update audit_report.json with fix_status for each violation.

    Adds/updates:
    - fix_status, fix_action, fix_timestamp on each detailed_violation
    - migration_applied top-level section with summary statistics

    Returns the updated report dict.
    """
    report_path = wf_dir / "00_metadata" / "audit_report.json"
    if not report_path.exists():
        return {}

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

    fix_map: dict[str, dict] = {}
    for fr in fix_results:
        key = f"{fr.get('file', '')}|{fr.get('path', '')}|{fr.get('error', '')}"
        fix_map[key] = fr

    total_violations = 0
    resolved_count = 0
    unresolved_count = 0
    skipped_count = 0

    scores = report.get("scores", {})
    for section_key, section_data in scores.items():
        if not isinstance(section_data, dict):
            continue
        detailed = section_data.get("detailed_violations", [])
        for v in detailed:
            if not isinstance(v, dict):
                continue
            total_violations += 1
            key = f"{v.get('file', '')}|{v.get('path', '')}|{v.get('error', '')}"
            if key in fix_map:
                fr = fix_map[key]
                v["fix_status"] = fr["fix_status"]
                v["fix_action"] = fr["fix_action"]
                v["fix_timestamp"] = fr["fix_timestamp"]

            status = v.get("fix_status", "")
            if status == "resolved":
                resolved_count += 1
            elif status == "skipped":
                skipped_count += 1
            elif status == "unresolved" or not status:
                unresolved_count += 1

    now = datetime.now(timezone.utc).isoformat()
    report["migration_applied"] = {
        "migrated_at": now,
        "migration_version": _MIGRATION_VERSION,
        "total_violations_at_audit": total_violations,
        "resolved": resolved_count,
        "unresolved": unresolved_count,
        "skipped": skipped_count,
        "pre_migration_score": round(pre_score, 6),
        "post_migration_score": round(
            _estimate_post_score(total_violations, resolved_count, pre_score), 6
        ),
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    return report


def _estimate_post_score(total: int, resolved: int, pre_score: float) -> float:
    """Estimate post-migration conformance score."""
    if total == 0:
        return pre_score
    fix_ratio = resolved / total
    improvement = (1.0 - pre_score) * fix_ratio
    return min(1.0, pre_score + improvement)
