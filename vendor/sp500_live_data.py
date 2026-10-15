"""Live-first data for tier 3 of the S&P 500 Corporate Stack.

Tier 3 (the 190 unmapped companies) has $0 routable corporate spend, but it
is not $0 of economic reality. Two public channels quantify it:

1. USAspending.gov (api.usaspending.gov, free, no key): federal obligated
   award dollars per recipient, per fiscal year, via
   /api/v2/search/spending_by_category/recipient/ with a recipient-name
   filter. Federal obligations only; excludes state and local spending.
2. SEC EDGAR companyfacts (data.sec.gov, free, proper User-Agent required):
   net book property value from the latest 10-K Schedule III for REITs:
   gross real-estate carrying amounts (land plus buildings and
   improvements) minus accumulated depreciation. Never presented as
   appraised market value.

Cached JSON (data/gov_awards.json, data/reit_values.json) is fallback only:
used when the network or an API is unreachable, and always labeled with the
cache date. --refresh forces a fresh live pull and rewrites the cache.

Every dollar figure carries its source and date. Estimates are never
presented as exacts.
"""

import csv
import datetime
import json
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

REPO = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(REPO, "data")
AWARDS_CACHE = os.path.join(DATA_DIR, "gov_awards.json")
REIT_CACHE = os.path.join(DATA_DIR, "reit_values.json")
SEC_TICKER_CACHE = os.path.join(DATA_DIR, "sec_company_tickers.json")

USASPENDING = "https://api.usaspending.gov"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK%010d.json"
USER_AGENT = "FrozenInFlames sp500-corporate-stack research contact@example.com"

# Most recent complete federal fiscal years (FY ends Sep 30).
FISCAL_YEARS = [2023, 2024, 2025]

AWARDS_LABEL = (
    "Federal obligated award dollars (contracts, grants, loans, direct "
    "payments and other financial assistance) matched by recipient name. "
    "Federal only; excludes state and local spending."
)
REIT_LABEL = (
    "Net book property value from the latest 10-K Schedule III (gross "
    "real-estate carrying amounts minus accumulated depreciation). "
    "Book value, not an appraised market value."
)

_STOPWORDS = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "companies",
    "ltd", "limited", "llc", "lp", "plc", "sa", "ag", "nv", "group",
    "holdings", "holding", "systems", "system", "technologies", "technology",
    "tech", "international", "global", "industries", "industry", "enterprises",
    "enterprise", "partners", "brands", "foods", "products", "services",
    "the", "and", "&", "of",
}


def distinctive_tokens(name):
    """Lowercase word tokens minus corporate stopwords, for recipient matching."""
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    toks = [w for w in words if w not in _STOPWORDS and len(w) > 1]
    return toks or words


def _post_json(url, payload, timeout=90):
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json",
                 "User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _post_json_retry(url, payload, tries=3, timeout=120):
    last = None
    for i in range(tries):
        try:
            return _post_json(url, payload, timeout=timeout)
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def usaspending_recipient_totals(company_name, fiscal_years=FISCAL_YEARS):
    """Return {fy: obligated_usd} for a company name via recipient grouping.

    Sums the recipient rows whose names contain every distinctive token of
    the company name. Returns (by_year, matched_names, match_method).
    Retries transient failures; a year that still fails records None
    (honest missing, not zero).
    """
    tokens = distinctive_tokens(company_name)
    by_year = {}
    matched = set()
    for fy in fiscal_years:
        payload = {
            "filters": {
                "recipient_search_text": [company_name],
                "award_type_codes": ["A", "B", "C", "D"],
                "time_period": [{
                    "start_date": "%d-10-01" % (fy - 1),
                    "end_date": "%d-09-30" % fy,
                }],
            },
            "limit": 50,
            "page": 1,
        }
        try:
            d = _post_json_retry(
                USASPENDING + "/api/v2/search/spending_by_category/recipient/",
                payload)
        except Exception:
            by_year[fy] = None
            continue
        total = 0.0
        for row in d.get("results", []):
            rname = (row.get("name") or "").lower()
            if all(t in rname for t in tokens):
                total += float(row.get("amount") or 0)
                matched.add(row.get("name") or "")
        by_year[fy] = round(total, 2)
        time.sleep(0.3)
    return by_year, sorted(matched), "recipient-name token match"


