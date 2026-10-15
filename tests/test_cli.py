"""Tests for the analyze.py CLI surface. No network access."""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stdout
from unittest import mock

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))

import analyze  # noqa: E402
import fixtures  # noqa: E402
from mafp import scoring  # noqa: E402


def fake_profile(company, limit, refresh):
    ticker, name = company["ticker"], company["name"]
    port = (fixtures.acquirer_portfolio() if ticker == "AAA"
            else fixtures.target_portfolio())
    return {
        "ticker": ticker, "name": name, "portfolio": port,
        "awards": fixtures.awards_dict(ticker, {2025: 100.0}),
        "provenance": "test", "awards_provenance": "test",
    }


FAKE_ROSTER = {
    "companies": [
        {"ticker": "AAA", "name": "Acquirer Inc",
         "assignee_queries": ["Acquirer"]},
        {"ticker": "TTT", "name": "Target Corp",
         "assignee_queries": ["Target"]},
    ]
}


def patched_main(args):
    with mock.patch.object(analyze, "build_profile", side_effect=fake_profile), \
         mock.patch.object(analyze.roster, "load_roster",
                           return_value=FAKE_ROSTER):
        return analyze.main(args)


class TestCLI(unittest.TestCase):
    def test_json_output_shape(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = patched_main(["--companies", "AAA,TTT", "--format", "json",
                               "--acquirer", "AAA"])
        self.assertEqual(rc, 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(doc["tool"], "Mergers and Acquisitions For Peace")
        self.assertEqual(doc["pairs_scored"], 1)
        pair = doc["pairs"][0]
        self.assertEqual(pair["acquirer"], "AAA")
        self.assertEqual(pair["target"], "TTT")
        self.assertIn("rationale", pair)
        self.assertIn("screening_score", pair)

    def test_text_output(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = patched_main(["--companies", "AAA,TTT",
                               "--acquirer", "AAA", "--top", "5"])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        self.assertIn("Mergers and Acquisitions For Peace", out)
        self.assertIn("AAA -> TTT", out)

    def test_no_companies_selected(self):
        rc = analyze.main(["--companies", "ZZZ"])
        self.assertEqual(rc, 1)

    def test_profile_failure_skipped(self):
        def boom(company, limit, refresh):
            raise RuntimeError("network down")
        with mock.patch.object(analyze, "build_profile", side_effect=boom), \
             mock.patch.object(analyze.roster, "load_roster",
                               return_value=FAKE_ROSTER):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = analyze.main(["--companies", "AAA", "--format", "json"])
        self.assertEqual(rc, 0)
        doc = json.loads(buf.getvalue())
        self.assertEqual(doc["pairs_scored"], 0)


if __name__ == "__main__":
    unittest.main()
