"""Generate a runnable FastAPI application for a patent portfolio.

Each patent in the portfolio gets its own family of REST endpoints
(``/api/v1/patents/{number}/...``) — i.e. every patent becomes an API —
plus portfolio-level ontology endpoints.  The generator writes a
self-contained ``portfolio_api.py`` (data embedded next to it in
``portfolio_data.json``), an ``openapi.json`` spec and a small HTML UI.
"""

from __future__ import annotations

import importlib.util
import json
import os
from typing import Any, Dict, List

APP_TEMPLATE = '''"""Generated Patent Portfolio API — do not edit by hand.

Regenerate with:  python cli.py build <patent numbers> --out <dir>
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "portfolio_data.json")) as fh:
    DATA: Dict[str, Any] = json.load(fh)

PATENTS: Dict[str, Dict[str, Any]] = {p["number"]: p for p in DATA["patents"]}
ONTOLOGY: Dict[str, Any] = DATA["ontology"]

app = FastAPI(
    title=DATA["meta"]["title"],
    description="Per-patent REST APIs plus portfolio ontology for a USPTO patent portfolio.",
    version=DATA["meta"]["version"],
)


def _patent_or_404(number: str) -> Dict[str, Any]:
    p = PATENTS.get(number)
    if not p:
        raise HTTPException(status_code=404, detail=f"patent {{number}} not in portfolio")
    return p


@app.get("/api/v1/portfolio", tags=["portfolio"])
def get_portfolio() -> Dict[str, Any]:
    """Portfolio metadata and patent list."""
    return {"meta": DATA["meta"],
            "patents": [{"number": p["number"], "title": p["title"],
                         "grant_date": p["grant_date"],
                         "assignees": p["assignees"]} for p in DATA["patents"]]}


@app.get("/api/v1/patents", tags=["patents"])
def list_patents() -> List[Dict[str, Any]]:
    """List every patent in the portfolio (full records)."""
    return DATA["patents"]


@app.get("/api/v1/patents/{number}", tags=["patents"])
def get_patent(number: str) -> Dict[str, Any]:
    """Full record for one patent — its API root."""
    return _patent_or_404(number)


@app.get("/api/v1/patents/{number}/claims", tags=["patents"])
def get_claims(number: str) -> Dict[str, Any]:
    p = _patent_or_404(number)
    return {"number": number, "claim_count": p["claim_count"], "claims": p["claims"]}


@app.get("/api/v1/patents/{number}/abstract", tags=["patents"])
def get_abstract(number: str) -> Dict[str, str]:
    p = _patent_or_404(number)
    return {"number": number, "abstract": p["abstract"]}


@app.get("/api/v1/patents/{number}/description", tags=["patents"])
def get_description(number: str) -> Dict[str, str]:
    p = _patent_or_404(number)
    return {"number": number, "description": p["description"]}


@app.get("/api/v1/patents/{number}/citations", tags=["patents"])
def get_citations(number: str) -> Dict[str, Any]:
    p = _patent_or_404(number)
    return {"number": number, "citations": p["citations"],
            "foreign_citations": p["foreign_citations"]}


@app.get("/api/v1/patents/{number}/classifications", tags=["patents"])
def get_classifications(number: str) -> Dict[str, Any]:
    p = _patent_or_404(number)
    return {"number": number, "cpc_inventive": p["cpc_inventive"],
            "cpc_additional": p["cpc_additional"], "ipc": p["ipc"],
            "us_classes": p["us_classes"]}


@app.get("/api/v1/patents/{number}/parties", tags=["patents"])
def get_parties(number: str) -> Dict[str, Any]:
    p = _patent_or_404(number)
    return {"number": number, "inventors": p["inventors"],
            "assignees": p["assignees"], "applicants": p["applicants"],
            "examiner": p["examiner"]}


@app.get("/api/v1/portfolio/ontology", tags=["ontology"])
def get_ontology() -> Dict[str, Any]:
    """Full portfolio ontology: concepts, CPC taxonomy, knowledge graph."""
    return ONTOLOGY


@app.get("/api/v1/portfolio/ontology/summary", tags=["ontology"])
def get_ontology_summary() -> Dict[str, Any]:
    """Human-readable summary of the portfolio ontology."""
    return ONTOLOGY["summary"]


@app.get("/api/v1/portfolio/ontology/concepts", tags=["ontology"])
def list_concepts(limit: int = Query(30, ge=1, le=500)) -> List[Dict[str, Any]]:
    return ONTOLOGY["concepts"][:limit]


@app.get("/api/v1/search", tags=["portfolio"])
def search(q: str = Query(..., min_length=2)) -> List[Dict[str, Any]]:
    """Full-text search across the portfolio (title, abstract, claims)."""
    needle = q.lower()
    hits = []
    for p in DATA["patents"]:
        hay = " ".join([p["title"], p["abstract"]] +
                       [c["text"] for c in p["claims"]]).lower()
        if needle in hay:
            hits.append({"number": p["number"], "title": p["title"]})
    return hits


@app.get("/api/v1/merge/summary", tags=["merge"])
def merge_summary() -> Dict[str, Any]:
    """M&A comparison summary (only present on merged portfolios)."""
    m = DATA.get("merge")
    if not m:
        raise HTTPException(status_code=404, detail="not a merged portfolio")
    return {"a": m["a"], "b": m["b"],
            "overlap_concept_count": m["overlap_concept_count"],
            "unique_a_count": m["unique_a_count"],
            "unique_b_count": m["unique_b_count"],
            "cpc_overlap": m["cpc_overlap"]}


@app.get("/api/v1/merge/concept-overlap", tags=["merge"])
def merge_concept_overlap() -> List[Dict[str, Any]]:
    m = DATA.get("merge")
    if not m:
        raise HTTPException(status_code=404, detail="not a merged portfolio")
    return m["concept_overlap"]


@app.get("/api/v1/merge/redundant-pairs", tags=["merge"])
def merge_redundant_pairs(limit: int = Query(10, ge=1, le=25)) -> List[Dict[str, Any]]:
    m = DATA.get("merge")
    if not m:
        raise HTTPException(status_code=404, detail="not a merged portfolio")
    return m["redundant_pairs"][:limit]


@app.get("/api/v1/merge/gaps", tags=["merge"])
def merge_gaps() -> Dict[str, Any]:
    """Concepts and CPC classes unique to each side."""
    m = DATA.get("merge")
    if not m:
        raise HTTPException(status_code=404, detail="not a merged portfolio")
    return {"unique_to_a": m["concepts_unique_to_a"],
            "unique_to_b": m["concepts_unique_to_b"],
            "cpc_unique_to_a": m["cpc_unique_to_a"],
            "cpc_unique_to_b": m["cpc_unique_to_b"]}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    path = os.path.join(HERE, "index.html")
    with open(path) as fh:
        return fh.read()
'''

