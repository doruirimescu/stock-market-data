"""
US Treasury timing gauges: score current macro conditions for buying or selling
short-, mid- and long-term Treasuries, and track three UCITS ETFs per bucket.

    python scripts/bond_signals.py                    # -> docs/data/bonds.js
    python scripts/bond_signals.py --out some/file.js

Data: FRED's public CSV endpoint (no API key) and Yahoo Finance chart data for
the ETFs. Stdlib only. Run daily (see .github/workflows/bond-signals.yml).

Method
------
Each bucket has 6-7 indicators drawn from the bond-return-predictability
literature. Every indicator is turned into a score in [-1, +1] (+1 = conditions
favour owning that part of the curve, -1 = favour selling it), either with a
fixed scale or as a rolling 10-year z-score. A gauge is the mean score x 100, so
it runs from -100 (strong sell) to +100 (strong buy).

No look-ahead: monthly and quarterly data become usable only after their usual
publication lag, and z-scores use only past data. Thresholds and scales were set
from economic reasoning, not fitted to returns; the backtest in the output is a
check on that, using constant-maturity yields to approximate bond returns.

Output (loaded as a <script>, so the page also works from disk):
    window.nexusData.bonds = { updated, asof, zones, gauges: {short, mid, long},
                               history: {dates, short, mid, long}, backtest }
"""

import argparse
import bisect
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import http_get_json  # noqa: E402
from fed_data import fetch  # noqa: E402  (plain-urllib FRED CSV fetch)

ROOT = Path(__file__).resolve().parent.parent
START = date(1990, 1, 2)
HISTORY_FROM = date(2000, 1, 1)
YEAR = 252  # business days

# Release lag in calendar days, counted from the date FRED stamps the
# observation with (the first day of the month/quarter for monthly/quarterly
# data, the week's end for weekly data).
SERIES = {
    "DFF": 1, "DFEDTARU": 0, "DFEDTAR": 0,
    "DGS2": 1, "DGS5": 1, "DGS10": 1, "DGS20": 1, "DTB3": 1,
    "T10Y3M": 1, "DFII5": 1, "DFII10": 1, "T5YIE": 1, "T10YIE": 1,
    "BAA10Y": 1, "THREEFYTP10": 1,
    "UNRATE": 37,       # first Friday of the next month
    "ICSA": 5,          # week ending Saturday, released the next Thursday
    "PCEPILFE": 60,     # end of the following month
    "CFNAIMA3": 55,     # about three weeks after the month ends
    "GDP": 120,         # advance estimate, ~4 weeks after the quarter ends
}

ZONES = [  # (upper bound, label, tone)
    (-50, "Strong sell", "negative"),
    (-20, "Sell", "negative"),
    (20, "Hold", "neutral"),
    (50, "Buy", "positive"),
    (101, "Strong buy", "positive"),
]

ETFS = {
    "short": [
        ("IB01.L", "iShares $ Treasury Bond 0-1yr UCITS ETF (Acc)", "0-1y"),
        ("IBTA.L", "iShares $ Treasury Bond 1-3yr UCITS ETF (Acc)", "1-3y"),
        ("TRS3.L", "SPDR Bloomberg 1-3 Year U.S. Treasury Bond UCITS ETF (Dist)", "1-3y"),
    ],
    "mid": [
        ("CBU7.L", "iShares $ Treasury Bond 3-7yr UCITS ETF (Acc)", "3-7y"),
        ("TRE7.L", "Invesco US Treasury Bond 3-7 Year UCITS ETF (Dist)", "3-7y"),
        ("CBU0.L", "iShares $ Treasury Bond 7-10yr UCITS ETF (Acc)", "7-10y"),
    ],
    "long": [
        ("IDTL.L", "iShares $ Treasury Bond 20+yr UCITS ETF (Dist)", "20y+"),
        ("LUTR.L", "SPDR Bloomberg 10+ Year U.S. Treasury Bond UCITS ETF (Dist)", "10y+"),
        ("TREL.L", "Invesco US Treasury Bond 10+ Year UCITS ETF (Dist)", "10y+"),
    ],
}

