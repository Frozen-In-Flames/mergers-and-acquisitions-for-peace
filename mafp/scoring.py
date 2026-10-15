"""Pairwise acquirer/target scoring for M&A screening.

Inputs per pair: two portfolio dicts (as built by mafp.portfolio), two
awards dicts (as built by mafp.awards). Output: a ranked list with a
plain-English rationale per pair.

The composite is a screening score, 0 to 100. It is not a valuation, not a
recommendation, and not investment advice. Weights are fixed and labeled.
"""

from __future__ import annotations

import math
import sys
import os
from typing import Dict, List

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "vendor"))

from ppa import merge  # noqa: E402

# Fixed, labeled weights for the screening score.
WEIGHTS = {
    "concept_overlap": 0.30,   # shared technology concepts
    "redundancy": 0.20,        # redundant patent pairs (overlap to prune)
    "gap_closure": 0.25,       # target capabilities the acquirer lacks
    "award_scale": 0.25,       # federal dollars that consolidate
}


def _top_labels(items: List[Dict], n: int = 3) -> List[str]:
    return [i.get("label", "") for i in items[:n] if i.get("label")]


def score_pair(acq: Dict, tgt: Dict) -> Dict:
    """Score one acquirer/target pair. acq/tgt each carry portfolio, awards,
    ticker, name, and provenance."""
    comp = merge.compare(acq["portfolio"], tgt["portfolio"])

    n_shared = comp["overlap_concept_count"]
    redundant = comp["redundant_pairs"]
    n_redundant = len(redundant)
    gap = comp["concepts_unique_to_b"]
    n_gap = comp["unique_b_count"]

    tgt_by_year = tgt["awards"].get("by_year", {}) or {}
    latest_fy = max((int(k) for k in tgt_by_year.keys()), default=None)
    tgt_awards = None
    if latest_fy is not None:
        tgt_awards = tgt_by_year.get(str(latest_fy))

    top_redundant = [
        {"a_number": p["a_number"], "a_title": p["a_title"][:80],
         "b_number": p["b_number"], "b_title": p["b_title"][:80],
         "shared_concepts": p["shared_concepts"][:5],
         "score": p["score"]}
        for p in redundant[:5]
    ]

    return {
        "acquirer": acq["ticker"],
        "acquirer_name": acq["name"],
        "target": tgt["ticker"],
        "target_name": tgt["name"],
        "shared_concept_count": n_shared,
        "shared_concepts_top": _top_labels(comp["concept_overlap"]),
        "redundant_pair_count": n_redundant,
        "redundant_pairs_top": top_redundant,
        "gap_concept_count": n_gap,
        "gap_concepts_top": _top_labels(gap),
        "target_awards_latest_fy": latest_fy,
        "target_awards_latest_usd": tgt_awards,
        "target_awards_source": tgt["awards"].get("source", ""),
        "portfolio_provenance": {
            "acquirer": acq["provenance"], "target": tgt["provenance"]},
        "awards_provenance": {
            "acquirer": acq["awards_provenance"],
            "target": tgt["awards_provenance"]},
        "weights": WEIGHTS,
    }


def _norm(values: List[float]) -> List[float]:
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def rank_pairs(scored: List[Dict]) -> List[Dict]:
    """Apply min-max normalization across the pair set and rank.

    Returns the pairs sorted by screening score, highest first, each with
    its score and component breakdown attached.
    """
    if not scored:
        return []
    shared = _norm([float(s["shared_concept_count"]) for s in scored])
    redund = _norm([float(s["redundant_pair_count"]) for s in scored])
    gaps = _norm([float(s["gap_concept_count"]) for s in scored])
    awards = _norm([math.log10(max(float(s["target_awards_latest_usd"] or 0), 1.0))
                    for s in scored])
    ranked = []
    for s, a, b, c, d in zip(scored, shared, redund, gaps, awards):
        parts = {
            "concept_overlap": round(a, 3),
            "redundancy": round(b, 3),
            "gap_closure": round(c, 3),
            "award_scale": round(d, 3),
        }
        score = sum(WEIGHTS[k] * parts[k] for k in WEIGHTS)
        s = dict(s)
        s["score_parts"] = parts
        s["screening_score"] = round(100 * score, 1)
        ranked.append(s)
    ranked.sort(key=lambda s: s["screening_score"], reverse=True)
    return ranked


def _usd(v) -> str:
    if isinstance(v, (int, float)):
        return "$%s" % f"{v:,.0f}"
    return "n/a (no award data)"


def rationale(pair: Dict) -> str:
    """Plain-English rationale for one scored pair."""
    bits = []
    bits.append("%s acquiring %s" % (pair["acquirer_name"], pair["target_name"]))
    shared = pair["shared_concepts_top"]
    if shared:
        bits.append("shares %d technology concepts, including %s" % (
            pair["shared_concept_count"], ", ".join(shared)))
    else:
        bits.append("shares no extracted technology concepts")
    if pair["redundant_pair_count"]:
        bits.append("%d redundant patent pairs suggest overlapping R and D "
                    "that a merger could prune" % pair["redundant_pair_count"])
    gap = pair["gap_concepts_top"]
    if gap:
        bits.append("adds %d capabilities %s lacks, including %s" % (
            pair["gap_concept_count"], pair["acquirer_name"], ", ".join(gap)))
    fy = pair["target_awards_latest_fy"]
    if fy:
        bits.append("brings %s in FY%d federal awards under one roof "
                    "(USAspending.gov, pulled %s)" % (
                        _usd(pair["target_awards_latest_usd"]), fy,
                        pair["awards_provenance"]["target"]))
    return ". ".join(bits) + "."
