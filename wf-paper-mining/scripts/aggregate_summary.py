from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .models.extraction import ExtractionResult
from .models.summary import FrequencyItem, ResourceSummary, UoSummary, VariantSummary
from .models.variant import UoComposition, UoStep, VariantDefinition
from .models.state import WorkflowState


def _glob_extractions(input_dir: Path, workflow_id: str) -> list[Path]:
    wf_prefix_pattern = f"{workflow_id}_P*.json"
    legacy_pattern1 = f"*_{workflow_id}.json"
    legacy_pattern2 = "*_extraction.json"
    found = set(input_dir.glob(wf_prefix_pattern)) | set(input_dir.glob(legacy_pattern1)) | set(input_dir.glob(legacy_pattern2))
    return sorted(found)


def _normalize_extraction(data: dict) -> dict:
    """Normalize common LLM field-name variations to match ExtractionResult schema."""
    alias_map_list = {
        "workflows": {"workflow_id": "catalog_id", "workflow_name": "name"},
        "hardware_uos": {"uo_id": "catalog_id", "uo_name": "name",
                         "mapped_uo_id": "catalog_id", "mapped_uo_name": "name"},
        "software_uos": {"uo_id": "catalog_id", "uo_name": "name",
                         "mapped_uo_id": "catalog_id", "mapped_uo_name": "name"},
    }
    for field, renames in alias_map_list.items():
        for item in data.get(field, []):
            for old_key, new_key in renames.items():
                if old_key in item and new_key not in item:
                    item[new_key] = item.pop(old_key)

    conn_renames = {"from": "from_uo", "to": "to_uo", "transferred": "transfer_object"}
    for conn in data.get("uo_connections", []):
        for old_key, new_key in conn_renames.items():
            if old_key in conn and new_key not in conn:
                conn[new_key] = conn.pop(old_key)

    for qc in data.get("qc_checkpoints", []):
        for alias in ("checkpoint_id", "step", "checkpoint_name"):
            if alias in qc and "name" not in qc:
                qc["name"] = qc.pop(alias)
                break
        if "method" in qc and "metric" not in qc:
            qc["metric"] = qc.pop("method")
        if "criteria" in qc and "threshold" not in qc:
            qc["threshold"] = qc.pop("criteria")

    # Normalize confidence: string labels -> float
    confidence_map = {"high": 0.9, "medium": 0.6, "low": 0.3, "very high": 0.95, "very low": 0.1}
    for field in ("workflows", "hardware_uos", "software_uos", "equipment",
                  "consumables", "reagents", "samples", "uo_connections", "qc_checkpoints"):
        for item in data.get(field, []):
            if "confidence" in item and isinstance(item["confidence"], str):
                item["confidence"] = confidence_map.get(item["confidence"].lower(), 0.5)

    # Flatten dict parameters to string
    for field in ("hardware_uos", "software_uos"):
        for item in data.get(field, []):
            for k in ("parameters", "equipment", "consumables", "input", "output",
                       "material_and_method", "result", "discussion", "method", "environment"):
                if k in item and isinstance(item[k], (dict, list)):
                    item[k] = json.dumps(item[k], ensure_ascii=False)

    return data


def _load_extractions(input_dir: Path, workflow_id: str) -> list[ExtractionResult]:
    results: list[ExtractionResult] = []
    for p in _glob_extractions(input_dir, workflow_id):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            data = _normalize_extraction(data)
            results.append(ExtractionResult.model_validate(data))
        except Exception:
            pass
    return results


def _accept_extraction(paper_id: str, paper_status: dict) -> bool:
    ps = paper_status.get(paper_id)
    if not ps:
        return False
    if ps.status == "rejected":
        return False
    if ps.panel_verdict == "accept":
        return True
    if ps.status == "extracted":
        return True
    return False


def _build_uo_composition(ext: ExtractionResult) -> tuple[UoStep, ...]:
    steps: list[UoStep] = []
    order = 1
    for ref in ext.hardware_uos:
        steps.append(UoStep(order=order, uo_id=ref.catalog_id, uo_name=ref.name, is_hardware=True))
        order += 1
    for ref in ext.software_uos:
        steps.append(UoStep(order=order, uo_id=ref.catalog_id, uo_name=ref.name, is_hardware=False))
        order += 1
    return tuple(steps)