BUCKETS = {
    "short": {"label": "Short-term", "horizon": "0-3 years", "proxy": "DGS2", "maturity": 2,
              "summary": "Driven by the Fed: front-end yields follow the expected path of the policy rate."},
    "mid": {"label": "Mid-term", "horizon": "3-10 years", "proxy": "DGS5", "maturity": 5,
            "summary": "Driven by the business cycle: growth, jobs and inflation expectations."},
    "long": {"label": "Long-term", "horizon": "10+ years", "proxy": "DGS20", "maturity": 20,
             "summary": "Driven by valuation and risk: term premium, real yields, inflation and flight to safety."},
}


# ---------------------------------------------------------------- helpers

def clip(x, lo=-1.0, hi=1.0):
    return None if x is None else max(lo, min(hi, x))


def sub(a, b):
    return [None if x is None or y is None else x - y for x, y in zip(a, b)]


def lagdiff(a, n):
    return [None if i < n or a[i] is None or a[i - n] is None else a[i] - a[i - n] for i in range(len(a))]


def moving_avg(a, n):
    out, s, cnt, q = [], 0.0, 0, []
    for v in a:
        q.append(v)
        if v is not None:
            s += v
            cnt += 1
        if len(q) > n:
            old = q.pop(0)
            if old is not None:
                s -= old
                cnt -= 1
        out.append(s / cnt if cnt >= n * 0.9 else None)
    return out


def rolling_z(a, n=10 * YEAR, min_n=2 * YEAR):
    """z-score of each value against the trailing window (inclusive)."""
    out, s, s2, cnt, q = [], 0.0, 0.0, 0, []
    for v in a:
        q.append(v)
        if v is not None:
            s += v
            s2 += v * v
            cnt += 1
        if len(q) > n:
            old = q.pop(0)
            if old is not None:
                s -= old
                s2 -= old * old
                cnt -= 1
        if v is None or cnt < min_n:
            out.append(None)
            continue
        m = s / cnt
        sd = math.sqrt(max(s2 / cnt - m * m, 1e-12))
        out.append((v - m) / sd)
    return out


def align(series, lag, days):
    """Value usable on each calendar day: the latest observation published by then."""
    keys = sorted(series)
    avail = [k + timedelta(days=lag) for k in keys]
    out = []
    for d in days:
        i = bisect.bisect_right(avail, d) - 1
        out.append(series[keys[i]] if i >= 0 else None)
    return out


def monthly_transform(series, fn):
    """Apply fn(values, i) over a monthly/quarterly series; returns {date: value}."""
    keys = sorted(series)
    vals = [series[k] for k in keys]
    out = {}
    for i, k in enumerate(keys):
        v = fn(vals, i)
        if v is not None:
            out[k] = v
    return out


def zone_of(score):
    for hi, label, tone in ZONES:
        if score < hi:
            return label, tone
    return ZONES[-1][1], ZONES[-1][2]


def rnd(v, nd=2):
    return None if v is None else round(v, nd)


# ---------------------------------------------------------------- indicators

def build_inputs():
    print("Downloading FRED series...", file=sys.stderr)
    raw = {s: fetch(s) for s in SERIES}

    last = max(raw["DGS10"])
    days = [START + timedelta(days=i) for i in range((last - START).days + 1)]
    days = [d for d in days if d.weekday() < 5]

    def a(sid, series=None):
        return align(series if series is not None else raw[sid], SERIES[sid], days)

    target = {**raw["DFEDTAR"], **raw["DFEDTARU"]}  # single target to Dec 2008, then upper bound
    core_yoy = monthly_transform(raw["PCEPILFE"], lambda v, i: (v[i] / v[i - 12] - 1) * 100 if i >= 12 else None)
    core_3m = monthly_transform(raw["PCEPILFE"], lambda v, i: ((v[i] / v[i - 3]) ** 4 - 1) * 100 if i >= 3 else None)

    def sahm(v, i):
        if i < 14:
            return None
        ma = lambda j: sum(v[j - 2:j + 1]) / 3
        return ma(i) - min(ma(j) for j in range(i - 12, i))

    claims = monthly_transform(raw["ICSA"], lambda v, i: (sum(v[i - 3:i + 1]) / 4 / (sum(v[i - 25:i + 1]) / 26) - 1) * 100
                               if i >= 25 else None)
    ngdp = monthly_transform(raw["GDP"], lambda v, i: (v[i] / v[i - 4] - 1) * 100 if i >= 4 else None)

    x = {k: a(k) for k in ("DFF", "DGS2", "DGS5", "DGS10", "DGS20", "DTB3", "T10Y3M", "DFII5", "DFII10",
                           "T5YIE", "T10YIE", "BAA10Y", "THREEFYTP10", "CFNAIMA3")}
    x["target"] = align(target, 0, days)
    x["core_yoy"] = align(core_yoy, SERIES["PCEPILFE"], days)
    x["core_3m"] = align(core_3m, SERIES["PCEPILFE"], days)
    x["sahm"] = align(monthly_transform(raw["UNRATE"], sahm), SERIES["UNRATE"], days)
    x["claims"] = align(claims, SERIES["ICSA"], days)
    x["ngdp"] = align(ngdp, SERIES["GDP"], days)
    x["unrate"] = a("UNRATE")
    return days, x, raw


