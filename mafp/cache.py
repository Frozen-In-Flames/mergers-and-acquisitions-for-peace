"""Cache helpers: live-first data with labeled fallback.

Live pulls are attempted at runtime; when the network or an API is
unreachable, the most recent cached file is used and the output labels it
with the cache date. --refresh forces a fresh pull and rewrites the cache.
"""

from __future__ import annotations

import datetime
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO, "data", "cache")


def _utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save(kind: str, key: str, payload: dict) -> str:
    """Save payload under data/cache/<kind>_<key>.json. Returns path."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, "%s_%s.json" % (kind, key))
    doc = {"pulled_at": _utcnow(), "payload": payload}
    with open(path, "w") as f:
        json.dump(doc, f)
    return path


def load(kind: str, key: str):
    """Load cached doc, or None. Returns (doc, pulled_at)."""
    path = os.path.join(CACHE_DIR, "%s_%s.json" % (kind, key))
    if not os.path.exists(path):
        return None
    with open(path) as f:
        doc = json.load(f)
    return doc, doc.get("pulled_at", "unknown")


def provenance(live_ok: bool, pulled_at: str) -> str:
    if live_ok:
        return "live:" + _utcnow()
    return "cached:" + pulled_at
