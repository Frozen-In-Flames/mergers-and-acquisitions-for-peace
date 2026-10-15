"""Shared synthetic fixtures for tests. No network access."""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "vendor"))

from ppa.models import Patent  # noqa: E402

from mafp import portfolio  # noqa: E402


def make_patent(number, title, abstract, cpc=("F41A1/00",)):
    return Patent(
        number=number,
        title=title,
        abstract=abstract,
        claims=[{"number": "1", "text": "A system comprising " + title}],
        assignees=["Test Assignee"],
        cpc_inventive=list(cpc),
        grant_date="2024-01-01",
    )


def acquirer_portfolio():
    patents = [
        make_patent("10000001", "Guided missile propulsion system",
                    "A propulsion system for a guided missile with thrust "
                    "vector control and solid propellant grain geometry.",
                    cpc=("F41A1/00", "F02K9/00")),
        make_patent("10000002", "Radar cross section reduction coating",
                    "A radar absorbing coating applied to aircraft surfaces "
                    "to reduce radar cross section signature.",
                    cpc=("F41H3/00",)),
    ]
    return portfolio.build_portfolio_dict("Acquirer portfolio", patents)


def target_portfolio():
    patents = [
        make_patent("20000001", "Missile thrust vector controller",
                    "A controller for missile thrust vectoring using gimballed "
                    "nozzle actuators and propellant flow regulation.",
                    cpc=("F41A1/00", "F02K9/00")),
        make_patent("20000002", "Autonomous drone swarm coordination",
                    "A method for coordinating autonomous drone swarms with "
                    "mesh networking and distributed target assignment.",
                    cpc=("B64C39/00",)),
    ]
    return portfolio.build_portfolio_dict("Target portfolio", patents)


def awards_dict(ticker, by_year):
    return {
        "ticker": ticker,
        "name": "Test Co",
        "by_year": {str(k): v for k, v in by_year.items()},
        "matched_recipient_names": [],
        "match_method": "test",
        "source": "test source",
    }
