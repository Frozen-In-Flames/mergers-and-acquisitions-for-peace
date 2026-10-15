"""Portfolio ontology: concept extraction, CPC taxonomy, knowledge graph.

No heavy ML dependencies — concepts are scored with TF-IDF over 1-3 word
phrases drawn from titles, abstracts and claims, with acronym expansions
("laser detection and ranging (LADAR)") folded in as aliases.
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set, Tuple

from .models import Patent

# --------------------------------------------------------------------- #
# Stopwords / phrase shaping

STOPWORDS = {
    "a", "an", "the", "and", "or", "of", "to", "in", "for", "with", "by",
    "on", "at", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "it", "its", "this", "that", "these", "those", "which", "who",
    "whom", "what", "where", "when", "how", "such", "than", "then", "there",
    "their", "they", "them", "he", "she", "we", "you", "i", "my", "our",
    "your", "his", "her", "said", "comprising", "comprises", "comprised",
    "including", "includes", "included", "having", "wherein", "whereby",
    "thereof", "thereto", "therein", "thereby", "configured", "adapted",
    "operative", "plurality", "one", "two", "three", "first", "second",
    "third", "each", "other", "another", "more", "most", "less", "least",
    "between", "within", "without", "upon", "into", "over", "under", "above",
    "below", "about", "against", "during", "before", "after", "can", "may",
    "might", "will", "would", "should", "could", "shall", "must", "do",
    "does", "did", "not", "no", "nor", "so", "but", "if", "else", "all",
    "any", "both", "few", "own", "same", "too", "very", "just", "also",
    "new", "novel", "improved", "method", "methods", "system", "systems",
    "apparatus", "device", "devices", "process", "use", "used", "using",
    "based", "via", "per", "etc", "eg", "ie", "fig", "figs",
    "claim", "claims", "invention", "embodiment", "embodiments",
    "according", "respectively", "thereby", "therein",
}

_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9\-]*")
_ACRONYM_RE = re.compile(
    r"\b((?:[a-z][a-z0-9\-]*\s+){0,4}[a-z][a-z0-9\-]*)"
    r"\s+\(([A-Z][A-Z0-9]{1,9})\)")


def _tokens(text: str) -> List[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def _candidate_phrases(text: str, max_n: int = 3) -> List[str]:
    toks = _tokens(text)
    phrases: List[str] = []
    for n in range(1, max_n + 1):
        for i in range(len(toks) - n + 1):
            gram = toks[i: i + n]
            if gram[0] in STOPWORDS or gram[-1] in STOPWORDS:
                continue
            if any(t in STOPWORDS and len(t) <= 2 for t in gram):
                continue
            if all(len(t) <= 1 for t in gram):
                continue
            phrases.append(" ".join(gram))
    return phrases


def extract_acronyms(texts: List[str]) -> Dict[str, str]:
    """Map ACRONYM -> expansion, e.g. LADAR -> laser detection and ranging."""
    out: Dict[str, str] = {}
    for text in texts:
        for m in _ACRONYM_RE.finditer(text):
            expansion, acronym = m.group(1).strip().lower(), m.group(2)
            if expansion and acronym not in out:
                out[acronym] = expansion
    return out


# --------------------------------------------------------------------- #
# Concept extraction

@dataclass
class Concept:
    label: str
    score: float
    patents: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)


def extract_concepts(patents: List[Patent],
                     per_patent: int = 25,
                     max_concepts: int = 120) -> List[Concept]:
    """TF-IDF keyphrase extraction across the portfolio."""
    if not patents:
        return []

    def doc_text(p: Patent) -> str:
        parts = [p.title, p.abstract]
        parts.extend(c["text"] for c in p.claims[:12])
        return " ".join(parts)

    texts = {p.number: doc_text(p) for p in patents}
    acronyms = extract_acronyms(list(texts.values()))

    # document frequency of each phrase across the portfolio
    df: Counter = Counter()
    tf: Dict[str, Counter] = {}
    for num, text in texts.items():
        phrases = _candidate_phrases(text, max_n=4)
        c = Counter(phrases)
        tf[num] = c
        for ph in c:
            df[ph] += 1

    n_docs = len(patents)
    scored: Dict[str, Dict[str, Any]] = {}
    for num, c in tf.items():
        # title boost: phrases from the title count double
        title_phrases = set(_candidate_phrases(texts[num].split(".")[0],
                                               max_n=4))
        total = sum(c.values()) or 1
        for ph, count in c.items():
            idf = math.log((n_docs + 1) / (df[ph] + 0.5)) + 1.0
            boost = 1.6 if ph in title_phrases else 1.0
            length_bonus = 1.0 + 0.15 * (len(ph.split()) - 1)
            s = (count / total) * idf * boost * length_bonus
            entry = scored.setdefault(
                ph, {"score": 0.0, "patents": set(), "tfidf": 0.0})
            entry["score"] += s
            entry["patents"].add(num)

    concepts: List[Concept] = []
    for label, e in scored.items():
        # drop subsumed phrases: "detection" when "quadrature detection" wins
        concepts.append(Concept(label=label, score=e["score"],
                                patents=sorted(e["patents"])))
    concepts.sort(key=lambda c: c.score, reverse=True)

    # fold acronyms in as aliases of their expansion concept, and also
    # index each acronym as a first-class concept (LADAR, PCR, ...),
    # ranked right beside its expansion
    by_label = {c.label: c for c in concepts}
    pending: List[Concept] = []
    for acro, expansion in acronyms.items():
        if expansion in by_label and acro not in by_label:
            base = by_label[expansion]
            if acro not in base.aliases:
                base.aliases.append(acro)
            pending.append(Concept(label=acro, score=base.score,
                                   patents=list(base.patents),
                                   aliases=[expansion]))
    # drop case-variant duplicates (e.g. lowercase "ladar") before indexing
    drop = {c.label.lower() for c in pending}
    concepts[:] = [c for c in concepts if c.label.lower() not in drop]
    by_label = {c.label: c for c in concepts}
    insertions = []
    for concept in pending:
        base = by_label.get(concept.aliases[0])
        if base is not None:
            insertions.append((concepts.index(base), concept))
    for idx, concept in sorted(insertions, reverse=True):
        concepts.insert(idx + 1, concept)

    # prune phrases fully contained in a much stronger longer phrase
    pruned: List[Concept] = []
    labels = {c.label for c in concepts[:max_concepts * 2]}
    for c in concepts:
        words = c.label.split()
        if len(words) == 1:
            longer = [o for o in concepts
                      if o is not c and o.score > c.score * 1.4
                      and c.label in o.label.split() and o.label in labels]
            if longer:
                continue
        pruned.append(c)
        if len(pruned) >= max_concepts:
            break
    return pruned


# --------------------------------------------------------------------- #
# CPC taxonomy

CPC_SECTIONS = {
    "A": "Human Necessities",
    "B": "Performing Operations; Transporting",
    "C": "Chemistry; Metallurgy",
    "D": "Textiles; Paper",
    "E": "Fixed Constructions",
    "F": "Mechanical Engineering; Lighting; Heating; Weapons",
    "G": "Physics",
    "H": "Electricity",
    "Y": "General Tagging of New Technological Developments",
}

_CPC_RE = re.compile(r"^([A-HY])(\d{2})([A-Z])(\d+)?(?:/(\d+))?")


def parse_cpc(code: str) -> Dict[str, str]:
    m = _CPC_RE.match(code.strip().upper())
    if not m:
        return {"code": code, "section": "", "class": "",
                "subclass": "", "group": ""}
    section, cls, sub = m.group(1), m.group(1) + m.group(2), \
        m.group(1) + m.group(2) + m.group(3)
    group = (m.group(4) or "") + ("/" + m.group(5) if m.group(5) else "")
    return {"code": code, "section": section, "class": cls,
            "subclass": sub, "group": group}


def build_cpc_taxonomy(patents: List[Patent]) -> Dict[str, Any]:
    tree: Dict[str, Any] = {"sections": {}}
    for p in patents:
        for code in p.cpc_inventive + p.cpc_additional:
            parsed = parse_cpc(code)
            if not parsed["section"]:
                continue
            sec = tree["sections"].setdefault(parsed["section"], {
                "title": CPC_SECTIONS.get(parsed["section"], ""),
                "patents": set(), "classes": {}})
            sec["patents"].add(p.number)
            cls = sec["classes"].setdefault(parsed["class"],
                                            {"patents": set(),
                                             "subclasses": {}})
            cls["patents"].add(p.number)
            sub = cls["subclasses"].setdefault(
                parsed["subclass"],
                {"code": parsed["subclass"], "patents": set(), "groups": {}})
            sub["patents"].add(p.number)
            if parsed["group"]:
                sub["groups"].setdefault(parsed["group"], set()).add(p.number)
    # sets -> sorted lists for JSON
    for sec in tree["sections"].values():
        sec["patents"] = sorted(sec["patents"])
        for cls in sec["classes"].values():
            cls["patents"] = sorted(cls["patents"])
            for sub in cls["subclasses"].values():
                sub["patents"] = sorted(sub["patents"])
                sub["groups"] = {g: sorted(ns)
                                 for g, ns in sub["groups"].items()}
    return tree


# --------------------------------------------------------------------- #
# Knowledge graph + summary

def _slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")


def build_graph(patents: List[Patent],
                concepts: List[Concept]) -> Dict[str, Any]:
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for p in patents:
        nodes.append({"id": f"patent:{p.number}", "type": "patent",
                      "label": f"US {p.number}", "title": p.title})
        for code in p.cpc_inventive:
            nodes.append({"id": f"cpc:{code}", "type": "cpc", "label": code})
            edges.append({"from": f"patent:{p.number}", "to": f"cpc:{code}",
                          "rel": "classified_as"})
        for cite in p.citations:
            if cite.number:
                nodes.append({"id": f"patent:{cite.number}",
                              "type": "patent", "label": f"US {cite.number}",
                              "title": cite.name, "external": True})
                edges.append({"from": f"patent:{p.number}",
                              "to": f"patent:{cite.number}",
                              "rel": "cites"})
    for c in concepts:
        cid = f"concept:{_slug(c.label)}"
        nodes.append({"id": cid, "type": "concept", "label": c.label,
                      "aliases": c.aliases, "score": round(c.score, 4)})
        for num in c.patents:
            edges.append({"from": f"patent:{num}", "to": cid,
                          "rel": "mentions"})
    # de-duplicate nodes
    seen, uniq = set(), []
    for n in nodes:
        if n["id"] not in seen:
            seen.add(n["id"])
            uniq.append(n)
    # co-occurrence edges between concepts sharing patents
    by_patent: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        if e["rel"] == "mentions":
            by_patent[e["from"]].append(e["to"])
    co: Counter = Counter()
    for cids in by_patent.values():
        for i in range(len(cids)):
            for j in range(i + 1, len(cids)):
                co[tuple(sorted((cids[i], cids[j])))] += 1
    for (a, b), w in co.most_common(60):
        edges.append({"from": a, "to": b, "rel": "co_occurs",
                      "weight": w})
    return {"nodes": uniq, "edges": edges}


def summarize(patents: List[Patent], concepts: List[Concept],
              taxonomy: Dict[str, Any]) -> Dict[str, Any]:
    assignees: Counter = Counter()
    inventors: Counter = Counter()
    years: List[str] = []
    for p in patents:
        assignees.update(p.assignees)
        inventors.update(p.inventors)
        if p.grant_date:
            years.append(p.grant_date[:4])

    # technology domains: group patents sharing CPC subclasses or concepts
    parent: Dict[str, str] = {}

    def find(x: str) -> str:
        while parent.get(x, x) != x:
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for p in patents:
        parent.setdefault(p.number, p.number)
    sub_to_patents: Dict[str, Set[str]] = defaultdict(set)
    for p in patents:
        for code in p.cpc_inventive:
            sub_to_patents[parse_cpc(code)["subclass"]].add(p.number)
    for nums in sub_to_patents.values():
        nums = list(nums)
        for other in nums[1:]:
            union(nums[0], other)
    for c in concepts[:40]:
        if len(c.patents) > 1:
            for other in c.patents[1:]:
                union(c.patents[0], other)
    clusters: Dict[str, List[str]] = defaultdict(list)
    for p in patents:
        clusters[find(p.number)].append(p.number)
    domains = []
    for members in sorted(clusters.values(), key=len, reverse=True):
        dom_concepts = [c.label for c in concepts
                        if set(c.patents) & set(members)][:6]
        dom_cpc = sorted({code for p in patents if p.number in members
                          for code in p.cpc_inventive})[:6]
        domains.append({"patents": sorted(members),
                        "concepts": dom_concepts, "cpc": dom_cpc})

    sections = [
        {"section": s, "title": v["title"], "patents": v["patents"],
         "patent_count": len(v["patents"])}
        for s, v in taxonomy["sections"].items()]
    sections.sort(key=lambda x: x["patent_count"], reverse=True)

    return {
        "portfolio_size": len(patents),
        "grant_year_range": [min(years), max(years)] if years else [],
        "top_assignees": assignees.most_common(10),
        "top_inventors": inventors.most_common(10),
        "cpc_sections": sections,
        "top_concepts": [{"label": c.label, "score": round(c.score, 4),
                          "aliases": c.aliases,
                          "patent_count": len(c.patents),
                          "patents": c.patents}
                         for c in concepts[:30]],
        "technology_domains": domains,
        "total_citations": sum(len(p.citations) for p in patents),
    }


def build_ontology(patents: List[Patent]) -> Dict[str, Any]:
    concepts = extract_concepts(patents)
    taxonomy = build_cpc_taxonomy(patents)
    graph = build_graph(patents, concepts)
    summary = summarize(patents, concepts, taxonomy)
    return {
        "concepts": [
            {"label": c.label, "score": round(c.score, 4),
             "aliases": c.aliases, "patents": c.patents}
            for c in concepts],
        "cpc_taxonomy": taxonomy,
        "graph": graph,
        "summary": summary,
    }