def _composition_key(steps: tuple[UoStep, ...]) -> tuple[tuple[str | None, str, bool], ...]:
    """Normalize to sorted tuple for order-independent variant comparison."""
    return tuple(sorted((s.uo_id, s.uo_name, s.is_hardware) for s in steps))


def _aggregate(extractions: list[ExtractionResult], workflow_id: str) -> tuple[ResourceSummary, list[dict]]:
    now = datetime.now(timezone.utc).isoformat()
    eq_counter: Counter[str] = Counter()
    eq_sources: dict[str, set[str]] = {}
    cons_counter: Counter[str] = Counter()
    cons_sources: dict[str, set[str]] = {}
    rea_counter: Counter[str] = Counter()
    rea_sources: dict[str, set[str]] = {}
    sam_counter: Counter[str] = Counter()
    sam_sources: dict[str, set[str]] = {}
    wf_uo: dict[str, tuple[int, set[str], bool, str | None, str]] = {}
    hw_uo: dict[str, tuple[int, set[str], bool, str | None, str]] = {}
    sw_uo: dict[str, tuple[int, set[str], bool, str | None, str]] = {}
    new_candidates: set[str] = set()

    for ext in extractions:
        pid = ext.paper_id
        for e in ext.equipment:
            eq_counter[e.name] += 1
            eq_sources.setdefault(e.name, set()).add(pid)
        for c in ext.consumables:
            cons_counter[c.name] += 1
            cons_sources.setdefault(c.name, set()).add(pid)
        for r in ext.reagents:
            rea_counter[r.name] += 1
            rea_sources.setdefault(r.name, set()).add(pid)
        for s in ext.samples:
            sam_counter[s.name] += 1
            sam_sources.setdefault(s.name, set()).add(pid)
        for w in ext.workflows:
            key = w.catalog_id or w.name
            if key not in wf_uo:
                wf_uo[key] = (0, set(), w.is_new, w.catalog_id, w.name)
            cnt, srcs, inew, cid, dname = wf_uo[key]
            wf_uo[key] = (cnt + 1, srcs | {pid}, inew or w.is_new, cid or w.catalog_id, dname or w.name)
        for h in ext.hardware_uos:
            key = h.catalog_id or h.name
            if key not in hw_uo:
                hw_uo[key] = (0, set(), h.is_new, h.catalog_id, h.name)
            cnt, srcs, inew, cid, dname = hw_uo[key]
            hw_uo[key] = (cnt + 1, srcs | {pid}, inew or h.is_new, cid or h.catalog_id, dname or h.name)
        for s in ext.software_uos:
            key = s.catalog_id or s.name
            if key not in sw_uo:
                sw_uo[key] = (0, set(), s.is_new, s.catalog_id, s.name)
            cnt, srcs, inew, cid, dname = sw_uo[key]
            sw_uo[key] = (cnt + 1, srcs | {pid}, inew or s.is_new, cid or s.catalog_id, dname or s.name)
        new_candidates.update(ext.new_uo_candidates)

    def _to_freq(counter: Counter, sources: dict[str, set[str]]) -> list[FrequencyItem]:
        return [
            FrequencyItem(name=k, count=v, source_papers=sorted(sources.get(k, set())))
            for k, v in counter.most_common()
        ]

    def _to_uo_summary(items: dict[str, tuple[int, set[str], bool, str | None, str]]) -> list[UoSummary]:
        out: list[UoSummary] = []
        for key, (cnt, srcs, is_new, catalog_id, display_name) in items.items():
            out.append(UoSummary(
                catalog_id=catalog_id,
                name=display_name or key,
                is_new=is_new,
                occurrence_count=cnt,
                source_papers=sorted(srcs),
            ))
        return sorted(out, key=lambda x: -x.occurrence_count)

    def _to_wf_uo(items: dict[str, tuple[int, set[str], bool, str | None, str]]) -> list[UoSummary]:
        out: list[UoSummary] = []
        for key, (cnt, srcs, is_new, catalog_id, display_name) in items.items():
            out.append(UoSummary(
                catalog_id=catalog_id,
                name=display_name or key,
                is_new=is_new,
                occurrence_count=cnt,
                source_papers=sorted(srcs),
            ))
        return sorted(out, key=lambda x: -x.occurrence_count)

    resource = ResourceSummary(
        workflow_id=workflow_id,
        generated=now,
        total_papers=len(extractions),
        total_extractions=len(extractions),
        workflows=_to_wf_uo(wf_uo),
        hardware_uos=_to_uo_summary(hw_uo),
        software_uos=_to_uo_summary(sw_uo),
        equipment=_to_freq(eq_counter, eq_sources),
        consumables=_to_freq(cons_counter, cons_sources),
        reagents=_to_freq(rea_counter, rea_sources),
        samples=_to_freq(sam_counter, sam_sources),
        new_catalog_candidates=[{"name": s} for s in sorted(new_candidates)],
    )
    new_catalog_list = [{"name": s} for s in sorted(new_candidates)]
    return resource, new_catalog_list


