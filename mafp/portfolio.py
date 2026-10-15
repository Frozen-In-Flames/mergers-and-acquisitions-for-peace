"""Company patent portfolios from USPTO PPUBS, live-first with cache fallback."""

from __future__ import annotations

import sys
import os
from typing import Dict, List, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "vendor"))

from ppa.models import Patent, from_ppubs  # noqa: E402
from ppa.ontology import build_ontology  # noqa: E402
from ppa.uspto import PPUBSClient, USPTOError  # noqa: E402

from mafp import cache  # noqa: E402
from mafp.roster import pick_query  # noqa: E402


def build_portfolio_dict(title: str, patents: List[Patent]) -> Dict:
    """portfolio_data dict in the shape ppa.merge.compare expects."""
    return {
        "meta": {
            "title": title,
            "version": "0.1.0",
            "patent_count": len(patents),
            "numbers": [p.number for p in patents],
        },
        "patents": [p.to_dict() for p in patents],
        "ontology": build_ontology(patents),
    }


def fetch_company_portfolio(company: Dict, limit: int = 10,
                            refresh: bool = False) -> Tuple[Dict, str]:
    """Pull a company's USPTO portfolio. Returns (portfolio_dict, provenance).

    Live-first: queries PPUBS at runtime. On failure, falls back to the
    cached portfolio and labels it with the cache date.
    """
    ticker = company["ticker"]
    if not refresh:
        cached = cache.load("portfolio", ticker)
    else:
        cached = None
    if cached is not None:
        doc, pulled_at = cached
        return doc["payload"], cache.provenance(False, pulled_at)

    client = PPUBSClient()
    try:
        variant_used, hits = pick_query(client, company, limit)
        patents: List[Patent] = []
        for h in hits[:limit]:
            guid = h.get("guid")
            if not guid:
                continue
            try:
                doc = client.get_document(guid)
                doc.setdefault("guid", guid)
                patents.append(from_ppubs(doc))
            except USPTOError:
                continue
        portfolio = build_portfolio_dict(
            "%s patent portfolio" % company["name"], patents)
        portfolio["meta"]["assignee_variant_used"] = variant_used
        portfolio["meta"]["assignee_match_method"] = (
            "USPTO PPUBS text search filtered by assignee-name tokens")
        cache.save("portfolio", ticker, portfolio)
        return portfolio, cache.provenance(True, "")
    except Exception:
        if cached is not None:
            doc, pulled_at = cached
            return doc["payload"], cache.provenance(False, pulled_at)
        raise
    finally:
        client.close()
