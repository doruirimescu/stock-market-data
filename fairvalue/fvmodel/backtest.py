"""Point-in-time backtest: do the Fair Value signals predict returns?

At every quarter end since 2013 each stock that was in the S&P 500 on that day
is valued with only the filings filed and the prices quoted by then
(analyze_history -> FactBook(filed_by=d), Market truncated to d). Stocks are
then ranked into quintiles by a signal and the forward total returns
(dividends reinvested) of each quintile are compared with the equal-weight
average of all ranked stocks:

    gap      the valuation gap (Fair Value - price) / Fair Value, uncapped
    quality  the Quality Score
    combo    the mean of the two percentile ranks

Membership comes from fja05680/sp500 (start and end date of every S&P 500
spell), so stocks that joined the index later are excluded before they joined,
and stocks that left it but still trade are included while they were members.
Stocks that no longer trade at all (acquired, bankrupt) have no SEC ticker or
Yahoo history and are missing: a survivorship bias that the page states.

Forward returns run to the last price on or before d + horizon. A stock whose
prices stop earlier (taken over) earns its return up to its last price.
"""

from __future__ import annotations

import csv
import io
import json
import math
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import market, sec
from .metrics import analyze_history

MEMBERSHIP_URL = "https://raw.githubusercontent.com/fja05680/sp500/master/sp500_ticker_start_end.csv"
START = date(2013, 3, 31)
HORIZONS = {"3m": 3, "6m": 6, "12m": 12, "36m": 36}
STALE_DAYS = 200  # latest fiscal period older than this at the signal date: the company stopped filing
PRICE_LAG_DAYS = 7  # last close older than this at the signal date: not trading then
MIN_STOCKS = 100  # dates with fewer ranked stocks are left out of the statistics
QUINTILES = 5
SIGNALS = {"gap": "Valuation gap", "quality": "Quality Score", "combo": "Gap + Quality"}

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "generated" / "fairvalue" / "backtest"


# ---- universe -------------------------------------------------------------


def load_membership(text: str) -> dict[str, list[tuple[date, date | None]]]:
    """{ticker: [(start, end or None), ...]} from the fja05680 start/end CSV."""
    spells: dict[str, list[tuple[date, date | None]]] = {}
    for row in csv.DictReader(io.StringIO(text)):
        end = date.fromisoformat(row["end_date"]) if row["end_date"] else None
        spells.setdefault(row["ticker"].upper(), []).append((date.fromisoformat(row["start_date"]), end))
    return spells


def fetch_membership() -> dict[str, list[tuple[date, date | None]]]:
    path = Path(market.CACHE_DIR).parent / "backtest" / "sp500_ticker_start_end.csv"
    if not path.exists() or time.time() - path.stat().st_mtime > market.MAX_AGE:
        text = requests.get(MEMBERSHIP_URL, timeout=60).text
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return load_membership(path.read_text())


# Members since 2013 whose ticker changed while the same SEC registrant carried
# on. SEC only maps current tickers, so their earlier spells are valued under
# the new one. Checked by hand: in the membership data a rename looks exactly
# like an index replacement (old ticker out, new ticker in, same day). Mergers
# into a different registrant (Mylan -> Viatris, Kraft -> Kraft Heinz,
# WestRock -> Smurfit Westrock) are not renames and stay missing.
RENAMES = {
    "ABC": "COR", "ANTM": "ELV", "ARNC": "HWM", "BHGE": "BKR", "CTL": "LUMN", "DISCA": "WBD",
    "DISCK": "WBD", "DWDP": "DD", "FB": "META", "FLT": "CPAY", "HRS": "LHX", "NLOK": "GEN",
    "PKI": "RVTY", "RE": "EG", "TMK": "GL", "UTX": "RTX",
}


def is_member(spells: list[tuple[date, date | None]], d: date) -> bool:
    return any(s <= d and (e is None or d < e) for s, e in spells)


def signal_dates(start: date, end: date) -> list[date]:
    """Quarter ends from start to end, inclusive."""
    return [ts.date() for ts in pd.date_range(start, end, freq="QE")]


# ---- returns --------------------------------------------------------------


