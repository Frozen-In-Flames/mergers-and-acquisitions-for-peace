"""Tests for portfolio building, roster queries, and cache. No network."""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "vendor"))
sys.path.insert(0, os.path.join(REPO, "tests"))

import fixtures  # noqa: E402
from mafp import cache, portfolio, roster  # noqa: E402


class FakeClient:
    def __init__(self, hits_by_variant):
        self.hits_by_variant = hits_by_variant

    def search(self, query, page_count=25):
        return {"patents": self.hits_by_variant.get(query, [])}

    def close(self):
        pass


def hit(assignee, guid="g1"):
    return {"guid": guid, "assigneeName": [assignee]}


class TestRoster(unittest.TestCase):
    def test_roster_loads_13_defense(self):
        r = roster.load_roster()
        self.assertEqual(len(r["companies"]), 13)
        tickers = {c["ticker"] for c in r["companies"]}
        self.assertIn("LMT", tickers)
        self.assertIn("RTX", tickers)

    def test_assignee_matches_tokens(self):
        self.assertTrue(roster.assignee_matches(
            hit("Lockheed Martin Corporation"), ["lockheed", "martin"]))
        self.assertFalse(roster.assignee_matches(
            hit("Maui Imaging, Inc."), ["lockheed", "martin"]))
        self.assertFalse(roster.assignee_matches(
            {"guid": "g2"}, ["lockheed", "martin"]))

    def test_pick_query_first_with_hits(self):
        company = {"ticker": "T", "assignee_queries": ["Alpha", "Beta"]}
        client = FakeClient({
            "Alpha": [hit("Alpha Corp", "g1")],
            "Beta": [hit("Beta Industries", "g%d" % i) for i in range(5)],
        })
        variant, hits = roster.pick_query(client, company, 10)
        self.assertEqual(variant, "Beta")
        self.assertEqual(len(hits), 5)

    def test_pick_query_falls_back_to_most_hits(self):
        company = {"ticker": "T", "assignee_queries": ["Alpha", "Beta"]}
        client = FakeClient({"Alpha": [hit("Alpha Corp", "g1")]})
        variant, hits = roster.pick_query(client, company, 10)
        self.assertEqual(variant, "Alpha")
        self.assertEqual(len(hits), 1)


class TestPortfolioDict(unittest.TestCase):
    def test_build_shape(self):
        patents = [fixtures.make_patent("10000001", "Test widget",
                                        "A test widget for testing.")]
        d = portfolio.build_portfolio_dict("Test portfolio", patents)
        self.assertEqual(d["meta"]["patent_count"], 1)
        self.assertIn("ontology", d)
        self.assertIn("concepts", d["ontology"])
        self.assertEqual(len(d["patents"]), 1)


class TestCache(unittest.TestCase):
    def test_round_trip(self):
        cache.save("testkind", "TESTKEY", {"a": 1})
        doc, pulled_at = cache.load("testkind", "TESTKEY")
        self.assertEqual(doc["payload"], {"a": 1})
        self.assertTrue(pulled_at)
        os.remove(os.path.join(cache.CACHE_DIR, "testkind_TESTKEY.json"))

    def test_missing_returns_none(self):
        self.assertIsNone(cache.load("testkind", "NOPE-NOT-HERE"))

    def test_provenance_labels(self):
        self.assertTrue(cache.provenance(True, "").startswith("live:"))
        self.assertTrue(
            cache.provenance(False, "2026-01-01").startswith("cached:"))


if __name__ == "__main__":
    unittest.main()
