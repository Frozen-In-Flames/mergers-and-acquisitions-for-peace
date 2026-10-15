"""Federal award dollars per company, via the S&P 500 Corporate Stack engine.

Reuses vendor/sp500_live_data.py (copied from the sp500-corporate-stack
repo, v0.4.x): USAspending.gov recipient-name matching, live-first with
cache fallback. Every figure carries its source and pull date.
"""

from __future__ import annotations

import sys
import os
from typing import Dict, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "vendor"))

import sp500_live_data as live_data  # noqa: E402

from mafp import cache  # noqa: E402

SOURCE_LABEL = (
    "Federal obligated award dollars (contracts, grants, loans, direct "
    "payments and other financial assistance), USAspending.gov "
    "/api/v2/search/spending_by_category/recipient/, matched by recipient "
    "name. Federal only; excludes state and local spending."
)


def fetch_company_awards(company: Dict, fiscal_years=(2023, 2024, 2025),
                         refresh: bool = False) -> Tuple[Dict, str]:
    """Pull a company's federal awards. Returns (awards_dict, provenance)."""
    ticker = company["ticker"]
    if not refresh:
        cached = cache.load("awards", ticker)
    else:
        cached = None
    if cached is not None:
        doc, pulled_at = cached
        return doc["payload"], cache.provenance(False, pulled_at)

    try:
        by_year, matched, method = live_data.usaspending_recipient_totals(
            company["name"], list(fiscal_years))
        awards = {
            "ticker": ticker,
            "name": company["name"],
            "by_year": {str(k): v for k, v in by_year.items()},
            "matched_recipient_names": matched,
            "match_method": method,
            "source": SOURCE_LABEL,
        }
        cache.save("awards", ticker, awards)
        return awards, cache.provenance(True, "")
    except Exception:
        if cached is not None:
            doc, pulled_at = cached
            return doc["payload"], cache.provenance(False, pulled_at)
        raise
