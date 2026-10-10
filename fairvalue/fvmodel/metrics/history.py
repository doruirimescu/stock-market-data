"""Quarterly TTM per-share history and daily valuation-multiple series.

The reference provider compares today's multiples with their own 10-year range and builds
Fair Value from historical median multiples. Both need a per-share fundamental
known at every trading day: the TTM value as of each quarter end, carried
forward until the next report.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from ..fundamentals import Fundamentals, _fix_share_scale

YEARS = 10


@dataclass
class PerShareHistory:
    """Per-share fundamentals indexed by quarter end (TTM for flows, balance for stocks)."""

    frame: pd.DataFrame  # columns: eps, eps_nri, revenue, fcf, book, ebitda, ebit, tbv

    def daily(self, index: pd.DatetimeIndex) -> pd.DataFrame:
        f = self.frame.copy()
        f.index = pd.to_datetime(f.index)
        return f.reindex(index.union(f.index)).ffill().reindex(index)


def per_share_history(f: Fundamentals, years: int = YEARS + 1) -> PerShareHistory:
    ends = [e for e in f.book.period_ends(("EarningsPerShareDiluted", "NetIncomeLoss", "ProfitLoss"))
            if (f.as_of - e).days <= years * 366]
    rows = {}
    for e in ends:
        shares = f.quarter_shares_diluted(e) or _fix_share_scale(
            f.mrq("shares_outstanding", e), f._nearest_shares_outstanding(e))
        if not shares:
            continue
        eps = f.ttm("eps_diluted", e)
        row = {
            "eps": eps,
            "eps_nri": f.eps_without_nri(e),
            "revenue": _ps(f.ttm("revenue", e), shares),
            "fcf": _ps(f.ttm("fcf", e), shares),
            "ebitda": _ps(f.ttm("ebitda", e), shares),
            "book": _ps(f.mrq("equity", e), shares),
            "tbv": _ps(f.mrq("tangible_equity", e), shares),
            "shares": shares,
        }
        if any(v is not None for k, v in row.items() if k != "shares"):
            rows[e] = row
    frame = pd.DataFrame.from_dict(rows, orient="index").sort_index().astype(float)
    return PerShareHistory(_fix_share_outliers(frame))


def _fix_share_outliers(frame: pd.DataFrame) -> pd.DataFrame:
    """Undo filer scaling errors in share counts (e.g. RITM Q1 2020 tagged 1000x too many).

    A quarter whose share count is more than 5x away from the median of its
    neighbours is rescaled to that median, together with its per-share values.
    """
    if frame.empty or "shares" not in frame:
        return frame
    sh = frame["shares"]
    ref = sh.rolling(5, center=True, min_periods=2).median()
    ratio = sh / ref
    bad = (ratio > 5) | (ratio < 0.2)
    if bad.any():
        frame = frame.copy()
        per_share = [c for c in frame.columns if c not in ("shares", "eps", "eps_nri")]  # EPS is reported per share directly
        frame.loc[bad, per_share] = frame.loc[bad, per_share].mul(ratio[bad], axis=0)
        frame.loc[bad, "shares"] = ref[bad]
    return frame


def _ps(v, shares):
    return None if v is None or not shares else v / shares


MULTIPLES = {"pe": "eps", "pe_nri": "eps_nri", "ps": "revenue", "pb": "book", "pfcf": "fcf"}


def multiple_series(closes: pd.Series, hist: PerShareHistory, as_of: date, years: int = YEARS) -> pd.DataFrame:
    """Daily price multiples over the last `years`; non-positive denominators are dropped."""
    start = pd.Timestamp(as_of) - pd.DateOffset(years=years)
    px = closes[closes.index >= start]
    fund = hist.daily(px.index)
    out = {}
    for name, col in MULTIPLES.items():
        denom = fund[col].where(fund[col] > 0)
        out[name] = px / denom
    return pd.DataFrame(out, index=px.index)


def range_stats(series: pd.Series, current: float | None) -> dict | None:
    """Min / median / max of a historical series and where `current` sits (0-100)."""
    s = series.dropna()
    if s.empty or current is None:
        return None
    return {
        "min": float(s.min()),
        "median": float(s.median()),
        "max": float(s.max()),
        "pct_rank": float((s < current).mean() * 100),
    }