def total_return_index(closes: pd.Series, dividends: pd.Series) -> pd.Series:
    """Close-to-close growth with each dividend reinvested on its ex-date."""
    closes = closes.dropna()
    divs = dividends.reindex(closes.index).fillna(0.0)
    growth = (closes + divs) / closes.shift(1)
    return growth.fillna(1.0).cumprod()


def forward_returns(tr: pd.Series, d: date, last_day: date) -> dict[str, float | None]:
    """Total return from the last close on or before d to the last close on or before d + h."""
    start = tr[: pd.Timestamp(d)]
    out = {}
    for name, months in HORIZONS.items():
        end_day = (pd.Timestamp(d) + pd.DateOffset(months=months)).date()
        if start.empty or end_day > last_day:
            out[name] = None
            continue
        end = tr[: pd.Timestamp(end_day)]
        out[name] = float(end.iloc[-1] / start.iloc[-1] - 1)
    return out


# ---- panel ----------------------------------------------------------------


def _offline():
    """Use the caches as they are: the run outlasts their one-day refresh."""
    sec.MAX_AGE = market.MAX_AGE = math.inf


def ticker_rows(ticker: str, dates: list[date], last_day: date) -> list[dict]:
    """One row per signal date the stock could be valued on."""
    h = market._history(ticker.replace(".", "-"))
    tr = total_return_index(h["Close"], h["Dividends"] if "Dividends" in h else pd.Series(dtype=float))
    rows = []
    for d, r in analyze_history(ticker, dates):
        row = {"date": d.isoformat(), "ticker": ticker}
        if isinstance(r, Exception):
            rows.append({**row, "skip": "no valuation"})
            continue
        if (d - r.price_date).days > PRICE_LAG_DAYS:
            rows.append({**row, "skip": "not trading"})
            continue
        if (d - r.as_of).days > STALE_DAYS:
            rows.append({**row, "skip": "stale filings"})
            continue
        rows.append({
            **row, "skip": None if r.m("valuation_score") is not None else "no fair value",
            "price": r.price, "fair_value": r.m("fair_value"), "gap": r.m("valuation_score"),
            "quality": r.m("quality_score"), "market_cap": r.market_cap, "financial": r.financial,
            "fundamentals_as_of": r.as_of.isoformat(),
            **{f"ret_{k}": v for k, v in forward_returns(tr, d, last_day).items()},
        })
    return rows


def _worker(ticker, dates, last_day):
    _offline()
    try:
        return ticker, ticker_rows(ticker, dates, last_day), None
    except Exception as e:
        return ticker, [], f"{type(e).__name__}: {e}"[:200]


def _prefetch(ticker: str) -> str | None:
    """Download what a worker needs, so the worker processes never call SEC or Yahoo."""
    try:
        sec.load_facts(ticker)
        sec.sic_code(ticker)
        market._history(ticker.replace(".", "-"))
        return None
    except Exception as e:
        return f"{type(e).__name__}: {e}"[:200]


