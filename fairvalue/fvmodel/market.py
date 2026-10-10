"""Market data: prices and dividends (Yahoo via yfinance), CPI (FRED).

Everything is cached under data/market/ for a day.
"""

from __future__ import annotations

import io
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import requests
import yfinance as yf

CACHE_DIR = Path(os.environ.get("FVMODEL_DATA", Path(__file__).resolve().parents[1] / "data")) / "market"
MAX_AGE = 24 * 3600
BENCHMARK = "^GSPC"
TREASURY_10Y = "^TNX"
CPI_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"


def _cached(name: str, fetch):
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE:
        return pd.read_pickle(path)
    data = fetch()
    if len(data) == 0:
        raise ValueError(f"No market data for {name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    data.to_pickle(tmp)
    tmp.replace(path)  # atomic, so parallel workers never read a half-written file
    return data


def _closes(symbol: str) -> pd.Series:
    """Daily closes, split-adjusted but not dividend-adjusted (like quoted prices)."""

    def fetch():
        hist = yf.Ticker(symbol).history(period="max", auto_adjust=False, actions=False)
        s = hist["Close"].dropna()
        s.index = s.index.tz_localize(None).normalize()
        return s

    return _cached(symbol.replace("^", "_"), fetch)


def _history(symbol: str) -> pd.DataFrame:
    """Daily close, dividends and splits in one request (cached)."""

    def fetch():
        hist = yf.Ticker(symbol).history(period="max", auto_adjust=False, actions=True)
        hist.index = hist.index.tz_localize(None).normalize()
        cols = [c for c in ("Close", "Dividends", "Stock Splits") if c in hist]
        return hist[cols]

    return _cached(f"{symbol}_hist", fetch)


def _dividends(symbol: str) -> pd.Series:
    h = _history(symbol)
    s = h["Dividends"] if "Dividends" in h else pd.Series(dtype=float)
    return s[s > 0]


def splits(symbol: str) -> list:
    """(date, ratio) for every stock split, oldest first."""
    h = _history(symbol.upper().replace(".", "-"))
    s = h["Stock Splits"] if "Stock Splits" in h else pd.Series(dtype=float)
    return [(d.date(), float(r)) for d, r in s.items() if r and r != 1]


def _cpi() -> pd.Series:
    def fetch():
        text = requests.get(CPI_URL, timeout=30).text
        df = pd.read_csv(io.StringIO(text), parse_dates=[0], index_col=0)
        return df.iloc[:, 0].astype(float)

    return _cached("CPIAUCSL", fetch)


@dataclass
class Market:
    symbol: str
    closes: pd.Series
    dividends: pd.Series
    benchmark: pd.Series
    risk_free: float  # 10-year Treasury yield, decimal
    cpi: pd.Series

    @property
    def price(self) -> float:
        return float(self.closes.iloc[-1])

    @property
    def price_date(self):
        return self.closes.index[-1].date()

    def price_on(self, when) -> float | None:
        s = self.closes[: pd.Timestamp(when)]
        return float(s.iloc[-1]) if len(s) else None


def load_market(symbol: str, as_of=None) -> Market:
    """Market data, optionally truncated to what was known on `as_of`."""
    sym = symbol.upper().replace(".", "-")
    try:
        cpi = _cpi()
    except Exception:  # CPI only feeds Shiller PE; degrade gracefully
        cpi = pd.Series(dtype=float)
    series = [_history(sym)["Close"].dropna(), _dividends(sym), _closes(BENCHMARK), _closes(TREASURY_10Y), cpi]
    if as_of is not None:
        end = pd.Timestamp(as_of)
        series = [s[s.index <= end] for s in series]
    closes, divs, bench, tnx, cpi = series
    return Market(sym, closes, divs, bench, float(tnx.iloc[-1]) / 100, cpi)