def _detect_variants(
    extractions: list[ExtractionResult],
    workflow_id: str,
    output_dir: Path,
    existing_variant_ids: set[str],
) -> VariantSummary:
    now = datetime.now(timezone.utc).isoformat()
    pattern_to_data: dict[tuple[tuple[str | None, str, bool], ...], tuple[list[str], tuple[UoStep, ...]]] = {}
    for ext in extractions:
        steps = _build_uo_composition(ext)
        if not steps:
            continue
        key = _composition_key(steps)
        if key not in pattern_to_data:
            pattern_to_data[key] = ([], steps)  # preserve first-seen step order
        pattern_to_data[key][0].append(ext.paper_id)

    variants: list[VariantDefinition] = []
    new_since: list[str] = []
    for i, (key, (papers, orig_steps)) in enumerate(sorted(pattern_to_data.items(), key=lambda x: -len(x[1][0])), 1):
        steps_list = list(orig_steps)
        comp = UoComposition(steps=steps_list)
        vid = f"V{i:03d}"
        vdef = VariantDefinition(
            variant_id=vid,
            workflow_id=workflow_id,
            composition=comp,
            source_papers=sorted(papers),
            discovered_in_run=1,
        )
        variants.append(vdef)
        if vid not in existing_variant_ids:
            new_since.append(vid)

    return VariantSummary(
        workflow_id=workflow_id,
        generated=now,
        total_variants=len(variants),
        variants=variants,
        new_since_last_run=new_since,
    )


def _load_existing_variant_ids(output_dir: Path, workflow_id: str) -> set[str]:
    p = output_dir / f"{workflow_id}_variants.json"
    if not p.exists():
        return set()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        vs = data.get("variants", [])
        return {v.get("variant_id", "") for v in vs if v.get("variant_id")}
    except Exception:
        return set()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--root-dir", type=Path, help="Root directory (v2)")
    g.add_argument("--registry", type=Path, help="Legacy registry file path")
    parser.add_argument("--workflow-id", required=True)
    args = parser.parse_args()

    if args.root_dir:
        state_path = args.root_dir / args.workflow_id / "wf_state.json"
    else:
        state_path = args.registry.expanduser().resolve().parent / args.workflow_id / "wf_state.json"

    if state_path.exists():
        ws = WorkflowState.model_validate(json.loads(state_path.read_text(encoding="utf-8")))
        paper_status = ws.paper_status
    else:
        paper_status = {}

    all_extractions = _load_extractions(args.input, args.workflow_id)
    accepted = [e for e in all_extractions if _accept_extraction(e.paper_id, paper_status)]

    resource, new_catalog_list = _aggregate(accepted, args.workflow_id)
    existing_ids = _load_existing_variant_ids(args.output, args.workflow_id)
    variants = _detect_variants(accepted, args.workflow_id, args.output, existing_ids)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / f"{args.workflow_id}_resource_summary.json").write_text(
        resource.model_dump_json(indent=2), encoding="utf-8"
    )
    (args.output / f"{args.workflow_id}_variants.json").write_text(
        variants.model_dump_json(indent=2), encoding="utf-8"
    )
    (args.output / f"{args.workflow_id}_new_catalog_candidates.json").write_text(
        json.dumps(new_catalog_list, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    summary = {
        "workflow_id": args.workflow_id,
        "total_extractions_loaded": len(all_extractions),
        "accepted_extractions": len(accepted),
        "resource_summary": resource.model_dump(),
        "variants": variants.model_dump(),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
