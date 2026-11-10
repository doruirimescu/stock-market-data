"""Price and macro data for the All-Weather gauges, cached in generated/allweather/cache/ (git-ignored).

    python -m allweather.data            # refresh the cache (Yahoo prices + FRED)

Prices: Yahoo Finance daily bars, adjusted for dividends and splits (total return), put on the NYSE
calendar (SPY's trading days; Bitcoin's weekend moves land in Monday's bar). Days before an asset
existed are filled with its first price and volume 0, so a backtest panel can hold all assets from the
start; the engine treats an asset as investable only after 260 days with real volume.
One CSV per proxy in the tradelab `generic_end` layout: ts (date), open, high, low, close, volume.

Macro: raw FRED observations for every series the gauges use, as {series: [[date, value], ...]}.
Release lags are applied later by the engine, so the cache holds what FRED reports.
"""
import csv
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from bond_signals import SERIES as BOND_SERIES  # noqa: E402
from common import http_get_json  # noqa: E402
from fed_data import fetch  # noqa: E402

from .universe import CASH, UNIVERSE  # noqa: E402

CACHE = ROOT / "generated/allweather/cache"
PRICES = CACHE / "prices"
FRED_FILE = CACHE / "fred.json"
PRICE_START = date(1998, 12, 22)   # the Select Sector SPDRs list in Dec 1998

# Release lag in calendar days for the extra series (the bond series carry theirs in bond_signals.SERIES).
EXTRA_SERIES = {
    "VIXCLS": 1,      # CBOE VIX close
    "STLFSI4": 7,     # St. Louis Fed Financial Stress Index, week ending Friday, released the next Thursday
    "DTWEXBGS": 7,    # broad trade-weighted dollar, posted weekly (H.10)
    "AAA10Y": 1,      # Moody's Aaa corporate yield minus 10-year Treasury
}
LAGS = {**BOND_SERIES, **EXTRA_SERIES}


def proxies():
    return [a["proxy"] for a in UNIVERSE] + [CASH["proxy"]]


def yahoo_daily(symbol, start=PRICE_START, end=None):
    """[(date, open, high, low, close, volume)] adjusted for dividends and splits."""
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    p2 = int((end and datetime(end.year, end.month, end.day, tzinfo=timezone.utc) or datetime.now(timezone.utc)).timestamp())
    url = (f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}"
           f"?period1={p1}&period2={p2}&interval=1d&events=div%7Csplit")
    res = http_get_json(url)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    out = []
    for t, o, h, lo, c, v, a in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"], adj):
        if None in (o, h, lo, c, a) or c <= 0:
            continue
        f = a / c
        d = datetime.fromtimestamp(t + res["meta"].get("gmtoffset", 0), timezone.utc).date()
        out.append((d, o * f, h * f, lo * f, a, float(v or 0)))
    return out


def to_calendar(rows, cal):
    """Rows on the master calendar: forward-fill small gaps; before the first row, the first price with volume 0."""
    by_day = {r[0]: r for r in rows}
    first = rows[0]
    out, last = [], None
    for d in cal:
        r = by_day.get(d)
        if r is not None:
            last = r
            out.append(r)
        elif last is None:
            out.append((d, first[1], first[1], first[1], first[1], 0.0))
        else:
            c = last[4]
            out.append((d, c, c, c, c, 0.0))
    return out


def refresh_prices():
    PRICES.mkdir(parents=True, exist_ok=True)
    print("Downloading Yahoo prices...", file=sys.stderr)
    raw = {s: yahoo_daily(s) for s in proxies()}
    cal = [r[0] for r in raw["SPY"]]
    for s, rows in raw.items():
        rows = [r for r in rows if r[0] <= cal[-1]]
        out = to_calendar(rows, cal)
        with open(PRICES / f"{s}.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["ts", "open", "high", "low", "close", "volume"])
            for d, o, h, lo, c, v in out:
                w.writerow([d.isoformat(), f"{o:.6g}", f"{h:.6g}", f"{lo:.6g}", f"{c:.6g}", float(v)])
        print(f"  {s}: {len(rows)} days from {rows[0][0]}, last {rows[-1][0]}", file=sys.stderr)


def refresh_fred():
    CACHE.mkdir(parents=True, exist_ok=True)
    print("Downloading FRED series...", file=sys.stderr)
    raw = {s: fetch(s) for s in LAGS}
    FRED_FILE.write_text(json.dumps({s: [[d.isoformat(), v] for d, v in sorted(obs.items())] for s, obs in raw.items()}))


def load_fred(path=FRED_FILE):
    """{series: {date: value}} from the cache."""
    data = json.loads(Path(path).read_text())
    return {s: {date.fromisoformat(d): v for d, v in obs} for s, obs in data.items()}


def load_prices(path_template=str(PRICES / "{symbol}.csv"), symbols=None):
    """{proxy: DataFrame(date index; open, high, low, close, volume)} from the cache."""
    import pandas as pd
    out = {}
    for s in symbols or proxies():
        df = pd.read_csv(path_template.format(symbol=s), parse_dates=["ts"]).set_index("ts")
        df.index = pd.DatetimeIndex(df.index).normalize()
        out[s] = df
    return out


def main():
    refresh_prices()
    refresh_fred()


if __name__ == "__main__":
    main()