def indicators(x):
    """Indicator definitions per bucket: raw value series + score series."""
    real_ff = sub(x["DFF"], x["core_yoy"])
    tgt_6m = lagdiff(x["target"], 126)
    d2_3m = lagdiff(x["DGS2"], 63)
    be5_3m = lagdiff(x["T5YIE"], 63)
    be10_3m = lagdiff(x["T10YIE"], 63)
    baa_3m = lagdiff(x["BAA10Y"], 63)
    gap5 = sub(x["DGS5"], moving_avg(x["DGS5"], 200))
    gap20 = sub(x["DGS20"], moving_avg(x["DGS20"], 200))
    y_vs_g = sub(x["DGS10"], x["ngdp"])

    def z_score(series):
        return [clip(None if z is None else z / 2) for z in rolling_z(series)]

    def lin(series, scale, centre=0.0, sign=1):
        return [clip(None if v is None else sign * (v - centre) / scale) for v in series]

    sahm = {
        "id": "sahm", "name": "Labour-market turn (Sahm)", "unit": "pp", "value": x["sahm"],
        "score": lin(x["sahm"], 0.3, centre=0.2),
        "desc": "3-month average unemployment rate minus its low of the past 12 months. Rising unemployment "
                "precedes Fed cuts and lower yields; a reading above 0.5 has marked every US recession since 1970.",
        "rule": "+1 at 0.5pp or more, 0 at 0.2pp, -1 at -0.1pp or less",
    }
    core = {
        "id": "core", "name": "Core inflation pace", "unit": "%", "value": x["core_3m"],
        "score": lin(x["core_3m"], 1.5, centre=2.0, sign=-1),
        "desc": "Core PCE inflation over the last 3 months, annualised, against the Fed's 2% target. "
                "Hot inflation keeps policy tight and pushes yields up.",
        "rule": "+1 at 0.5% or less, 0 at 2%, -1 at 3.5% or more",
    }

    return {
        "short": [
            {"id": "realff", "name": "Real policy rate", "unit": "%", "value": real_ff, "score": z_score(real_ff),
             "desc": "Effective fed funds rate minus core PCE inflation (year on year). A high real rate is "
                     "restrictive and gives the Fed room to cut, which lifts short-term bond prices.",
             "rule": "10-year z-score / 2: high real rate = buy"},
            {"id": "fedpath", "name": "Fed direction", "unit": "pp", "value": tgt_6m,
             "score": lin(tgt_6m, 0.75, sign=-1),
             "desc": "Change in the fed funds target over the last 6 months. Cutting cycles tend to continue "
                     "and carry front-end yields down; hiking cycles push them up.",
             "rule": "+1 after 75bp of cuts, -1 after 75bp of hikes"},
            {"id": "y2mom", "name": "2-year yield momentum", "unit": "pp", "value": d2_3m,
             "score": lin(d2_3m, 0.5, sign=-1),
             "desc": "3-month change in the 2-year Treasury yield. Bond trends persist (time-series momentum): "
                     "falling yields tend to keep falling.",
             "rule": "+1 if the yield fell 50bp, -1 if it rose 50bp"},
            sahm,
            {"id": "claims", "name": "Jobless claims trend", "unit": "%", "value": x["claims"],
             "score": lin(x["claims"], 10),
             "desc": "Initial jobless claims, 4-week average against the 26-week average. A rise in layoffs is "
                     "the earliest weekly sign that the Fed will ease.",
             "rule": "+1 when claims run 10% above trend, -1 when 10% below"},
            core,
        ],
        "mid": [
            {"id": "real5", "name": "5-year real yield", "unit": "%", "value": x["DFII5"], "score": z_score(x["DFII5"]),
             "desc": "5-year TIPS yield: the inflation-adjusted return of a 5-year Treasury. Bonds are cheap "
                     "when it is high against its own history (bond value factor).",
             "rule": "10-year z-score / 2: high real yield = buy"},
            {"id": "trend5", "name": "5-year yield trend", "unit": "pp", "value": gap5, "score": lin(gap5, 0.4, sign=-1),
             "desc": "5-year yield minus its 200-day average. Yields below their average are in a downtrend, "
                     "which favours holding bonds.",
             "rule": "+1 at 40bp below the average, -1 at 40bp above"},
            {"id": "cfnai", "name": "Economic activity (CFNAI)", "unit": "", "value": x["CFNAIMA3"],
             "score": lin(x["CFNAIMA3"], 0.6, sign=-1),
             "desc": "Chicago Fed National Activity Index, 3-month average of 85 activity series; 0 is trend "
                     "growth, below -0.7 signals recession. Bond returns are countercyclical.",
             "rule": "+1 at -0.6 or less, -1 at +0.6 or more"},
            sahm,
            {"id": "be5", "name": "Inflation expectations (5y)", "unit": "pp", "value": be5_3m,
             "score": lin(be5_3m, 0.3, sign=-1),
             "desc": "3-month change in the 5-year breakeven inflation rate (nominal minus TIPS yield). "
                     "Rising expectations push nominal yields up.",
             "rule": "+1 if breakevens fell 30bp, -1 if they rose 30bp"},
            core,
        ],
        "long": [
            {"id": "tp", "name": "Term premium (10y)", "unit": "%", "value": x["THREEFYTP10"],
             "score": z_score(x["THREEFYTP10"]),
             "desc": "Kim-Wright 10-year term premium: the extra yield investors demand for locking money up "
                     "long instead of rolling short bills. A high premium means long bonds pay well for their risk.",
             "rule": "10-year z-score / 2: high premium = buy"},
            {"id": "real10", "name": "10-year real yield", "unit": "%", "value": x["DFII10"], "score": z_score(x["DFII10"]),
             "desc": "10-year TIPS yield. Long bonds are cheap when the real yield is high against its own history.",
             "rule": "10-year z-score / 2: high real yield = buy"},
            {"id": "slope", "name": "Yield-curve slope (10y-3m)", "unit": "pp", "value": x["T10Y3M"],
             "score": z_score(x["T10Y3M"]),
             "desc": "10-year minus 3-month yield. A steep curve predicts higher excess returns on long bonds "
                     "(Campbell-Shiller, Fama-Bliss); an inverted curve leaves little reward for duration.",
             "rule": "10-year z-score / 2: steep = buy"},
            {"id": "yvg", "name": "Yield vs nominal growth", "unit": "pp", "value": y_vs_g, "score": lin(y_vs_g, 2),
             "desc": "10-year yield minus nominal GDP growth over the past year. Yields well below nominal "
                     "growth (2021) are a poor deal; yields above it are attractive.",
             "rule": "+1 at 2pp above growth, -1 at 2pp below"},
            {"id": "be10", "name": "Inflation expectations (10y)", "unit": "pp", "value": be10_3m,
             "score": lin(be10_3m, 0.25, sign=-1),
             "desc": "3-month change in the 10-year breakeven inflation rate. Long bonds suffer most when "
                     "inflation expectations climb.",
             "rule": "+1 if breakevens fell 25bp, -1 if they rose 25bp"},
            {"id": "trend20", "name": "20-year yield trend", "unit": "pp", "value": gap20, "score": lin(gap20, 0.4, sign=-1),
             "desc": "20-year yield minus its 200-day average. Long yields below their average are trending "
                     "down, which favours holding long bonds.",
             "rule": "+1 at 40bp below the average, -1 at 40bp above"},
            {"id": "credit", "name": "Flight to quality", "unit": "pp", "value": baa_3m, "score": lin(baa_3m, 0.4),
             "desc": "3-month change in the Moody's Baa corporate spread over the 10-year Treasury. Widening "
                     "credit spreads signal risk-off, when money moves into long Treasuries.",
             "rule": "+1 if the spread widened 40bp, -1 if it narrowed 40bp"},
        ],
    }


