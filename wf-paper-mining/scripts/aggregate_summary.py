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
from .models.state import RunRegistry


def _load_extractions(input_dir: Path) -> list[ExtractionResult]:
    results: list[ExtractionResult] = []
    for p in sorted(input_dir.glob("*_extraction.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
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
    return tuple((s.uo_id, s.uo_name, s.is_hardware) for s in steps)


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
    pattern_to_papers: dict[tuple[tuple[str | None, str, bool], ...], list[str]] = {}
    for ext in extractions:
        steps = _build_uo_composition(ext)
        if not steps:
            continue
        key = _composition_key(steps)
        pattern_to_papers.setdefault(key, []).append(ext.paper_id)

    variants: list[VariantDefinition] = []
    new_since: list[str] = []
    for i, (key, papers) in enumerate(sorted(pattern_to_papers.items(), key=lambda x: -len(x[1])), 1):
        steps_list = [
            UoStep(order=j + 1, uo_id=triple[0], uo_name=triple[1], is_hardware=triple[2])
            for j, triple in enumerate(key)
        ]
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
    parser.add_argument("--registry", required=True, type=Path)
    parser.add_argument("--workflow-id", required=True)
    args = parser.parse_args()

    registry_data = json.loads(args.registry.read_text(encoding="utf-8"))
    registry = RunRegistry.model_validate(registry_data)
    wf = registry.workflows.get(args.workflow_id)
    paper_status = wf.paper_status if wf else {}

    all_extractions = _load_extractions(args.input)
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
