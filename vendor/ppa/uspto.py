"""Client for the USPTO Patent Public Search (PPUBS) web API.

The PPUBS web app (ppubs.uspto.gov/pubwebapp) talks to a JSON API.  The flow
is:
  1. GET  /pubwebapp/                        (establish cookies)
  2. POST /api/users/me/session  (body: -1)  -> access token arrives in the
     ``x-access-token`` response header; case id in the JSON body
  3. POST /api/searches/searchWithBeFamily     (BRS query, X-Access-Token)
  4. GET  /api/patents/highlight/{guid}       (full document, X-Access-Token)

No API key is required.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

import requests

log = logging.getLogger(__name__)

BASE_URL = "https://ppubs.uspto.gov"
USER_AGENT = "Mozilla/5.0 (compatible; patent-portfolio-apis/0.1.0)"


class USPTOError(RuntimeError):
    """Raised when the USPTO API cannot fulfil a request."""


def _search_body(query: str, case_id: int, start: int = 0,
                 page_count: int = 25,
                 databases: Optional[List[str]] = None) -> Dict[str, Any]:
    databases = databases or ["USPAT"]
    return {
        "start": start,
        "pageCount": page_count,
        "sort": "date_publ desc",
        "docFamilyFiltering": "familyIdFiltering",
        "searchType": 1,
        "familyIdEnglishOnly": True,
        "familyIdFirstPreferred": "US-PGPUB",
        "familyIdSecondPreferred": "USPAT",
        "familyIdThirdPreferred": "FPRS",
        "showDocPerFamilyPref": "showEnglish",
        "queryId": 0,
        "tagDocSearch": False,
        "query": {
            "caseId": case_id,
            "hl_snippets": "2",
            "op": "AND",
            "q": query,
            "queryName": query,
            "highlights": "1",
            "qt": "brs",
            "spellCheck": False,
            "viewName": "tile",
            "plurals": True,
            "britishEquivalents": True,
            "databaseFilters": [
                {"databaseName": db, "countryCodes": []} for db in databases
            ],
            "searchType": 1,
            "ignorePersist": True,
            "userEnteredQuery": query,
        },
    }


class PPUBSClient:
    """Thin session-managed client for the PPUBS JSON API."""

    def __init__(self, timeout: int = 60, max_retries: int = 5) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self._s = requests.Session()
        self._s.headers.update({"User-Agent": USER_AGENT})
        self._token: Optional[str] = None
        self._case_id: Optional[int] = None

    # ------------------------------------------------------------------ #
    def _request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        last: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                resp = self._s.request(method, url, timeout=self.timeout,
                                       **kwargs)
                if resp.status_code == 200:
                    return resp
                last = USPTOError(f"{method} {url} -> HTTP {resp.status_code}")
                log.warning("%s (attempt %d)", last, attempt + 1)
            except Exception as exc:  # network / proxy flakiness
                last = exc
                log.warning("request failed (attempt %d): %s", attempt + 1, exc)
            time.sleep(2 * (attempt + 1))
        raise USPTOError(f"request failed after {self.max_retries} attempts: {last}")

    # ------------------------------------------------------------------ #
    def ensure_session(self) -> None:
        if self._token and self._case_id:
            return
        self._request("GET", f"{BASE_URL}/pubwebapp/")
        resp = self._request(
            "POST", f"{BASE_URL}/api/users/me/session", json=-1,
            headers={"X-Access-Token": "null",
                     "referer": f"{BASE_URL}/pubwebapp/",
                     "Accept": "application/json",
                     "Content-Type": "application/json"})
        token = resp.headers.get("x-access-token")
        body = resp.json()
        case_id = (body.get("userCase") or {}).get("caseId")
        if not token or not case_id:
            raise USPTOError("could not establish PPUBS session")
        self._token, self._case_id = token, case_id

    def _auth(self) -> Dict[str, str]:
        self.ensure_session()
        assert self._token is not None
        return {"X-Access-Token": self._token}

    # ------------------------------------------------------------------ #
    def search(self, query: str, start: int = 0,
               page_count: int = 25) -> Dict[str, Any]:
        """Run a BRS-syntax query, e.g. '("10000000").pn.' or 'tesla.as.'."""
        self.ensure_session()
        assert self._case_id is not None
        resp = self._request(
            "POST", f"{BASE_URL}/api/searches/searchWithBeFamily",
            json=_search_body(query, self._case_id, start, page_count),
            headers=self._auth())
        data = resp.json()
        if data.get("error"):
            raise USPTOError(f"search error: {data['error']}")
        return data

    def search_by_number(self, number: str) -> Optional[Dict[str, Any]]:
        """Return the first patent hit for a patent number, or None."""
        digits = "".join(ch for ch in number if ch.isdigit())
        if not digits:
            raise ValueError(f"not a patent number: {number!r}")
        data = self.search(f'("{digits}").pn.', page_count=5)
        patents = data.get("patents") or []
        return patents[0] if patents else None

    def search_by_inventor(self, name: str,
                           limit: int = 25) -> List[Dict[str, Any]]:
        """Search granted patents by inventor name (e.g. 'Musk.in.')."""
        data = self.search(f"{name}.in.", page_count=limit)
        return data.get("patents") or []

    def get_document(self, guid: str) -> Dict[str, Any]:
        """Fetch the full document (biblio, abstract, claims, description)."""
        resp = self._request(
            "GET", f"{BASE_URL}/api/patents/highlight/{guid}",
            params={"queryId": 1, "source": "USPAT", "includeSections": True},
            headers=self._auth())
        return resp.json()

    def fetch_patent(self, number: str) -> Dict[str, Any]:
        """Search by number, then fetch the full document."""
        hit = self.search_by_number(number)
        if not hit:
            raise USPTOError(f"patent not found: {number}")
        guid = hit.get("guid")
        if not guid:
            raise USPTOError(f"no document guid for patent {number}")
        doc = self.get_document(guid)
        # keep a few search-hit fields the full doc may lack
        doc.setdefault("guid", guid)
        return doc

    def close(self) -> None:
        self._s.close()