# FRED series behind each indicator (for the "data as of" date and source links).
SOURCES = {
    "realff": ["DFF", "PCEPILFE"], "fedpath": ["DFEDTARU"], "y2mom": ["DGS2"], "sahm": ["UNRATE"],
    "claims": ["ICSA"], "core": ["PCEPILFE"], "real5": ["DFII5"], "trend5": ["DGS5"], "cfnai": ["CFNAIMA3"],
    "be5": ["T5YIE"], "tp": ["THREEFYTP10"], "real10": ["DFII10"], "slope": ["T10Y3M"], "yvg": ["DGS10", "GDP"],
    "be10": ["T10YIE"], "trend20": ["DGS20"], "credit": ["BAA10Y"],
}


def gauge_series(inds, n):
    out = []
    need = (len(inds) + 1) // 2
    for i in range(n):
        s = [ind["score"][i] for ind in inds if ind["score"][i] is not None]
        out.append(100 * sum(s) / len(s) if len(s) >= need else None)
    return out


# ---------------------------------------------------------------- backtest

def bond_returns(y, bill, maturity):
    """Daily excess return of a constant-maturity par bond, from its yield (%)."""
    out = [None]
    for i in range(1, len(y)):
        y0, y1, b = y[i - 1], y[i], bill[i - 1]
        if None in (y0, y1, b):
            out.append(None)
            continue
        r = max(y0, 0.01) / 100
        dur = (1 - (1 + r / 2) ** (-2 * maturity)) / r  # modified duration of a par bond
        dy = (y1 - y0) / 100
        out.append(y0 / 100 / YEAR - dur * dy + 0.5 * dur * dur * dy * dy - b / 100 / YEAR)
    return out


