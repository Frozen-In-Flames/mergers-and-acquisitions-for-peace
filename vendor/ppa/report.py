"""Render the portfolio ontology summary as Markdown and HTML."""

from __future__ import annotations

import html as _html
from typing import Any, Dict, List

from .models import Patent


def _esc(s: str) -> str:
    return _html.escape(s or "")


def markdown_report(title: str, patents: List[Patent],
                    ontology: Dict[str, Any]) -> str:
    s = ontology["summary"]
    L: List[str] = [f"# {title}", "",
                    f"**{s['portfolio_size']} patents** analyzed from USPTO records.",
                    ""]
    if s["grant_year_range"]:
        L.append(f"Grant years: {s['grant_year_range'][0]} - "
                 f"{s['grant_year_range'][1]}")
        L.append("")
    L.append("## Portfolio")
    L.append("")
    for p in patents:
        who = ", ".join(p.assignees) if p.assignees else "unassigned"
        L.append(f"- **US {p.number}** ({p.grant_date}) — {p.title} [{who}]")
    L.append("")
    if s["top_assignees"]:
        L.append("## Top assignees")
        L.append("")
        for name, count in s["top_assignees"]:
            L.append(f"- {name}: {count} patent(s)")
        L.append("")
    if s["top_inventors"]:
        L.append("## Top inventors")
        L.append("")
        for name, count in s["top_inventors"]:
            L.append(f"- {name}: {count} patent(s)")
        L.append("")
    L.append("## Technology domains (CPC sections)")
    L.append("")
    for sec in s["cpc_sections"]:
        L.append(f"- **{sec['section']} — {sec['title']}**: "
                 f"{sec['patent_count']} patent(s)")
    L.append("")
    L.append("## Key concepts across the portfolio")
    L.append("")
    for c in s["top_concepts"][:20]:
        alias = f" ({', '.join(c['aliases'])})" if c["aliases"] else ""
        L.append(f"- {c['label']}{alias} — {c['patent_count']} patent(s)")
    L.append("")
    L.append("## Technology clusters")
    L.append("")
    for i, dom in enumerate(s["technology_domains"], 1):
        L.append(f"### Cluster {i}: {', '.join('US ' + n for n in dom['patents'])}")
        if dom["concepts"]:
            L.append(f"Concepts: {', '.join(dom['concepts'])}")
        if dom["cpc"]:
            L.append(f"CPC: {', '.join(dom['cpc'])}")
        L.append("")
    L.append(f"Total backward citations in portfolio: {s['total_citations']}")
    L.append("")
    return "\n".join(L)


def html_report(title: str, patents: List[Patent],
                ontology: Dict[str, Any]) -> str:
    s = ontology["summary"]
    parts: List[str] = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{_esc(title)} — Ontology Summary</title>",
        ("<style>body{font-family:system-ui,sans-serif;max-width:960px;"
         "margin:2rem auto;padding:0 1rem}h1,h2{color:#111}"
         ".tag{display:inline-block;background:#eef;padding:.15rem .5rem;"
         "border-radius:4px;font-size:.8rem;margin:.1rem}"
         "table{border-collapse:collapse;width:100%}"
         "td,th{border:1px solid #ddd;padding:.4rem;text-align:left}</style>"),
        "</head><body>",
        f"<h1>{_esc(title)} — Portfolio Ontology</h1>",
        f"<p>{s['portfolio_size']} patents analyzed from USPTO records.</p>",
        "<h2>Patents</h2><table><tr><th>Patent</th><th>Granted</th>"
        "<th>Title</th><th>Assignee</th></tr>",
    ]
    for p in patents:
        parts.append(
            f"<tr><td>US {_esc(p.number)}</td><td>{_esc(p.grant_date)}</td>"
            f"<td>{_esc(p.title)}</td>"
            f"<td>{_esc(', '.join(p.assignees))}</td></tr>")
    parts.append("</table><h2>Key concepts</h2><p>")
    for c in s["top_concepts"][:30]:
        parts.append(f"<span class='tag'>{_esc(c['label'])} "
                     f"({c['patent_count']})</span>")
    parts.append("</p><h2>Technology domains</h2>")
    for sec in s["cpc_sections"]:
        parts.append(f"<p><b>{_esc(sec['section'])} — "
                     f"{_esc(sec['title'])}</b>: {sec['patent_count']} "
                     "patent(s)</p>")
    parts.append("<h2>Clusters</h2>")
    for i, dom in enumerate(s["technology_domains"], 1):
        parts.append(f"<h3>Cluster {i}</h3><p>Patents: "
                     + ", ".join("US " + _esc(n) for n in dom["patents"])
                     + "</p>")
        if dom["concepts"]:
            parts.append("<p>Concepts: "
                         + ", ".join(_esc(c) for c in dom["concepts"])
                         + "</p>")
    parts.append("</body></html>")
    return "\n".join(parts)


def merger_report(title: str, comparison: Dict[str, Any]) -> str:
    a, b = comparison["a"], comparison["b"]
    L: List[str] = [
        f"# {title}", "",
        f"Comparing **{a['title']}** ({a['patent_count']} patents) "
        f"with **{b['title']}** ({b['patent_count']} patents).", "",
        "## Overlap",
        "",
        f"- Shared concepts: **{comparison['overlap_concept_count']}**",
        f"- Shared CPC classes: **{len(comparison['cpc_overlap'])}**",
        f"- Concepts only in {a['title']}: "
        f"**{comparison['unique_a_count']}**",
        f"- Concepts only in {b['title']}: "
        f"**{comparison['unique_b_count']}**",
        "",
    ]
    if comparison["concept_overlap"]:
        L.append("### Shared concepts (top 20)")
        L.append("")
        for c in comparison["concept_overlap"][:20]:
            L.append(f"- {c['label']} — A: {', '.join('US ' + n for n in c['a_patents'])}; "
                     f"B: {', '.join('US ' + n for n in c['b_patents'])}")
        L.append("")
    if comparison["redundant_pairs"]:
        L.append("## Most redundant cross-portfolio pairs")
        L.append("")
        for r in comparison["redundant_pairs"][:10]:
            L.append(f"- **US {r['a_number']}** ({r['a_title'][:60]}) "
                     f"<-> **US {r['b_number']}** ({r['b_title'][:60]}) "
                     f"[score {r['score']}]")
            if r["shared_concepts"]:
                L.append(f"  shared: {', '.join(r['shared_concepts'][:8])}")
        L.append("")
    else:
        L.append("_No overlapping patents found — the portfolios cover "
                 "distinct territory._")
        L.append("")
    for side, key in ((a["title"], "concepts_unique_to_a"),
                      (b["title"], "concepts_unique_to_b")):
        uniq = comparison[key][:15]
        if uniq:
            L.append(f"## Unique to {side}")
            L.append("")
            L.append(", ".join(c["label"] for c in uniq))
            L.append("")
    return "\n".join(L)
