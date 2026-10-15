"""Portfolio merging for M&A-style comparison.

Take two built portfolios (their ``portfolio_data.json`` files) and answer:
where do they overlap, where is each side unique, and which patent pairs are
redundant across the two sides?
"""

from __future__ import annotations

from typing import Any, Dict, List


def _norm(label: str) -> str:
    return " ".join(label.lower().split())


def _concepts_by_label(ontology: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for c in ontology.get("concepts", []):
        out[_norm(c["label"])] = c
    return out


def _cpc_sets(patents: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for p in patents:
        for code in p.get("cpc_inventive", []):
            out.setdefault(code, []).append(p["number"])
    return out


def _patent_concepts(patent_number: str,
                     concepts: Dict[str, Dict[str, Any]]) -> List[str]:
    return [label for label, c in concepts.items()
            if patent_number in c.get("patents", [])]


def compare(portfolio_a: Dict[str, Any],
            portfolio_b: Dict[str, Any]) -> Dict[str, Any]:
    """Compare two portfolios; both are ``portfolio_data`` dicts."""
    pa, pb = portfolio_a["patents"], portfolio_b["patents"]
    oa, ob = portfolio_a["ontology"], portfolio_b["ontology"]
    ca, cb = _concepts_by_label(oa), _concepts_by_label(ob)

    labels_a, labels_b = set(ca), set(cb)
    overlap, unique_a, unique_b = [], [], []
    for label in sorted(labels_a & labels_b):
        overlap.append({
            "label": ca[label]["label"],
            "a_patents": ca[label].get("patents", []),
            "b_patents": cb[label].get("patents", []),
        })
    for label in sorted(labels_a - labels_b):
        unique_a.append({"label": ca[label]["label"],
                         "patents": ca[label].get("patents", [])})
    for label in sorted(labels_b - labels_a):
        unique_b.append({"label": cb[label]["label"],
                         "patents": cb[label].get("patents", [])})

    cpc_a, cpc_b = _cpc_sets(pa), _cpc_sets(pb)
    cpc_overlap = [{"code": code, "a_patents": cpc_a[code],
                    "b_patents": cpc_b[code]}
                   for code in sorted(set(cpc_a) & set(cpc_b))]

    # redundancy: every cross-portfolio patent pair, ranked by shared
    # concepts and shared CPC classes
    pairs = []
    for p in pa:
        a_concepts = set(_patent_concepts(p["number"], ca))
        a_cpc = set(p.get("cpc_inventive", []))
        for q in pb:
            if p["number"] == q["number"]:
                continue
            shared_c = a_concepts & set(_patent_concepts(q["number"], cb))
            shared_x = a_cpc & set(q.get("cpc_inventive", []))
            score = 2 * len(shared_c) + 3 * len(shared_x)
            if score > 0:
                pairs.append({
                    "a_number": p["number"], "a_title": p["title"],
                    "b_number": q["number"], "b_title": q["title"],
                    "shared_concepts": sorted(shared_c),
                    "shared_cpc": sorted(shared_x),
                    "score": score,
                })
    pairs.sort(key=lambda r: r["score"], reverse=True)

    def meta(portfolio: Dict[str, Any]) -> Dict[str, Any]:
        m = portfolio["meta"]
        return {"title": m["title"], "patent_count": m["patent_count"],
                "numbers": m["numbers"]}

    return {
        "a": meta(portfolio_a),
        "b": meta(portfolio_b),
        "concept_overlap": overlap,
        "concepts_unique_to_a": unique_a,
        "concepts_unique_to_b": unique_b,
        "cpc_overlap": cpc_overlap,
        "cpc_unique_to_a": sorted(set(cpc_a) - set(cpc_b)),
        "cpc_unique_to_b": sorted(set(cpc_b) - set(cpc_a)),
        "redundant_pairs": pairs[:25],
        "overlap_concept_count": len(overlap),
        "unique_a_count": len(unique_a),
        "unique_b_count": len(unique_b),
    }
