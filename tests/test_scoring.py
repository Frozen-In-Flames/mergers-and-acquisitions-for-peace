"""Tests for pairwise scoring. No network access."""

import os
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import fixtures  # noqa: E402
from mafp import scoring  # noqa: E402


def profile(ticker, name, port, by_year):
    return {
        "ticker": ticker, "name": name, "portfolio": port,
        "awards": fixtures.awards_dict(ticker, by_year),
        "provenance": "test", "awards_provenance": "test",
    }


class TestScorePair(unittest.TestCase):
    def setUp(self):
        self.acq = profile("AAA", "Acquirer Inc", fixtures.acquirer_portfolio(),
                           {2025: 1000000.0})
        self.tgt = profile("TTT", "Target Corp", fixtures.target_portfolio(),
                           {2025: 500000.0})

    def test_keys_present(self):
        s = scoring.score_pair(self.acq, self.tgt)
        for k in ("acquirer", "target", "shared_concept_count",
                  "redundant_pair_count", "gap_concept_count",
                  "target_awards_latest_usd", "weights"):
            self.assertIn(k, s)

    def test_shared_concepts_found(self):
        s = scoring.score_pair(self.acq, self.tgt)
        # both portfolios talk about missiles / thrust vectoring
        self.assertGreater(s["shared_concept_count"], 0)

    def test_gap_concepts_found(self):
        s = scoring.score_pair(self.acq, self.tgt)
        # drone swarm coordination is unique to the target
        self.assertGreater(s["gap_concept_count"], 0)

    def test_awards_latest_year(self):
        s = scoring.score_pair(self.acq, self.tgt)
        self.assertEqual(s["target_awards_latest_fy"], 2025)
        self.assertEqual(s["target_awards_latest_usd"], 500000.0)


class TestRankPairs(unittest.TestCase):
    def test_ranking_orders_by_score(self):
        a = profile("AAA", "Acquirer", fixtures.acquirer_portfolio(), {2025: 1.0})
        t1 = profile("T1", "Target One", fixtures.target_portfolio(), {2025: 1.0})
        # target two: same portfolio shape but no awards and fewer patents
        t2 = profile("T2", "Target Two", fixtures.target_portfolio(), {2025: 0.0})
        ranked = scoring.rank_pairs(
            [scoring.score_pair(a, t1), scoring.score_pair(a, t2)])
        self.assertEqual(len(ranked), 2)
        self.assertGreaterEqual(ranked[0]["screening_score"],
                                ranked[1]["screening_score"])
        for r in ranked:
            self.assertGreaterEqual(r["screening_score"], 0.0)
            self.assertLessEqual(r["screening_score"], 100.0)
            self.assertIn("score_parts", r)

    def test_empty(self):
        self.assertEqual(scoring.rank_pairs([]), [])

    def test_weights_labeled(self):
        self.assertAlmostEqual(sum(scoring.WEIGHTS.values()), 1.0)


class TestRationale(unittest.TestCase):
    def test_rationale_plain_english(self):
        a = profile("AAA", "Acquirer Inc", fixtures.acquirer_portfolio(),
                    {2025: 1000000.0})
        t = profile("TTT", "Target Corp", fixtures.target_portfolio(),
                    {2025: 500000.0})
        s = scoring.score_pair(a, t)
        r = scoring.rationale(s)
        self.assertIn("Acquirer Inc acquiring Target Corp", r)
        self.assertIn("500,000", r)
        self.assertNotIn("\u2014", r)  # no em dashes


if __name__ == "__main__":
    unittest.main()
