# Mergers and Acquisitions For Peace

Acquisition screening for defense capability, built from two proven
systems: the S&P 500 Corporate Stack (live federal award dollars) and the
Patent Portfolio APIs (USPTO portfolio analysis and M&A merging).

The thesis: consolidating warfighting capability into fewer, stronger
hands ends wars faster. Decisive capability is a peacemaking force. This
tool screens which defense acquisitions would consolidate the most
capability, so the M&A that matters most happens first.

## What it does

For each defense-relevant S&P 500 company (the 13 `defense_gov` names from
the Corporate Stack), it pulls:

1. A live USPTO patent portfolio via assignee-name search, with a concept
   ontology extracted per portfolio.
2. Live federal award dollars from USAspending.gov, matched by recipient
   name.

Then it scores every acquirer/target pair on four labeled components:

- **Concept overlap** (30%): shared technology concepts across the two
  patent portfolios.
- **Redundancy** (20%): patent pairs covering the same ground, R&D a
  merger could prune.
- **Gap closure** (25%): capabilities the target holds that the acquirer
  lacks.
- **Award scale** (25%): federal contract dollars that would consolidate.

The composite is a screening score from 0 to 100. It is not a valuation,
not a recommendation, and not investment advice.

## Usage

```bash
python3 analyze.py --sector defense --acquirer LMT
python3 analyze.py --sector defense --format json --top 5
python3 analyze.py --companies LMT,RTX,GD --limit 8 --refresh
```

Options: `--acquirer TICKER` scores every other company as a target for
that acquirer (default: every ordered pair); `--limit N` sets patents
pulled per company (default: 10); `--refresh` forces fresh live pulls and
rewrites the cache; `--format json` emits machine-readable output.

Data is live-first: USPTO and USAspending are queried at runtime. When an
API is unreachable, the most recent cached pull is used and labeled with
its date. Every dollar figure carries its source and pull date. Estimates
are never presented as exacts.

## Technical readiness: TRL 8

Self-assessed against the NASA scale. This system is complete and
qualified through test and demonstration: 20 automated tests green with
no network access in the test suite, and the CLI demonstrated end-to-end
on real live USPTO and USAspending data (see `demo/sample-output.md`).

The specific gap to TRL 9 is operational use: real analysts running it on
real deals, where sustained use against live acquisition work proves it
in its operational environment. Aries takes it to 9 himself through that
use.

## Honest limits

- Assignee matching is by USPTO assignee-name query, and assignee names
  vary (subsidiaries, legacy names like Raytheon vs RTX). The query used
  is recorded per company; the match is labeled, not exact.
- Patent portfolios are capped per run (`--limit`, default 10 recent
  patents per company). This is a screening sample, not a full portfolio
  audit.
- USAspending matching is by recipient name tokens. A year that fails to
  pull is recorded as missing, never zero.
- Concept extraction is TF-IDF phrase scoring, not legal claim analysis.
  Redundant pairs are text-and-classification similarity, not legal
  opinions on patent validity or freedom to operate.
- Scores compare pairs within a single run only. They do not transfer
  across runs with different company sets.

## Sources

- Patent data: USPTO Patent Public Search (PPUBS) web API, no key
  required, queried live at runtime.
- Awards data: USAspending.gov
  `/api/v2/search/spending_by_category/recipient/`, queried live at
  runtime by the vendored S&P 500 Corporate Stack engine.
- Company roster: S&P 500 Corporate Stack `vendor_map.json`,
  `reason_code=defense_gov`, October 2026.

## License

Apache-2.0. Not investment advice.