def fetch_gov_awards(companies, fiscal_years=FISCAL_YEARS, workers=8):
    """companies: list of (ticker, name). Returns dict keyed by ticker."""
    out = {}

    def one(item):
        ticker, name = item
        try:
            by_year, matched, method = usaspending_recipient_totals(
                name, fiscal_years)
        except Exception as e:  # never let one company kill the pull
            return ticker, {"name": name, "by_year": {},
                            "matched_names": [], "match_method": "error",
                            "error": str(e)[:200]}
        return ticker, {"name": name, "by_year": by_year,
                        "matched_names": matched, "match_method": method}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ticker, rec in ex.map(one, companies):
            out[ticker] = rec
    return out


def _sec_get_json(url):
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def sec_ticker_map():
    """ticker -> CIK, cached to data/sec_company_tickers.json."""
    if os.path.exists(SEC_TICKER_CACHE):
        with open(SEC_TICKER_CACHE) as f:
            return json.load(f)
    d = _sec_get_json(SEC_TICKERS_URL)
    m = {v["ticker"]: v["cik_str"] for v in d.values()}
    with open(SEC_TICKER_CACHE, "w") as f:
        json.dump(m, f)
    return m


def sec_latest_assets(cik):
    """Latest 10-K us-gaap Assets value. Returns (usd, filing_end_date)."""
    facts = _sec_get_json(SEC_FACTS_URL % int(cik))
    units = facts["facts"]["us-gaap"]["Assets"]["units"]["USD"]
    tens = [u for u in units if u.get("form") == "10-K"]
    if not tens:
        raise ValueError("no 10-K Assets fact")
    tens.sort(key=lambda u: u["end"], reverse=True)
    latest = tens[0]
    return float(latest["val"]), latest["end"]


# Schedule III (real estate and accumulated depreciation) XBRL tags.
# The single combined land-and-buildings tag went stale after 2012, so the
# component tags are used instead.
REIT_PROPERTY_TAGS = {
    "land": "RealEstateAndAccumulatedDepreciationCarryingAmountOfLand",
    "buildings": ("RealEstateAndAccumulatedDepreciationCarryingAmountOf"
                   "BuildingsAndImprovements"),
    "depreciation": "RealEstateAccumulatedDepreciation",
}


def _fy_facts_by_end(units):
    """Latest-filed 10-K FY fact per period end. Returns {end: value}."""
    by_end = {}
    for u in units or []:
        if u.get("form") != "10-K" or u.get("fp") != "FY" or not u.get("end"):
            continue
        end = u["end"]
        if end not in by_end or str(u.get("filed", "")) > str(
                by_end[end].get("filed", "")):
            by_end[end] = u
    return {e: float(u["val"]) for e, u in by_end.items()}


def sec_reit_property_value(cik):
    """Net book property value from the latest 10-K Schedule III.

    gross land carrying amount + gross buildings/improvements carrying
    amount - accumulated depreciation, all from the latest common 10-K
    fiscal year-end across the three tags. Returns (usd, end_date).
    Raises ValueError when the tags are absent.
    """
    facts = _sec_get_json(SEC_FACTS_URL % int(cik))
    usgaap = facts.get("facts", {}).get("us-gaap", {})
    series = {}
    for key, tag in REIT_PROPERTY_TAGS.items():
        units = usgaap.get(tag, {}).get("units", {}).get("USD", [])
        s = _fy_facts_by_end(units)
        if not s:
            raise ValueError("no 10-K FY USD fact for %s" % tag)
        series[key] = s
    common = (set(series["land"]) & set(series["buildings"])
              & set(series["depreciation"]))
    if not common:
        raise ValueError("no common 10-K period across property tags")
    end = max(common)
    net = series["land"][end] + series["buildings"][end] \
        - series["depreciation"][end]
    return net, end


