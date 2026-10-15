#!/usr/bin/env python3
"""Mergers and Acquisitions For Peace: acquisition screening for defense
capability.

For each defense-relevant S&P 500 company, pulls a live USPTO patent
portfolio and live federal award dollars, then scores acquirer/target pairs
on shared patent concepts, redundant IP, capability gaps closed, and
contract dollars at stake.

Usage:
    python3 analyze.py --sector defense [--acquirer LMT] [--format json]
    python3 analyze.py --companies LMT,RTX,GD --limit 8 --refresh
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from mafp import __version__, awards, cache, portfolio, roster, scoring  # noqa: E402


def build_profile(company, limit, refresh):
    """Pull one company's portfolio + awards. Returns profile dict."""
    port, port_prov = portfolio.fetch_company_portfolio(
        company, limit=limit, refresh=refresh)
    awd, awd_prov = awards.fetch_company_awards(company, refresh=refresh)
    return {
        "ticker": company["ticker"],
        "name": company["name"],
        "portfolio": port,
        "awards": awd,
        "provenance": port_prov,
        "awards_provenance": awd_prov,
    }


def print_text(ranked, args):
    print("Mergers and Acquisitions For Peace v%s" % __version__)
    print("Sector: %s | pairs scored: %d" % (args.sector, len(ranked)))
    print("Screening scores are 0-100 and are not valuations or advice.")
    print()
    for i, p in enumerate(ranked[: args.top], 1):
        print("%d. %s -> %s  score %.1f" % (
            i, p["acquirer"], p["target"], p["screening_score"]))
        print("   %s" % scoring.rationale(p))
        print("   parts: overlap %.2f | redundancy %.2f | gap %.2f | awards %.2f"
              % (p["score_parts"]["concept_overlap"],
                 p["score_parts"]["redundancy"],
                 p["score_parts"]["gap_closure"],
                 p["score_parts"]["award_scale"]))
        print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Mergers and Acquisitions For Peace: rank defense "
                    "acquisition pairs by patent overlap and federal awards.")
    ap.add_argument("--sector", default="defense",
                    help="company sector roster to use (default: defense)")
    ap.add_argument("--acquirer", default=None,
                    help="ticker of the acquirer; all others become targets "
                         "(default: score every ordered pair)")
    ap.add_argument("--companies", default=None,
                    help="comma-separated tickers to include, e.g. LMT,RTX,GD")
    ap.add_argument("--limit", type=int, default=10,
                    help="patents pulled per company portfolio (default: 10)")
    ap.add_argument("--top", type=int, default=10,
                    help="pairs shown in text output (default: 10)")
    ap.add_argument("--refresh", action="store_true",
                    help="force fresh live pulls and rewrite the cache")
    ap.add_argument("--format", choices=["text", "json"], default="text")
    args = ap.parse_args(argv)

    roster_data = roster.load_roster()
    companies = roster_data["companies"]
    if args.companies:
        want = {t.strip().upper() for t in args.companies.split(",")}
        companies = [c for c in companies if c["ticker"] in want]
    if not companies:
        print("no companies selected", file=sys.stderr)
        return 1

    profiles = {}
    for c in companies:
        print("pulling %s ..." % c["ticker"], file=sys.stderr)
        try:
            profiles[c["ticker"]] = build_profile(c, args.limit, args.refresh)
        except Exception as e:
            print("  !! %s failed: %s" % (c["ticker"], e), file=sys.stderr)

    tickers = list(profiles.keys())
    if args.acquirer:
        acq = args.acquirer.upper()
        if acq not in profiles:
            print("acquirer %s not in pulled set" % acq, file=sys.stderr)
            return 1
        pairs = [(acq, t) for t in tickers if t != acq]
    else:
        pairs = [(a, b) for a, b in itertools.permutations(tickers, 2)]

    scored = []
    for a, b in pairs:
        try:
            scored.append(scoring.score_pair(profiles[a], profiles[b]))
        except Exception as e:
            print("  !! pair %s->%s failed: %s" % (a, b, e), file=sys.stderr)

    ranked = scoring.rank_pairs(scored)
    for p in ranked:
        p["rationale"] = scoring.rationale(p)

    if args.format == "json":
        print(json.dumps({
            "tool": "Mergers and Acquisitions For Peace",
            "version": __version__,
            "sector": args.sector,
            "pairs_scored": len(ranked),
            "score_note": "Screening scores 0-100; not valuations, not advice.",
            "pairs": ranked,
        }, indent=1))
    else:
        print_text(ranked, args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
