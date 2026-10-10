"""SEC EDGAR client: ticker -> CIK lookup and XBRL companyfacts download.

Responses are cached under data/sec/ and refreshed after MAX_AGE.
SEC requires a User-Agent that names a contact email; set SEC_USER_AGENT.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import requests

PROJECT_DIR = Path(__file__).resolve().parents[1]
CACHE_DIR = Path(os.environ.get("FVMODEL_DATA", PROJECT_DIR / "data")) / "sec"
MAX_AGE = 24 * 3600
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"

# Filers that replaced an older registrant (e.g. a new holding company).
# Their history lives under the predecessor CIK, which we merge underneath.
PREDECESSOR_CIKS: dict[str, list[int]] = {
    "XOM": [34088],  # ExxonMobil Holdings Corp (2026) <- Exxon Mobil Corp
}


class SecError(RuntimeError):
    pass


def _user_agent() -> str:
    ua = os.environ.get("SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        raise SecError(
            "SEC EDGAR needs a contact email in the User-Agent. "
            'Set SEC_USER_AGENT="Your Name you@example.com" (e.g. in mise.local.toml).'
        )
    return ua


_rate_lock = threading.Lock()
_last_request = [0.0]
MIN_INTERVAL = 0.125  # SEC allows 10 requests/second; stay at 8 across all threads


def _throttle():
    with _rate_lock:
        wait = _last_request[0] + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request[0] = time.monotonic()


def _get_json(url: str, path: Path, refresh: bool = False) -> dict:
    if path.exists() and not refresh and time.time() - path.stat().st_mtime < MAX_AGE:
        return json.loads(path.read_text())
    _throttle()
    resp = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=60)
    if resp.status_code != 200:
        if path.exists():  # stale cache beats no data
            return json.loads(path.read_text())
        raise SecError(f"GET {url} -> HTTP {resp.status_code}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
    tmp.write_text(resp.text)
    tmp.replace(path)
    return resp.json()


def lookup(ticker: str) -> tuple[int, str]:
    """Return (cik, company title) for a ticker."""
    data = _get_json(TICKERS_URL, CACHE_DIR / "company_tickers.json")
    ticker = ticker.upper().replace(".", "-")
    for row in data.values():
        if row["ticker"].upper() == ticker:
            return int(row["cik_str"]), row["title"]
    raise SecError(f"Ticker {ticker} not found in SEC company_tickers.json")


def company_facts(cik: int) -> dict:
    return _get_json(FACTS_URL.format(cik=cik), CACHE_DIR / f"CIK{cik:010d}.json")


def load_facts(ticker: str) -> tuple[str, list[dict]]:
    """Company name plus the companyfacts documents, newest registrant first."""
    cik, title = lookup(ticker)
    docs = [company_facts(cik)]
    for old in PREDECESSOR_CIKS.get(ticker.upper(), []):
        docs.append(company_facts(old))
    return title, docs


def sic_code(ticker: str) -> int | None:
    """Standard Industrial Classification code from EDGAR (6000-6799 = financial)."""
    cik, _ = lookup(ticker)
    try:
        sic = _get_json(SUBMISSIONS_URL.format(cik=cik), CACHE_DIR / f"submissions_{cik:010d}.json").get("sic")
        return int(sic) if sic else None
    except (SecError, ValueError):
        return None


def is_financial(sic: int | None) -> bool:
    return sic is not None and 6000 <= sic <= 6799