def forward_sum(r, h):
    out = [None] * len(r)
    for i in range(len(r) - h):
        w = r[i + 1:i + 1 + h]
        if all(v is not None for v in w):
            out[i] = sum(w)
    return out


def spearman(a, b):
    def ranks(v):
        order = sorted(range(len(v)), key=v.__getitem__)
        rk = [0.0] * len(v)
        for pos, idx in enumerate(order):
            rk[idx] = pos
        return rk
    ra, rb = ranks(a), ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = sum((x - ma) ** 2 for x in ra)
    vb = sum((y - mb) ** 2 for y in rb)
    return cov / math.sqrt(va * vb)


def backtest(days, g, x, bucket, h=126):
    meta = BUCKETS[bucket]
    fwd = forward_sum(bond_returns(x[meta["proxy"]], x["DTB3"], meta["maturity"]), h)
    pairs = [(g[i], fwd[i]) for i in range(len(days)) if days[i] >= HISTORY_FROM and g[i] is not None and fwd[i] is not None]
    first = next(days[i] for i in range(len(days)) if days[i] >= HISTORY_FROM and g[i] is not None and fwd[i] is not None)
    rows = []
    for (hi, label, tone), lo in zip(ZONES, [-101] + [z[0] for z in ZONES[:-1]]):
        sel = [f for s, f in pairs if lo <= s < hi]
        rows.append({
            "zone": label, "tone": tone, "share": rnd(100 * len(sel) / len(pairs), 1),
            "fwd": rnd(100 * sum(sel) / len(sel) * YEAR / h, 2) if sel else None,  # annualised
            "hit": rnd(100 * sum(1 for f in sel if f > 0) / len(sel), 1) if sel else None,
        })
    allf = [f for _, f in pairs]
    return {
        "from": first.isoformat(), "horizon_days": h, "proxy": meta["proxy"],
        "ic": rnd(spearman([s for s, _ in pairs], allf), 3),
        "base_fwd": rnd(100 * sum(allf) / len(allf) * YEAR / h, 2),
        "zones": rows,
    }


# ---------------------------------------------------------------- ETFs

