"""
Download the Federal Reserve series behind the Learn > "How the Fed makes money"
lecture from FRED and write them to docs/learn/data/fed.js.

    python scripts/fed_data.py                       # -> docs/learn/data/fed.js
    python scripts/fed_data.py --out some/file.js

Uses FRED's public CSV endpoint (no API key). Stdlib only.

Output (loaded as a <script>, so the page also works from disk):
    window.nexusData.fed = {
      updated, weekly: { dates, <series>: [...] },   # H.4.1 Wednesdays since 2007, $bn
      rates:   { dates, <series>: [...] },           # policy rates on those Wednesdays, %
      repo2019:{ dates, <series>: [...] },           # daily, Aug 2019 - Jan 2020
      m2:      { dates, yoy: [...], level: [...] },  # monthly, YoY % and $bn
    }
"""

import argparse
import csv
import io
import json
import sys
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={}"
START = date(2007, 1, 3)

# H.4.1 Wednesday levels, millions of dollars.
WEEKLY = {
    "total": "WALCL",        # total assets
    "treasuries": "TREAST",  # Treasury securities held outright
    "mbs": "WSHOMCB",        # mortgage-backed securities
    "repo": "WORAL",         # repurchase agreements (Fed lends cash)
    "loans": "WLCFLL",       # loans (discount window, PPP, emergency facilities)
    "swaps": "SWPT",         # central bank liquidity swaps
    "reserves": "WRBWFRBL",  # reserve balances
    "currency": "WCURCIR",   # currency in circulation
    "rrp": "WLRRAL",         # reverse repurchase agreements (Fed borrows cash)
    "tga": "WDTGAL",         # Treasury General Account
}
# Daily, percent.
RATES = {
    "effr": "DFF",
    "upper": "DFEDTARU",
    "lower": "DFEDTARL",
    "ioer": "IOER",          # interest on excess reserves, to Jul 2021
    "iorb": "IORB",          # interest on reserve balances, from Jul 2021
    "rrp": "RRPONTSYAWARD",  # ON RRP offering rate
    "sofr": "SOFR",
}


def fetch(series_id):
    """{date: float} for one FRED series; missing values (".") are skipped."""
    # Plain urllib on purpose: FRED's CDN stalls requests with a custom User-Agent
    # (common.http_get's browser UA included) but answers the default one.
    for attempt in range(3):
        try:
            text = urllib.request.urlopen(FRED.format(series_id), timeout=60).read().decode()
            break
        except OSError as e:
            if attempt == 2:
                raise
            print(f"  retry {series_id}: {e}", file=sys.stderr)
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        v = row.get(series_id, ".")
        if v in (".", ""):
            continue
        out[date.fromisoformat(row["observation_date"])] = float(v)
    print(f"  {series_id}: {len(out)} obs, last {max(out) if out else '-'}", file=sys.stderr)
    return out


def asof(series, d, max_gap=10):
    """Latest value on or before d (within max_gap days), else None."""
    for k in range(max_gap + 1):
        v = series.get(d - timedelta(days=k))
        if v is not None:
            return v
    return None


def r(v, nd):
    return None if v is None else round(v, nd)


def build():
    print("Downloading FRED series...", file=sys.stderr)
    w = {k: fetch(s) for k, s in WEEKLY.items()}
    rt = {k: fetch(s) for k, s in RATES.items()}
    m2 = fetch("M2SL")

    dates = sorted(d for d in w["total"] if d >= START)
    weekly = {"dates": [d.isoformat() for d in dates]}
    for k, s in w.items():
        # Millions -> billions.
        weekly[k] = [r(None if s.get(d) is None else s[d] / 1000, 1) for d in dates]

    rates = {"dates": weekly["dates"]}
    for k, s in rt.items():
        # Each series only exists for part of the period; don't carry it past its end.
        lo, hi = (min(s), max(s)) if s else (None, None)
        rates[k] = [r(asof(s, d), 2) if s and lo <= d <= hi + timedelta(days=7) else None for d in dates]

    d0, d1 = date(2019, 8, 1), date(2020, 1, 31)
    days = sorted(d for d in rt["effr"] if d0 <= d <= d1 and d.weekday() < 5)
    repo2019 = {"dates": [d.isoformat() for d in days]}
    for k in ("effr", "sofr", "upper", "lower", "ioer"):
        repo2019[k] = [r(rt[k].get(d), 2) for d in days]

    md = sorted(m2)
    m2out = {"dates": [], "yoy": [], "level": []}
    for d in md:
        prev = m2.get(date(d.year - 1, d.month, 1))
        if prev is None:
            continue
        m2out["dates"].append(d.isoformat()[:7])
        m2out["yoy"].append(round((m2[d] / prev - 1) * 100, 2))
        m2out["level"].append(round(m2[d], 1))

    return {
        "updated": datetime.utcnow().strftime("%Y-%m-%d"),
        "weekly": weekly, "rates": rates, "repo2019": repo2019, "m2": m2out,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "docs/learn/data/fed.js"))
    args = ap.parse_args()
    data = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, separators=(",", ":"))
    out.write_text(f'window.nexusData=window.nexusData||{{}};window.nexusData["fed"]={body};\n')
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
