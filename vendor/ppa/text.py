"""Text helpers: strip the HTML PPUBS returns and split claims."""

from __future__ import annotations

import html as _html
import re
from typing import List, Optional, Tuple

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
# PPUBS inline markup for sub/superscripts, e.g. "CO.SUB.2" -> "CO2"
_MARKUP_RE = re.compile(r"\.(SUB|SUP)\.([A-Za-z0-9]+)")


def strip_html(raw: Optional[str]) -> str:  # type: ignore[name-defined]
    """Remove tags/entities from PPUBS HTML-ish fields."""
    if not raw:
        return ""
    # preserve block boundaries before stripping tags
    text = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    text = re.sub(r"(?i)</p\s*>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = _MARKUP_RE.sub(r"\2", text)
    text = _html.unescape(text)
    # PPUBS sometimes leaves literal "\n" sequences in the JSON strings
    text = text.replace("\\n", "\n").replace("\\t", " ")
    lines = [ln.strip() for ln in text.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    return _WS_RE.sub(" ", text).strip()


_CLAIM_SPLIT_RE = re.compile(r"(?m)^\s*(\d{1,3})\.\s+")


def split_claims(claims_text: str) -> List[Tuple[int, str]]:
    """Split numbered claim text into (number, text) pairs."""
    text = strip_html(claims_text)
    if not text:
        return []
    parts = _CLAIM_SPLIT_RE.split(text)
    # split() with a group: [pre, num, body, num, body, ...]
    claims: List[Tuple[int, str]] = []
    i = 1
    while i + 1 < len(parts):
        try:
            num = int(parts[i])
        except ValueError:
            i += 2
            continue
        body = _WS_RE.sub(" ", parts[i + 1]).strip()
        if body:
            claims.append((num, body))
        i += 2
    # Fallback: if numbering wasn't found but text exists, treat as claim 1
    if not claims and text:
        claims = [(1, _WS_RE.sub(" ", text).strip())]
    return claims


def first_sentence(text: str) -> str:
    text = strip_html(text)
    m = re.search(r"\.\s", text)
    return text[: m.start() + 1] if m else text[:240]