def fetch_reit_assets(tickers, workers=6):
    """tickers: list of (ticker, name). Returns dict keyed by ticker.

    Primary figure is the Schedule III net book property value; when the
    property tags are missing, falls back to total assets and records the
    method so the output stays honest.
    """
    tmap = sec_ticker_map()
    out = {}

    def one(item):
        ticker, name = item
        try:
            cik = tmap[ticker]
            try:
                val, end = sec_reit_property_value(cik)
                method = "schedule_iii"
            except Exception:
                val, end = sec_latest_assets(cik)
                method = "total_assets_proxy"
            return ticker, {"name": name, "cik": str(cik).zfill(10),
                            "net_property_value_usd": val,
                            "filing_period_end": end, "form": "10-K",
                            "method": method}
        except Exception as e:
            return ticker, {"name": name, "error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        for ticker, rec in ex.map(one, tickers):
            out[ticker] = rec
            time.sleep(0.1)
    return out


def save_awards_cache(companies_data, fiscal_years=FISCAL_YEARS):
    doc = {
        "source": ("api.usaspending.gov "
                   "/api/v2/search/spending_by_category/recipient/"),
        "label": AWARDS_LABEL,
        "fiscal_years": fiscal_years,
        "pulled_at": (datetime.datetime.now(datetime.timezone.utc)
                      .isoformat()),
        "companies": companies_data,
    }
    with open(AWARDS_CACHE, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return doc


def save_reit_cache(reits_data):
    doc = {
        "source": "SEC EDGAR companyfacts (data.sec.gov)",
        "label": REIT_LABEL,
        "pulled_at": (datetime.datetime.now(datetime.timezone.utc)
                      .isoformat()),
        "reits": reits_data,
    }
    with open(REIT_CACHE, "w") as f:
        json.dump(doc, f, indent=2)
        f.write("\n")
    return doc


def load_awards_cache():
    if not os.path.exists(AWARDS_CACHE):
        return None
    with open(AWARDS_CACHE) as f:
        return json.load(f)


def load_reit_cache():
    if not os.path.exists(REIT_CACHE):
        return None
    with open(REIT_CACHE) as f:
        return json.load(f)


def get_tier3_data(mappings, refresh=False):
    """Live-first tier-3 quantification.

    Returns (data, provenance) where data has 'awards', 'reits',
    'fiscal_years', and provenance is 'live' or 'cached:<pulled_at>'.
    On refresh, rewrites both caches. On network failure, falls back to
    cache and labels it.
    """
    tier3 = [m for m in mappings if m.get("status") == "unmapped"]
    reit_tickers = [(m["ticker"], m["name"]) for m in tier3
                    if m.get("reason_code") == "reit"]
    all_companies = [(m["ticker"], m["name"]) for m in tier3]

    def do_live():
        awards = fetch_gov_awards(all_companies)
        adoc = save_awards_cache(awards)
        reits = fetch_reit_assets(reit_tickers)
        rdoc = save_reit_cache(reits)
        return {"awards": adoc, "reits": rdoc}, "live"

    if not refresh:
        try:
            return do_live()
        except Exception:
            pass  # fall through to cache
    else:
        return do_live()

    adoc = load_awards_cache()
    rdoc = load_reit_cache()
    if adoc is None or rdoc is None:
        raise RuntimeError(
            "live pull failed and no cache exists; "
            "run with --refresh when the network is available")
    stamp = adoc.get("pulled_at", "unknown date")
    return {"awards": adoc, "reits": rdoc}, "cached:" + stamp
