"""Normalized patent record built from a raw PPUBS document."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .text import split_claims, strip_html


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    text = str(value).strip()
    return [text] if text else []


def _split_codes(value: Any) -> List[str]:
    out: List[str] = []
    for item in _as_list(value):
        out.extend(c.strip() for c in str(item).replace(",", ";").split(";")
                   if c.strip())
    # de-duplicate, preserve order
    seen, uniq = set(), []
    for code in out:
        if code not in seen:
            seen.add(code)
            uniq.append(code)
    return uniq


@dataclass
class Citation:
    raw: str
    number: str = ""
    kind: str = ""
    name: str = ""
    date: str = ""
    cited_by: str = ""
    country: str = "US"


_CITE_RE = None


def _parse_citation(raw: str) -> "Citation":
    import re

    global _CITE_RE
    if _CITE_RE is None:
        _CITE_RE = re.compile(
            r"^(?P<country>[A-Z]{2})\s+(?P<number>[\d/,]+)\s*"
            r"(?P<kind>[A-Z]\d?)?\s*(?P<rest>.*)$")
    cite = Citation(raw=raw)
    m = _CITE_RE.match(raw.strip())
    if m:
        cite.country = m.group("country")
        cite.number = m.group("number").replace(",", "").replace("/", "")
        cite.kind = (m.group("kind") or "").strip()
        rest = (m.group("rest") or "").strip()
        low = rest.lower()
        if "cited by examiner" in low:
            cite.cited_by = "examiner"
            rest = rest[: low.index("cited by examiner")].strip()
        elif "cited by applicant" in low:
            cite.cited_by = "applicant"
            rest = rest[: low.index("cited by applicant")].strip()
        # trailing token that looks like YYYYMM is usually the date
        parts = rest.rsplit(" ", 1)
        if len(parts) == 2 and parts[1].isdigit() and len(parts[1]) == 6:
            cite.date, cite.name = parts[1], parts[0].strip()
        else:
            cite.name = rest
    return cite


@dataclass
class Patent:
    number: str
    kind_code: str = ""
    title: str = ""
    abstract: str = ""
    claims: List[Dict[str, Any]] = field(default_factory=list)
    claim_count: int = 0
    description: str = ""
    inventors: List[str] = field(default_factory=list)
    assignees: List[str] = field(default_factory=list)
    applicants: List[str] = field(default_factory=list)
    filing_date: str = ""
    grant_date: str = ""
    application_number: str = ""
    cpc_inventive: List[str] = field(default_factory=list)
    cpc_additional: List[str] = field(default_factory=list)
    ipc: List[str] = field(default_factory=list)
    us_classes: List[str] = field(default_factory=list)
    citations: List[Citation] = field(default_factory=list)
    foreign_citations: List[Citation] = field(default_factory=list)
    family_members: List[Dict[str, str]] = field(default_factory=list)
    examiner: str = ""
    guid: str = ""
    uspto_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


def patent_from_dict(d: Dict[str, Any]) -> Patent:
    """Rebuild a Patent from ``to_dict()`` output (e.g. merged portfolios)."""
    p = Patent(number=str(d.get("number", "")))
    for key in Patent.__dataclass_fields__:
        if key == "number" or key not in d:
            continue
        if key == "citations":
            p.citations = [Citation(**c) for c in d["citations"]]
        elif key == "foreign_citations":
            p.foreign_citations = [Citation(**c) for c in d["foreign_citations"]]
        else:
            setattr(p, key, d[key])
    return p


def _norm_name(name: str) -> str:
    """'Last; First' -> 'First Last'."""
    parts = [p.strip() for p in name.split(";")]
    if len(parts) == 2 and parts[0] and parts[1]:
        return f"{parts[1]} {parts[0]}"
    return name.strip()


def from_ppubs(doc: Dict[str, Any]) -> Patent:
    """Normalize a raw PPUBS full-document dict into a Patent."""
    number = str(doc.get("publicationReferenceDocumentNumber")
                 or doc.get("pubRefDocNumber") or "").strip()
    claims = [{"number": n, "text": t}
              for n, t in split_claims(doc.get("claimsHtml") or "")]
    title = strip_html(doc.get("inventionTitle") or "")
    if title.upper() == "TEXT NOT AVAILABLE":
        # very old patents with no OCR text — treat as missing, not content
        title = ""

    p = Patent(
        number=number,
        kind_code=(_as_list(doc.get("kindCode")) or [""])[0],
        title=title,
        abstract=strip_html(doc.get("abstractHtml") or ""),
        claims=claims,
        description=strip_html(doc.get("descriptionHtml") or ""),
        inventors=[_norm_name(n) for n in _as_list(doc.get("inventorsName"))],
        assignees=_as_list(doc.get("assigneeName")),
        applicants=_as_list(doc.get("applicantName")),
        application_number=str(doc.get("applicationNumber") or ""),
        cpc_inventive=_split_codes(doc.get("cpcInventiveFlattened")),
        cpc_additional=_split_codes(doc.get("cpcAdditionalFlattened")),
        ipc=_split_codes(doc.get("ipcCodeFlattened")),
        us_classes=_split_codes(doc.get("uspcFullClassificationFlattened")),
        examiner=str(doc.get("primaryExaminer") or ""),
        guid=str(doc.get("guid") or ""),
    )
    # dates: PPUBS returns lists like ["2015-03-10T00:00:00Z"]
    filing = _as_list(doc.get("applicationFilingDate"))
    p.filing_date = filing[0][:10] if filing else ""
    grant = str(doc.get("datePublished") or "")
    p.grant_date = grant[:10]

    try:
        p.claim_count = int(str(doc.get("numberOfClaims") or 0))
    except ValueError:
        p.claim_count = len(claims)
    if not p.claim_count:
        p.claim_count = len(claims)

    p.citations = [_parse_citation(r) for r in _as_list(doc.get("usRefGroup"))]
    p.foreign_citations = [_parse_citation(r)
                           for r in _as_list(doc.get("foreignRefGroup"))]

    for m in _as_list(doc.get("patentFamilyDocNumber")):
        p.family_members.append({"document": m})

    if number:
        digits = "".join(c for c in number if c.isdigit())
        p.uspto_url = (f"https://ppubs.uspto.gov/pubwebapp/external.html"
                       f"?documentId={digits}")
    return p
