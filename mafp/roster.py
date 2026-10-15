"""Defense company roster and USPTO assignee matching.

The PPUBS BRS field syntax for assignee names is unreliable through the
web API (quoted AN/ queries return HTTP 500; suffix forms return nothing),
so matching is done the honest, labeled way: a plain-text search per name
variant, then a client-side filter keeping only hits whose assignee name
contains every distinctive token of the variant. This mirrors the
recipient-name token matching the S&P 500 Corporate Stack uses for
USAspending. The variant and method are recorded per company.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Dict, List, Tuple

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROSTER_PATH = os.path.join(REPO, "data", "defense_companies.json")

sys.path.insert(0, os.path.join(REPO, "vendor"))
import sp500_live_data as live_data  # noqa: E402

MIN_HITS = 3


def load_roster() -> Dict:
    with open(ROSTER_PATH) as f:
        return json.load(f)


def _assignee_text(hit: Dict) -> str:
    names = hit.get("assigneeName") or []
    if isinstance(names, str):
        names = [names]
    return " ".join(names).lower()


def assignee_matches(hit: Dict, tokens: List[str]) -> bool:
    """True when the hit's assignee name contains every token."""
    text = _assignee_text(hit)
    return bool(tokens) and all(t in text for t in tokens)


def pick_query(client, company: Dict, limit: int) -> Tuple[str, List[Dict]]:
    """Try name variants in order; use the first with >= MIN_HITS matches.

    Returns (variant_used, matched_hits). The variant and the token filter
    are recorded on the company profile so the match stays labeled.
    """
    best: Tuple[str, List[Dict]] = (company["assignee_queries"][0], [])
    for variant in company["assignee_queries"]:
        try:
            hits = (client.search(variant, page_count=limit * 3)
                    .get("patents") or [])
        except Exception:
            continue
        tokens = live_data.distinctive_tokens(variant)
        matched = [h for h in hits if assignee_matches(h, tokens)][:limit]
        if len(matched) >= MIN_HITS:
            return variant, matched
        if len(matched) > len(best[1]):
            best = (variant, matched)
    return best


MATCH_METHOD = ("USPTO PPUBS text search filtered by assignee-name tokens "
                "(distinctive tokens must all appear in the assignee name)")