def etf_data(symbol, name, maturity):
    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=2y&interval=1d"
    try:
        res = http_get_json(url)["chart"]["result"][0]
    except Exception as e:  # noqa: BLE001 - the gauges are still useful without one ETF
        print(f"  {symbol}: failed ({e})", file=sys.stderr)
        return {"symbol": symbol.split(".")[0], "yahoo": symbol, "name": name, "maturity": maturity}
    ts = res["timestamp"]
    adj = res["indicators"]["adjclose"][0]["adjclose"]
    close = res["indicators"]["quote"][0]["close"]
    pts = [(datetime.fromtimestamp(t, timezone.utc).date(), a, c) for t, a, c in zip(ts, adj, close) if a and c]
    d_last, a_last, c_last = pts[-1]

    def ret_since(d0):
        base = next((a for d, a, _ in pts if d >= d0), None)
        return rnd((a_last / base - 1) * 100) if base else None

    ma200 = sum(a for _, a, _ in pts[-200:]) / min(200, len(pts))
    year = [(d, a) for d, a, _ in pts if d >= d_last - timedelta(days=365)]
    a0 = year[0][1]
    print(f"  {symbol}: {len(pts)} days, last {d_last}", file=sys.stderr)
    return {
        "symbol": symbol.split(".")[0], "yahoo": symbol, "name": name, "maturity": maturity,
        "currency": res["meta"].get("currency"), "price": rnd(c_last, 3), "asof": d_last.isoformat(),
        "r1m": ret_since(d_last - timedelta(days=30)), "r3m": ret_since(d_last - timedelta(days=91)),
        "r6m": ret_since(d_last - timedelta(days=182)), "r1y": ret_since(d_last - timedelta(days=365)),
        "ytd": ret_since(date(d_last.year, 1, 1)),
        "vs200": rnd((a_last / ma200 - 1) * 100),
        "chart": {"dates": [d.isoformat() for d, _ in year], "idx": [rnd(100 * a / a0, 2) for _, a in year]},
    }


# ---------------------------------------------------------------- build

def build():
    days, x, raw = build_inputs()
    inds = indicators(x)
    n = len(days)
    i_now = n - 1
    i_week = max(0, i_now - 5)
    i_month = max(0, i_now - 21)

    gauges, hist = {}, {}
    weekly = [i for i, d in enumerate(days) if d >= HISTORY_FROM and d.weekday() == 4] + [i_now]
    weekly = sorted(set(weekly))
    for b, meta in BUCKETS.items():
        g = gauge_series(inds[b], n)
        hist[b] = [rnd(g[i], 1) for i in weekly]
        score = g[i_now]
        label, tone = zone_of(score)
        print(f"{b:>5}: {score:+.0f} {label}", file=sys.stderr)
        rows = []
        for ind in inds[b]:
            src = SOURCES[ind["id"]]
            rows.append({
                "id": ind["id"], "name": ind["name"], "desc": ind["desc"], "rule": ind["rule"], "unit": ind["unit"],
                "value": rnd(ind["value"][i_now], 2), "score": rnd(ind["score"][i_now], 2),
                "score_month": rnd(ind["score"][i_month], 2),
                "src": src, "asof": min(max(raw[s]) for s in src).isoformat(),
            })
        print("Fetching ETFs...", file=sys.stderr)
        gauges[b] = {
            **{k: meta[k] for k in ("label", "horizon", "summary")},
            "score": rnd(score, 1), "zone": label, "tone": tone,
            "week": rnd(g[i_week], 1), "month": rnd(g[i_month], 1),
            "indicators": rows,
            "etfs": [etf_data(*e) for e in ETFS[b]],
            "backtest": backtest(days, g, x, b),
        }

    snapshot = {k: rnd(x[k][i_now], 2) for k in ("DFF", "DTB3", "DGS2", "DGS5", "DGS10", "DGS20", "DFII10", "T10YIE",
                                                 "THREEFYTP10", "unrate", "core_yoy")}
    return {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "asof": days[i_now].isoformat(),
        "fred_last": {k: max(v).isoformat() for k, v in raw.items() if v},
        "zones": [{"hi": hi, "label": label, "tone": tone} for hi, label, tone in ZONES],
        "snapshot": snapshot,
        "gauges": gauges,
        "history": {"dates": [days[i].isoformat() for i in weekly], **hist},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "docs/data/bonds.js"))
    args = ap.parse_args()
    data = build()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(data, separators=(",", ":"))
    out.write_text(f'window.nexusData=window.nexusData||{{}};window.nexusData["bonds"]={body};\n')
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