def build_panel(start: date = START, workers: int = 8, limit: int | None = None) -> pd.DataFrame:
    spells = fetch_membership()
    last_day = market._history("SPY").index[-1].date()
    dates = signal_dates(start, last_day)
    spells = {t: sp for t, sp in spells.items() if any(is_member([s], d) for s in sp for d in dates)}
    renames = {old: new for old, new in RENAMES.items() if old in spells and new in spells}
    for old, new in renames.items():
        spells[new] = spells[new] + spells.pop(old)
    universe = sorted(spells)[:limit]
    print(f"[backtest] {len(universe)} tickers were S&P 500 members on {len(dates)} quarter ends "
          f"{dates[0]}..{dates[-1]}", file=sys.stderr)

    market._closes(market.BENCHMARK), market._closes(market.TREASURY_10Y), sec.lookup("AAPL")
    try:
        market._cpi()
    except Exception:
        pass
    missing = {}
    with ThreadPoolExecutor(max_workers=6) as pool:  # SEC throttling is shared between threads
        for tk, err in zip(universe, pool.map(_prefetch, universe)):
            if err:
                missing[tk] = err
    print(f"[backtest] no SEC or Yahoo data for {len(missing)} tickers (delisted)", file=sys.stderr)

    rows, failed, started = [], {}, time.time()
    todo = [tk for tk in universe if tk not in missing]
    with ProcessPoolExecutor(max_workers=workers, initializer=_offline) as pool:
        futures = [pool.submit(_worker, tk, [d for d in dates if is_member(spells[tk], d)], last_day) for tk in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            tk, r, err = fut.result()
            rows.extend(r)
            if err:
                failed[tk] = err
            if i % 50 == 0 or i == len(futures):
                print(f"[backtest] {i}/{len(futures)} tickers, {len(rows)} rows, {time.time() - started:.0f}s",
                      file=sys.stderr)

    # Members that could not be valued at all still count in the coverage figures.
    for tk in missing:
        rows.extend({"date": d.isoformat(), "ticker": tk, "skip": "delisted (no data)"}
                    for d in dates if is_member(spells[tk], d))
    panel = pd.DataFrame(rows).sort_values(["date", "ticker"]).reset_index(drop=True)
    panel.attrs["meta"] = {"universe": len(universe), "missing": missing, "failed": failed,
                           "renames": renames, "last_day": last_day.isoformat()}
    return panel


# ---- statistics -----------------------------------------------------------


def newey_west_t(x: np.ndarray, lag: int) -> float | None:
    """t-stat of the mean with Newey-West errors (overlapping horizons are autocorrelated)."""
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 4:
        return None
    e = x - x.mean()
    var = e @ e / n
    for k in range(1, min(lag, n - 1) + 1):
        var += 2 * (1 - k / (lag + 1)) * (e[k:] @ e[:-k]) / n
    return float(x.mean() / math.sqrt(var / n)) if var > 0 else None


def add_signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Valued rows only, with a per-date percentile rank per signal (1 = best)."""
    v = panel[panel["gap"].notna()].copy()
    by = v.groupby("date")
    v["rank_gap"] = by["gap"].rank(pct=True)
    v["rank_quality"] = by["quality"].rank(pct=True)
    v["combo"] = (v["rank_gap"] + v["rank_quality"]) / 2
    v.loc[v["quality"].isna(), "combo"] = np.nan
    return v


def quintiles(s: pd.Series) -> pd.Series:
    """1 = highest fifth of the signal ... 5 = lowest; ties broken by order."""
    ranks = s.rank(method="first", ascending=False)
    return np.ceil(ranks / len(s) * QUINTILES).astype(int)


def signal_stats(v: pd.DataFrame, signal: str, spy: pd.Series) -> dict:
    out = {"horizons": {}, "by_year": {}, "cumulative": None}
    for h, months in HORIZONS.items():
        col = f"ret_{h}"
        per_date = []
        for d, g in v[v[signal].notna() & v[col].notna()].groupby("date"):
            if len(g) < MIN_STOCKS:
                continue
            q = quintiles(g[signal])
            means = g[col].groupby(q).mean()
            per_date.append({
                "date": d, "n": len(g), "universe": float(g[col].mean()),
                **{f"q{k}": float(means.get(k, np.nan)) for k in range(1, QUINTILES + 1)},
                "ic": float(g[signal].rank().corr(g[col].rank())),
            })
        if not per_date:
            continue
        pdf = pd.DataFrame(per_date)
        spread = (pdf["q1"] - pdf[f"q{QUINTILES}"]).to_numpy()
        lag = max(months // 3 - 1, 0)
        out["horizons"][h] = {
            "dates": len(pdf), "first": pdf["date"].iloc[0], "last": pdf["date"].iloc[-1],
            "stocks_per_date": round(float(pdf["n"].mean())),
            "universe": float(pdf["universe"].mean()),
            "excess": [float((pdf[f"q{k}"] - pdf["universe"]).mean()) for k in range(1, QUINTILES + 1)],
            "spread": float(spread.mean()), "spread_t": newey_west_t(spread, lag),
            "hit_rate": float((spread > 0).mean()),
            "ic": float(pdf["ic"].mean()), "ic_t": newey_west_t(pdf["ic"].to_numpy(), lag),
            "ic_positive": float((pdf["ic"] > 0).mean()),
        }
        if h == "12m":
            years = pd.to_datetime(pdf["date"]).dt.year
            out["by_year"] = {int(y): float(s.mean()) for y, s in pd.Series(spread).groupby(years.to_numpy())}
        if h == "3m":
            out["cumulative"] = _cumulative(pdf, spy)
    return out


def _cumulative(pdf: pd.DataFrame, spy: pd.Series) -> dict:
    """Growth of 1 in each quintile, rebalanced every quarter on the 3-month returns."""
    dates = list(pdf["date"])
    ends = [(pd.Timestamp(d) + pd.DateOffset(months=3)).date().isoformat() for d in dates]
    curves = {f"q{k}": [1.0] for k in range(1, QUINTILES + 1)} | {"universe": [1.0], "spy": [1.0]}
    for (_, row), d, e in zip(pdf.iterrows(), dates, ends):
        for k in curves:
            if k == "spy":
                r = float(spy[: pd.Timestamp(e)].iloc[-1] / spy[: pd.Timestamp(d)].iloc[-1] - 1)
            else:
                r = row[k]
            curves[k].append(curves[k][-1] * (1 + r))
    years = (pd.Timestamp(ends[-1]) - pd.Timestamp(dates[0])).days / 365.25
    return {"dates": [dates[0], *ends], "curves": curves,
            "cagr": {k: c[-1] ** (1 / years) - 1 for k, c in curves.items()}}


def summarize(panel: pd.DataFrame, meta: dict) -> dict:
    v = add_signals(panel)
    spy_h = market._history("SPY")
    spy = total_return_index(spy_h["Close"], spy_h["Dividends"])
    coverage = (panel.assign(valued=panel["gap"].notna() if "gap" in panel else False)
                .groupby("date").agg(members=("ticker", "size"), valued=("valued", "sum")))
    skips = panel["skip"].fillna("valued").value_counts().to_dict()
    latest = v[v["date"] == v["date"].max()]
    return {
        "generated": date.today().isoformat(),
        "meta": {**meta, "missing": len(meta.get("missing", {})), "failed": len(meta.get("failed", {})),
                 "tickers_valued": int(v["ticker"].nunique()), "observations": len(v), "skips": skips},
        "coverage": {"dates": list(coverage.index), "members": coverage["members"].tolist(),
                     "valued": [int(x) for x in coverage["valued"]]},
        "signals": {k: {"label": label, **signal_stats(v, k, spy)} for k, label in SIGNALS.items()},
        "latest_date": None if latest.empty else latest["date"].iloc[0],
    }


# ---- entry point ----------------------------------------------------------


def _clean(o):
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(o, dict):
        return {str(k): _clean(x) for k, x in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(x) for x in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(o) else round(float(o), 6)
    if isinstance(o, np.integer):
        return int(o)
    return o


def main(args) -> None:
    from .render import render_backtest

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    panel_path, meta_path = OUT_DIR / "sp500_panel.csv.gz", OUT_DIR / "sp500_panel_meta.json"
    if args.from_panel:
        panel = pd.read_csv(panel_path, dtype={"date": str})
        meta = json.loads(meta_path.read_text())
    else:
        panel = build_panel(date.fromisoformat(args.start), args.workers, args.limit)
        meta = panel.attrs["meta"]
        panel.to_csv(panel_path, index=False, float_format="%.6g")
        meta_path.write_text(json.dumps(meta, indent=1))
    _offline()
    summary = _clean(summarize(panel, meta))
    (OUT_DIR / "sp500_backtest.json").write_text(json.dumps(summary, indent=1))
    pages = Path(args.pages) if args.pages else REPO / "docs" / "fairvalue"
    render_backtest(summary, pages)
    h = summary["signals"]["gap"]["horizons"].get("12m", {})
    print(f"[backtest] wrote {pages / 'backtest.html'}; gap 12m Q1-Q5 spread "
          f"{h.get('spread', float('nan')) * 100:.1f}% (t={h.get('spread_t')}), IC {h.get('ic')}", file=sys.stderr)
