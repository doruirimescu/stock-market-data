"""All-Weather gauges and allocation (pure functions, no I/O). Shared by the daily page build and the
tradelab backtest strategy, so both use exactly the same rules.

Gauge (-100 sell ... +100 buy) per asset = weighted mean of four components, each in [-1, +1]:

    trend     25%  price vs its 200-day average and 12-1 month momentum, both scaled by volatility
                   (time-series momentum, Moskowitz-Ooi-Pedersen 2012)
    relative  25%  rank among all investable assets by risk-adjusted 6- and 12-month momentum
                   (cross-sectional momentum)
    value     20%  equities, sectors, real assets, crypto: rank of the 4-year return ending a year ago,
                   reversed (long-term reversal, the "value everywhere" proxy of Asness-Moskowitz-Pedersen 2013);
                   TIPS: 10y real yield; corporates: credit spread (both as 10-year z-scores);
                   Treasuries: none (the bond gauges below already contain value)
    macro     30%  the asset's sensitivities times six macro factors (universe.py); for the three
                   Treasury buckets, the Treasury Timing gauges (scripts/bond_signals.py)

That weighted mean is the asset's absolute score. The published gauge blends it 50/50 with the asset's
rank among all investable assets on that score, so there is always a best and a worst place for capital.

Causality: every value at date t uses only prices up to t and macro data published by t (release lags in
data.LAGS / bond_signals.SERIES); rebalancing happens on the first trading day of a month (known without
seeing the next day).
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .universe import (BY_ID, CASH, CASH_FALLBACK, FIXED_INCOME, IDS, MAX_WEIGHT, MAX_WEIGHT_BY_ID, SLEEVES,
                       UNIVERSE, VALUE_SERIES)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import bond_signals as bs  # noqa: E402

COMPONENTS = {"trend": 0.25, "relative": 0.25, "value": 0.20, "macro": 0.30}
RANK_BLEND = 0.5   # gauge = 50% absolute conditions + 50% rank among all assets on those conditions
FACTORS = {
    "G": "Growth", "I": "Inflation", "S": "Financial stress", "R": "Falling rates", "U": "Stronger dollar",
    "Y": "Falling real yields",
}
ZONES = bs.ZONES
YEAR = 252
INVESTABLE_DAYS = 260   # days with real trading before an asset can be held (its indicators need a year)


def _clip(x):
    return x.clip(-1, 1)


def _rz(s, n=10 * YEAR, min_n=2 * YEAR):
    r = s.rolling(n, min_periods=min_n)
    return (s - r.mean()) / r.std(ddof=0)


def _mean(*parts):
    return pd.concat(parts, axis=1).mean(axis=1, skipna=True)


# ---------------------------------------------------------------- macro

def macro_frame(raw, extra_lags, last=None):
    """Macro factors and fixed-income valuation on a weekday calendar (values usable on each date).

    raw: {series: {date: value}} (FRED); extra_lags: release lags of the series not in bond_signals.SERIES;
    last: end of the calendar (default: the newest 10-year yield; pass the newest price date so that day's
    row uses everything published by then).
    Columns: G I S R U Y (factors, [-1, 1]), their sub-indicators (g_*, i_*, ...), bond_short/mid/long
    (Treasury Timing gauges / 100) and z_real10 / z_aaa / z_baa (value scores for TIPS and corporates).
    """
    days, x = bs.inputs_from_raw(raw, last)
    idx = pd.DatetimeIndex(days)
    n = len(days)

    def s(k):
        return pd.Series(np.array(x[k], dtype=float), index=idx)

    def extra(k):
        return pd.Series(np.array(bs.align(raw[k], extra_lags[k], days), dtype=float), index=idx)

    df = pd.DataFrame(index=idx)
    inds = bs.indicators(x)
    for b in ("short", "mid", "long"):
        df["bond_" + b] = np.array(bs.gauge_series(inds[b], n), dtype=float) / 100

    df["g_cfnai"] = _clip(s("CFNAIMA3") / 0.6)
    df["g_sahm"] = _clip(-(s("sahm") - 0.2) / 0.3)
    df["g_claims"] = _clip(-s("claims") / 10)
    df["i_core"] = _clip((s("core_3m") - 2.0) / 1.5)
    df["i_be5"] = _clip(s("T5YIE").diff(63) / 0.3)
    df["s_vix"] = _clip(_rz(extra("VIXCLS")) / 2)
    df["s_credit"] = _clip(s("BAA10Y").diff(63) / 0.4)
    df["s_fsi"] = _clip(extra("STLFSI4") / 1.5)
    df["r_10y"] = _clip(-s("DGS10").diff(63) / 0.5)
    df["r_fed"] = _clip(-s("target").diff(126) / 0.75)
    usd = extra("DTWEXBGS")
    df["u_usd"] = _clip(100 * np.log(usd / usd.shift(126)) / 5)
    df["y_real10"] = _clip(-s("DFII10").diff(63) / 0.4)

    df["G"] = _mean(df["g_cfnai"], df["g_sahm"], df["g_claims"])
    df["I"] = _mean(df["i_core"], df["i_be5"])
    df["S"] = _mean(df["s_vix"], df["s_credit"], df["s_fsi"])
    df["R"] = _mean(df["r_10y"], df["r_fed"])
    df["U"] = df["u_usd"]
    df["Y"] = df["y_real10"]

    df["z_real10"] = _clip(_rz(s("DFII10")) / 2)
    df["z_aaa"] = _clip(_rz(extra("AAA10Y")) / 2)
    df["z_baa"] = _clip(_rz(s("BAA10Y")) / 2)
    return df


# ---------------------------------------------------------------- gauges

def gauges(close, volume, macro):
    """Gauge components and scores.

    close, volume: DataFrame (date x asset id), dates on a trading calendar (pre-listing rows have volume 0).
    macro: macro_frame() output. Returns a dict of DataFrames (date x asset id): trend, relative, value,
    macro, score (-100..100, NaN when not investable) and investable (bool).
    """
    close = close[IDS]
    volume = volume[IDS]
    real_days = (volume > 0).cumsum()
    investable = real_days >= INVESTABLE_DAYS

    vol = np.log(close).diff().rolling(YEAR, min_periods=200).std() * np.sqrt(YEAR)
    ma200 = close.rolling(200).mean()
    mom12 = close.shift(21) / close.shift(YEAR) - 1
    mom6 = close.shift(21) / close.shift(126) - 1
    trend = (_clip((close / ma200 - 1) / (0.5 * vol)) + _clip(mom12 / vol)) / 2
    trend = trend.where(investable)

    ram = (mom12 / vol + mom6 / (vol * np.sqrt(0.5))) / 2
    ram = ram.where(investable)
    relative = _rank_scores(ram)

    # long-term reversal: return from 5 years to 1 year ago, ranked and reversed; needs 5 real years
    lt = (close.shift(YEAR) / close.shift(5 * YEAR) - 1).where(real_days >= 5 * YEAR + 5)
    lt = lt[[a for a in IDS if a not in FIXED_INCOME]]
    value = -_rank_scores(lt, min_assets=5)
    value = value.reindex(columns=IDS)

    m = macro.reindex(close.index, method="ffill")
    for a, col in VALUE_SERIES.items():
        value[a] = m[col]
    value = value.where(investable)

    mac = pd.DataFrame(index=close.index, columns=IDS, dtype=float)
    for a in UNIVERSE:
        beta = a["beta"]
        if isinstance(beta, str):          # "bond:short" -> Treasury Timing gauge
            mac[a["id"]] = m["bond_" + beta.split(":")[1]]
            continue
        num = sum(b * m[f].fillna(0) for f, b in beta.items())
        den = sum(abs(b) * m[f].notna() for f, b in beta.items())
        mac[a["id"]] = (num / den.replace(0, np.nan)).clip(-1, 1)
    mac = mac.where(investable)

    parts = {"trend": trend, "relative": relative, "value": value, "macro": mac}
    num = sum(COMPONENTS[k] * v.fillna(0) for k, v in parts.items())
    den = sum(COMPONENTS[k] * v.notna() for k, v in parts.items())
    absolute = (100 * num / den.replace(0, np.nan)).where(investable)
    # Rotation is relative: the capital has to go somewhere. Half of the gauge is the asset's own
    # conditions, half its rank among all investable assets on those conditions.
    rank = 100 * _rank_scores(absolute)
    score = (1 - RANK_BLEND) * absolute + RANK_BLEND * rank
    return {**parts, "absolute": absolute, "rank": rank, "score": score, "investable": investable, "vol": vol}


def _rank_scores(df, min_assets=3):
    """Row-wise rank mapped linearly to [-1, 1] (best = +1) among non-NaN entries."""
    r = df.rank(axis=1)
    n = df.notna().sum(axis=1)
    out = 2 * (r.sub(1)).div((n - 1).replace(0, np.nan), axis=0) - 1
    return out.where(n >= min_assets)


def zone(score):
    if score != score:
        return None, None
    for hi, label, tone in ZONES:
        if score < hi:
            return label, tone
    return ZONES[-1][1], ZONES[-1][2]


# ---------------------------------------------------------------- allocation

BASE = {a["id"]: a["base"] / 100 for a in UNIVERSE}
SLEEVE_MEMBERS = {s: [a["id"] for a in UNIVERSE if a["sleeve"] == s] for s in SLEEVES}


def multiplier(score, tilt):
    """Weight multiplier from a gauge: -50 -> 0x, 0 -> 1x, +50 -> 2x (tilt 1), capped at 1 + 1.5 * tilt."""
    return float(np.clip(1 + tilt * score / 50, 0, 1 + 1.5 * tilt))


def target_weights(score_row, investable_row, tilt=1.0, cash_id=CASH["id"]):
    """{asset id: weight} for one date; the cash share is keyed by cash_id."""
    w = {}
    for sleeve, members in SLEEVE_MEMBERS.items():
        mass = sum(BASE[a] for a in members)
        avail = [a for a in members if investable_row.get(a, False) and score_row.get(a) == score_row.get(a)]
        if not avail:
            continue                                    # the sleeve's share goes to cash
        sb = sum(BASE[a] for a in avail)
        for a in avail:
            w[a] = mass * BASE[a] / sb * multiplier(score_row[a], tilt)
    for a in w:
        w[a] = min(w[a], MAX_WEIGHT_BY_ID.get(a, MAX_WEIGHT))
    total = sum(w.values())
    if total > 1:
        w = {a: v / total for a, v in w.items()}
    w[cash_id] = max(0.0, 1 - sum(w.values()))
    return w


def rebalance_flags(dates, rebalance="monthly"):
    """True on the first trading day of each month (or ISO week) and on the first date."""
    d = pd.DatetimeIndex(dates)
    if rebalance == "monthly":
        key = d.year * 100 + d.month
    elif rebalance == "weekly":
        iso = d.isocalendar()
        key = (iso.year * 100 + iso.week).to_numpy()
    else:
        raise ValueError(f"rebalance must be monthly or weekly, not {rebalance!r}")
    key = np.asarray(key)
    flags = np.r_[True, key[1:] != key[:-1]]
    return flags


def allocate(score, investable, tilt=1.0, rebalance="monthly", cash_investable=None):
    """Target weights (date x [asset ids + cash id]) held between rebalance dates.

    cash_investable: bool Series; when False the cash share goes to CASH_FALLBACK (or stays uninvested).
    """
    cols = IDS + [CASH["id"]]
    out = np.full((len(score), len(cols)), np.nan)
    flags = rebalance_flags(score.index, rebalance)
    cur = None
    sc = score.to_dict("index")
    inv = investable.to_dict("index")
    for i, d in enumerate(score.index):
        if flags[i]:
            w = target_weights(sc[d], inv[d], tilt)
            if cash_investable is not None and not bool(cash_investable.get(d, False)):
                c = w.pop(CASH["id"])
                if inv[d].get(CASH_FALLBACK, False):
                    w[CASH_FALLBACK] = w.get(CASH_FALLBACK, 0.0) + c
            cur = np.array([w.get(c, 0.0) for c in cols])
        out[i] = cur
    return pd.DataFrame(out, index=score.index, columns=cols)


def run(close, volume, macro, tilt=1.0, rebalance="monthly", exclude=()):
    """Gauges + allocation for a price history that includes the cash proxy column.

    exclude: asset ids never held (their sleeve share is spread over the rest of the sleeve, or held as cash).
    """
    g = gauges(close, volume, macro)
    cash_inv = (volume[CASH["id"]] > 0).cumsum() >= 20
    inv = g["investable"].copy()
    for a in exclude:
        inv[a] = False
    w = allocate(g["score"], inv, tilt, rebalance, cash_inv)
    return g, w


def sleeve_of(asset_id):
    return BY_ID[asset_id]["sleeve"] if asset_id in BY_ID else "Cash"