INDEX_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>__TITLE__ — Patent Portfolio API</title>
<style>
body{font-family:system-ui,sans-serif;max-width:960px;margin:2rem auto;padding:0 1rem;color:#1a1a1a}
.card{border:1px solid #ddd;border-radius:8px;padding:1rem;margin:0.75rem 0}
.tag{display:inline-block;background:#eef;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.8rem;margin:0.1rem}
a{color:#0b5fff} code{background:#f4f4f4;padding:0.1rem 0.3rem;border-radius:3px}
</style></head><body>
<h1>__TITLE__</h1>
<p>__COUNT__ patents. Every patent is its own REST API. Interactive docs: <a href="/docs">/docs</a></p>
<h2>Patents</h2>
<div id="patents"></div>
<h2>Top concepts</h2>
<div id="concepts"></div>
<h2>Try it</h2>
<p><code>GET /api/v1/patents/{number}/claims</code> &middot;
<code>GET /api/v1/portfolio/ontology/summary</code> &middot;
<code>GET /api/v1/search?q=laser</code></p>
<script>
fetch('/api/v1/portfolio').then(r=>r.json()).then(d=>{
  document.getElementById('patents').innerHTML = d.patents.map(p=>
    `<div class="card"><b>US ${p.number}</b> — ${p.title}<br>
     <span class="tag">${p.grant_date||''}</span>
     ${(p.assignees||[]).map(a=>`<span class="tag">${a}</span>`).join('')}
     <br><a href="/api/v1/patents/${p.number}">API root</a> ·
     <a href="/api/v1/patents/${p.number}/claims">claims</a> ·
     <a href="/api/v1/patents/${p.number}/citations">citations</a></div>`).join('');
});
fetch('/api/v1/portfolio/ontology/concepts?limit=20').then(r=>r.json()).then(cs=>{
  document.getElementById('concepts').innerHTML = cs.map(c=>
    `<span class="tag">${c.label} (${c.patents.length})</span>`).join('');
});
</script></body></html>
"""


def generate(out_dir: str, portfolio_data: Dict[str, Any]) -> Dict[str, str]:
    """Write the generated server, data, OpenAPI spec and UI. Returns paths."""
    os.makedirs(out_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    data_path = os.path.join(out_dir, "portfolio_data.json")
    with open(data_path, "w") as fh:
        json.dump(portfolio_data, fh, indent=1)
    paths["data"] = data_path

    app_path = os.path.join(out_dir, "portfolio_api.py")
    with open(app_path, "w") as fh:
        fh.write(APP_TEMPLATE)
    paths["app"] = app_path

    index_path = os.path.join(out_dir, "index.html")
    with open(index_path, "w") as fh:
        fh.write(INDEX_TEMPLATE
                 .replace("__TITLE__", portfolio_data["meta"]["title"])
                 .replace("__COUNT__",
                          str(portfolio_data["meta"]["patent_count"])))
    paths["index"] = index_path

    # Build the OpenAPI spec by importing the generated app.
    spec = importlib.util.spec_from_file_location("portfolio_api", app_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    openapi_path = os.path.join(out_dir, "openapi.json")
    with open(openapi_path, "w") as fh:
        json.dump(module.app.openapi(), fh, indent=1)
    paths["openapi"] = openapi_path
    return paths
