#!/usr/bin/env python3
"""
score_pqa.py — Rubric-based Paper Quality Assessment for workflow-composer v2.0.

Replaces the 6-expert PQA panel with deterministic rubric scoring.
Only ONE LLM call needed: extract_pqa_indicators() extracts factual indicators.
All scoring functions are pure/deterministic.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime

_SCRIPTS_DIR = Path(__file__).parent
_PROJECT_DIR = _SCRIPTS_DIR.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

from scripts import __version__

SKILL_DIR = Path(__file__).parent.parent
ASSETS_DIR = SKILL_DIR / "assets"


def load_v2_config() -> dict:
    """Load v2_config.json."""
    with open(ASSETS_DIR / "v2_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def load_journal_tiers() -> dict:
    """Load journal_tiers.json."""
    with open(ASSETS_DIR / "journal_tiers.json", "r", encoding="utf-8") as f:
        return json.load(f)


def extract_pqa_indicators(full_text: str) -> dict:
    """Extract factual indicators from paper full text.

    THIS IS THE ONLY LLM-DEPENDENT FUNCTION.
    In production, this is called by the LLM agent which fills in the values.
    For testing, we return a mock structure.

    The LLM should extract these factual indicators (not subjective scores):
    - journal_name: str
    - step_count: int (number of distinct protocol steps)
    - has_catalog_numbers: bool
    - has_detailed_concentrations: bool
    - equipment_named: list[str] (equipment with model/manufacturer)
    - software_named: list[str]
    - has_quantitative_results: bool (yields, purity percentages, activity values)
    - has_qualitative_results: bool (gel images, colony counts without numbers)
    - technique_keywords: list[str] (core techniques mentioned)
    - step_descriptions: list[str] (brief 1-line per step)

    Returns:
        Dict of factual indicators.
    """
    # This function is a TEMPLATE — the actual extraction happens via LLM.
    # The structure below shows what the LLM should return.
    return {
        "journal_name": "",
        "step_count": 0,
        "has_catalog_numbers": False,
        "has_detailed_concentrations": False,
        "equipment_named": [],
        "software_named": [],
        "has_quantitative_results": False,
        "has_qualitative_results": False,
        "technique_keywords": [],
        "step_descriptions": [],
        "_extraction_method": "template",
    }


def score_jq(indicators: dict, journal_tiers: dict = None) -> float:
    """Score Journal Quality (JQ) axis via tier lookup.

    Pure function — no LLM needed.
    """
    if journal_tiers is None:
        journal_tiers = load_journal_tiers()

    journal_name = indicators.get("journal_name", "").strip()
    if not journal_name:
        return journal_tiers.get("scoring", {}).get("unknown", 0.3)

    journal_lower = journal_name.lower()
    scoring = journal_tiers.get("scoring", {})
    tiers = journal_tiers.get("tiers", {})

    # Check preprint servers first
    for server in tiers.get("preprint", {}).get("servers", []):
        if server.lower() in journal_lower:
            return scoring.get("preprint", 0.3)

    # Check tiers (exact then partial match)
    for tier_name in ["tier1", "tier2", "tier3"]:
        tier_journals = tiers.get(tier_name, {}).get("journals", [])
        for j in tier_journals:
            if j.lower() == journal_lower or j.lower() in journal_lower:
                return scoring.get(tier_name, 0.3)

    return scoring.get("unknown", 0.3)


def score_pd(indicators: dict, rubric: dict = None) -> float:
    """Score Protocol Detail (PD) axis via step count bands.

    Pure function — no LLM needed.
    """
    step_count = indicators.get("step_count", 0)
    has_catalog = indicators.get("has_catalog_numbers", False)
    has_concentrations = indicators.get("has_detailed_concentrations", False)

    if step_count >= 8 and (has_catalog or has_concentrations):
        return 0.9
    elif step_count >= 6:
        return 0.7
    elif step_count >= 4:
        return 0.5
    else:
        return 0.3


def score_uc(indicators: dict, uo_catalog: dict = None) -> float:
    """Score UO Coverage (UC) axis via mappable step count.

    Pure function — checks how many paper steps can map to UO catalog.
    """
    step_descriptions = indicators.get("step_descriptions", [])
    technique_keywords = indicators.get("technique_keywords", [])
    equipment = indicators.get("equipment_named", [])

    if not step_descriptions:
        step_count = indicators.get("step_count", 0)
        if step_count == 0:
            return 0.1
        # Without descriptions, estimate from equipment/technique count
        mappable = len(equipment) + len(technique_keywords)
        ratio = min(mappable / max(step_count, 1), 1.0)
        return round(max(ratio, 0.2), 2)

    # Count steps that have equipment or known technique keywords
    mappable_count = 0
    for step in step_descriptions:
        step_lower = step.lower()
        has_equipment = any(eq.lower() in step_lower for eq in equipment) if equipment else False
        has_technique = any(tk.lower() in step_lower for tk in technique_keywords) if technique_keywords else False
        if has_equipment or has_technique or len(step.split()) >= 5:
            mappable_count += 1

    total = len(step_descriptions)
    ratio = mappable_count / total if total > 0 else 0
    return round(max(ratio, 0.1), 2)


def score_es(indicators: dict) -> float:
    """Score Equipment/Software Specificity (ES) axis.

    Pure function — counts named equipment with model numbers.
    """
    equipment_count = len(indicators.get("equipment_named", []))
    software_count = len(indicators.get("software_named", []))
    total = equipment_count + software_count

    if total >= 5:
        return 0.9
    elif total >= 3:
        return 0.7
    elif total >= 1:
        return 0.5
    else:
        return 0.2


def score_ev(indicators: dict) -> float:
    """Score Experimental Validation (EV) axis.

    Pure function — checks for quantitative/qualitative results.
    """
    if indicators.get("has_quantitative_results", False):
        return 0.9
    elif indicators.get("has_qualitative_results", False):
        return 0.5
    else:
        return 0.1


def score_ug(indicators: dict, pool_techniques: list[set] = None) -> float:
    """Score Uniqueness/Gap Fill (UG) axis via Jaccard distance.

    Pure function — computes 1 - max_jaccard_similarity to pool.
    """
    paper_techniques = set(t.lower() for t in indicators.get("technique_keywords", []))

    if not paper_techniques:
        return 0.5  # Neutral if no techniques extracted

    if not pool_techniques:
        return 0.9  # First paper is always unique

    max_similarity = 0.0
    for pool_set in pool_techniques:
        if not pool_set:
            continue
        intersection = paper_techniques & pool_set
        union = paper_techniques | pool_set
        if union:
            jaccard = len(intersection) / len(union)
            max_similarity = max(max_similarity, jaccard)

    return round(1.0 - max_similarity, 2)


AXIS_SCORERS = {
    "JQ": score_jq,
    "PD": score_pd,
    "UC": score_uc,
    "ES": score_es,
    "EV": score_ev,
    "UG": score_ug,
}


def score_axis(axis_code: str, indicators: dict, rubric: dict = None,
               pool_techniques: list[set] = None, journal_tiers: dict = None,
               uo_catalog: dict = None) -> float:
    """Score a single PQA axis using the rubric formula.

    Pure function (except JQ which needs journal_tiers data).

    Args:
        axis_code: "JQ", "PD", "UC", "ES", "EV", or "UG"
        indicators: from extract_pqa_indicators()
        rubric: rubric config from v2_config
        pool_techniques: list of technique sets from existing pool (for UG)
        journal_tiers: journal tier data (for JQ)
        uo_catalog: UO catalog (for UC)

    Returns:
        Score in [0.0, 1.0]
    """
    if axis_code == "JQ":
        return score_jq(indicators, journal_tiers)
    elif axis_code == "PD":
        return score_pd(indicators, rubric)
    elif axis_code == "UC":
        return score_uc(indicators, uo_catalog)
    elif axis_code == "ES":
        return score_es(indicators)
    elif axis_code == "EV":
        return score_ev(indicators)
    elif axis_code == "UG":
        return score_ug(indicators, pool_techniques)
    else:
        raise ValueError(f"Unknown PQA axis: {axis_code}")


def compute_pqa(indicators: dict, rubric: dict = None,
                pool_techniques: list[set] = None,
                journal_tiers: dict = None) -> dict:
    """Compute full PQA score from indicators.

    Args:
        indicators: from extract_pqa_indicators()
        rubric: from v2_config.phases.phase_2_pqa.rubric (loaded if None)
        pool_techniques: existing pool technique sets (for UG uniqueness)
        journal_tiers: journal tier data (loaded if None)

    Returns:
        {
            "pqa_scores": {"JQ": {"score": 0.7, "weight": 0.10}, ...},
            "pqa_composite": 0.72,
            "pool_status": "active" | "retired",
            "method": "rubric_v2",
        }
    """
    config = load_v2_config()
    pqa_phase_config = config.get("phases", {}).get("phase_2_pqa", {})

    if rubric is None:
        rubric = pqa_phase_config.get("rubric", {})

    if journal_tiers is None:
        try:
            journal_tiers = load_journal_tiers()
        except FileNotFoundError:
            journal_tiers = {"scoring": {"unknown": 0.3}, "tiers": {}}

    # Read threshold from config; fall back to 0.4 if not specified
    pqa_threshold = pqa_phase_config.get("pqa_threshold", 0.4)

    scores = {}
    composite = 0.0

    for axis_code, axis_config in rubric.items():
        weight = axis_config.get("weight", 0.0) if isinstance(axis_config, dict) else 0.0
        score = score_axis(axis_code, indicators, rubric,
                          pool_techniques, journal_tiers)
        scores[axis_code] = {"score": round(score, 2), "weight": weight}
        composite += score * weight

    composite = round(composite, 4)

    return {
        "pqa_scores": scores,
        "pqa_composite": composite,
        "pool_status": "active" if composite >= pqa_threshold else "retired",
        "method": "rubric_v2",
        "indicators_summary": {
            "journal": indicators.get("journal_name", ""),
            "step_count": indicators.get("step_count", 0),
            "equipment_count": len(indicators.get("equipment_named", [])),
            "software_count": len(indicators.get("software_named", [])),
        },
    }


def score_paper(paper_id: int, indicators: dict, rubric: dict = None,
                pool_techniques: list[set] = None,
                journal_tiers: dict = None,
                evaluated_in_version: float = 2.0) -> dict:
    """Score a single paper and return a PQA entry compatible with upgrade_manager.

    Returns dict compatible with upgrade_manager.create_pqa_entry().
    """
    result = compute_pqa(indicators, rubric, pool_techniques, journal_tiers)

    return {
        "paper_id": paper_id,
        "pqa_composite": result["pqa_composite"],
        "pqa_scores": result["pqa_scores"],
        "pool_status": result["pool_status"],
        "evaluated_in_version": evaluated_in_version,
        "method": "rubric_v2",
        "indicators_summary": result["indicators_summary"],
    }


def score_batch(papers_with_indicators: list[dict], rubric: dict = None,
                journal_tiers: dict = None) -> list[dict]:
    """Score a batch of papers, computing UG (uniqueness) incrementally.

    Args:
        papers_with_indicators: list of {"paper_id": int, "indicators": dict}
        rubric: PQA rubric config
        journal_tiers: journal tier data

    Returns:
        List of PQA entry dicts, sorted by composite descending.
    """
    if rubric is None:
        config = load_v2_config()
        rubric = config.get("phases", {}).get("phase_2_pqa", {}).get("rubric", {})

    if journal_tiers is None:
        try:
            journal_tiers = load_journal_tiers()
        except FileNotFoundError:
            journal_tiers = {"scoring": {"unknown": 0.3}, "tiers": {}}

    pool_techniques = []
    results = []

    for item in papers_with_indicators:
        paper_id = item["paper_id"]
        indicators = item["indicators"]

        result = score_paper(paper_id, indicators, rubric, pool_techniques, journal_tiers)
        results.append(result)

        # Add this paper's techniques to pool for subsequent UG scoring
        techniques = set(t.lower() for t in indicators.get("technique_keywords", []))
        if techniques:
            pool_techniques.append(techniques)

    # Sort by composite descending
    results.sort(key=lambda r: r["pqa_composite"], reverse=True)
    return results


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("=== score_pqa.py self-test ===\n")

        # Test 1: JQ scoring
        jt = {
            "scoring": {"tier1": 0.9, "tier2": 0.7, "tier3": 0.5, "preprint": 0.3, "unknown": 0.3},
            "tiers": {
                "tier1": {"journals": ["Nature Methods", "Nature Biotechnology"]},
                "tier2": {"journals": ["PLoS ONE", "Scientific Reports"]},
                "tier3": {"journals": ["Bio-protocol"]},
                "preprint": {"servers": ["bioRxiv"]},
            }
        }
        assert score_jq({"journal_name": "Nature Methods"}, jt) == 0.9
        assert score_jq({"journal_name": "PLoS ONE"}, jt) == 0.7
        assert score_jq({"journal_name": "Bio-protocol"}, jt) == 0.5
        assert score_jq({"journal_name": "bioRxiv"}, jt) == 0.3
        assert score_jq({"journal_name": "Unknown Journal"}, jt) == 0.3
        print("Test 1 PASS: JQ scoring correct")

        # Test 2: PD scoring
        assert score_pd({"step_count": 10, "has_catalog_numbers": True}) == 0.9
        assert score_pd({"step_count": 7, "has_catalog_numbers": False}) == 0.7
        assert score_pd({"step_count": 5}) == 0.5
        assert score_pd({"step_count": 2}) == 0.3
        print("Test 2 PASS: PD scoring correct")

        # Test 3: ES scoring
        assert score_es({"equipment_named": ["A", "B", "C", "D", "E"]}) == 0.9
        assert score_es({"equipment_named": ["A", "B", "C"]}) == 0.7
        assert score_es({"equipment_named": ["A"]}) == 0.5
        assert score_es({"equipment_named": []}) == 0.2
        print("Test 3 PASS: ES scoring correct")

        # Test 4: EV scoring
        assert score_ev({"has_quantitative_results": True}) == 0.9
        assert score_ev({"has_qualitative_results": True}) == 0.5
        assert score_ev({}) == 0.1
        print("Test 4 PASS: EV scoring correct")

        # Test 5: UG scoring
        assert score_ug({"technique_keywords": ["gibson"]}, []) == 0.9
        assert score_ug({"technique_keywords": ["gibson"]}, [{"gibson"}]) == 0.0
        assert score_ug({"technique_keywords": ["gibson", "pcr"]}, [{"gibson"}]) > 0.0
        print("Test 5 PASS: UG scoring correct")

        # Test 6: Full composite
        indicators = {
            "journal_name": "Nature Methods",
            "step_count": 10,
            "has_catalog_numbers": True,
            "has_detailed_concentrations": True,
            "equipment_named": ["Hamilton STAR", "Bio-Rad C1000", "Tecan Infinite"],
            "software_named": ["Benchling"],
            "has_quantitative_results": True,
            "has_qualitative_results": True,
            "technique_keywords": ["Gibson assembly", "transformation"],
            "step_descriptions": ["digest", "assemble", "transform", "plate", "pick", "verify", "sequence", "store"],
        }
        result = compute_pqa(indicators, journal_tiers=jt)
        assert result["pqa_composite"] > 0.5, f"Expected >0.5, got {result['pqa_composite']}"
        assert result["pool_status"] == "active"
        print(f"Test 6 PASS: Full composite = {result['pqa_composite']:.3f} ({result['pool_status']})")
        for axis, data in result["pqa_scores"].items():
            print(f"  {axis}: {data['score']:.2f} (weight={data['weight']})")

        # Test 7: Batch scoring with UG uniqueness
        batch = [
            {"paper_id": 1, "indicators": {**indicators, "technique_keywords": ["Gibson assembly"]}},
            {"paper_id": 2, "indicators": {**indicators, "technique_keywords": ["Gibson assembly"]}},
            {"paper_id": 3, "indicators": {**indicators, "technique_keywords": ["Golden Gate", "MoClo"]}},
        ]
        batch_results = score_batch(batch, journal_tiers=jt)
        # Paper 3 should have higher UG than paper 2 (different techniques)
        p2_ug = next(r for r in batch_results if r["paper_id"] == 2)["pqa_scores"]["UG"]["score"]
        p3_ug = next(r for r in batch_results if r["paper_id"] == 3)["pqa_scores"]["UG"]["score"]
        assert p3_ug > p2_ug, f"Paper 3 UG ({p3_ug}) should be > Paper 2 UG ({p2_ug})"
        print(f"\nTest 7 PASS: Batch UG uniqueness — P2={p2_ug:.2f}, P3={p3_ug:.2f}")

        # Test 8: Low-quality paper
        low_indicators = {
            "journal_name": "Unknown Publisher",
            "step_count": 2,
            "equipment_named": [],
            "software_named": [],
            "has_quantitative_results": False,
            "technique_keywords": [],
        }
        low_result = compute_pqa(low_indicators, journal_tiers=jt)
        assert low_result["pool_status"] == "retired", f"Expected retired, got {low_result['pool_status']}"
        print(f"Test 8 PASS: Low-quality paper → composite={low_result['pqa_composite']:.3f} (retired)")

        print("\n=== All tests passed! ===")
    else:
        print("Usage: python score_pqa.py --test")
        print("  Or import and use compute_pqa(), score_batch()")
