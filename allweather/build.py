"""Daily build of the All-Weather page data -> docs/data/allweather.js.

    python -m allweather.build              # refresh the cache (Yahoo + FRED), then build
    python -m allweather.build --offline    # build from the existing cache

The backtest section has its own file (docs/data/allweather_backtest.js, from allweather.backtest).
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from . import data as awdata
from . import engine
from .universe import BY_ID, CASH, IDS, SLEEVES, UNIVERSE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data/allweather.js"
HISTORY_FROM = "2008-01-01"
CAPITAL = 10_000

FACTOR_PARTS = {
    "G": [("g_cfnai", "Chicago Fed activity index (3-month)"), ("g_sahm", "Sahm rule (unemployment turn), inverted"),
          ("g_claims", "Jobless claims vs trend, inverted")],
    "I": [("i_core", "Core PCE inflation, 3-month annualised vs 2%"), ("i_be5", "5-year breakeven inflation, 3-month change")],
    "S": [("s_vix", "VIX vs its 10-year history"), ("s_credit", "Baa credit spread, 3-month change"),
          ("s_fsi", "St. Louis Fed Financial Stress Index")],
    "R": [("r_10y", "10-year yield, 3-month change, inverted"), ("r_fed", "Fed funds target, 6-month change, inverted")],
    "U": [("u_usd", "Broad trade-weighted dollar, 6-month change")],
    "Y": [("y_real10", "10-year TIPS real yield, 3-month change, inverted")],
}
FACTOR_DESC = {
    "G": "Is the economy strong and improving? Helps equities, credit and commodities; hurts bonds.",
    "I": "Is inflation high or rising? Helps commodities, energy, TIPS; hurts nominal bonds and long-duration equities.",
    "S": "Are markets under financial stress? Helps Treasuries, gold and defensives; hurts equities, credit and crypto.",
    "R": "Are interest rates falling? Helps bonds, real estate, utilities and growth stocks.",
    "U": "Is the dollar strengthening? Hurts emerging markets, gold and commodities in dollar terms.",
    "Y": "Are real (inflation-adjusted) yields falling? The main driver of gold and silver.",
}


def _r(v, nd=3):
    return None if v is None or v != v else round(float(v), nd)


def load_frames():
    px = awdata.load_prices()
    p2i = {a["proxy"]: a["id"] for a in UNIVERSE} | {CASH["proxy"]: CASH["id"]}
    close = pd.DataFrame({p2i[s]: d["close"] for s, d in px.items()})
    volume = pd.DataFrame({p2i[s]: d["volume"] for s, d in px.items()})
    return close, volume


def ucits_quotes():
    """Last price and currency of each UCITS line (display only; failures are skipped)."""
    out = {}
    for a in UNIVERSE + [CASH]:
        try:
            res = awdata.http_get_json(f"https://query2.finance.yahoo.com/v8/finance/chart/{a['ucits']}?range=5d&interval=1d",
                                       retries=2)["chart"]["result"][0]
            m = res["meta"]
            out[a["id"]] = {"price": _r(m.get("regularMarketPrice"), 4), "currency": m.get("currency")}
        except Exception as e:  # noqa: BLE001
            print(f"  {a['ucits']}: {e}", file=sys.stderr)
    return out


def dispersion(score):
    """How often every zone is occupied at a monthly rebalance."""
    mon = score[engine.rebalance_flags(score.index)]
    bounds = [-101] + [z[0] for z in engine.ZONES[:-1]]
    occ = {label: ((mon >= lo) & (mon < hi)) for (hi, label, _), lo in zip(engine.ZONES, bounds)}
    all5 = np.logical_and.reduce([o.any(axis=1).to_numpy() for o in occ.values()])
    both = (occ["Strong buy"].any(axis=1) & occ["Strong sell"].any(axis=1)).to_numpy()
    return {"months": int(len(mon)), "all_zones": _r(100 * all5.mean(), 1), "strong_both": _r(100 * both.mean(), 1),
            "avg_per_zone": {k: _r(v.sum(axis=1).mean(), 2) for k, v in occ.items()}}


def correlations(close):
    wk = close.loc[HISTORY_FROM:, IDS].resample("W-FRI").last()
    r = np.log(wk).diff()
    c = r.corr(min_periods=104)
    iu = np.triu_indices(len(IDS), 1)
    vals = c.to_numpy()[iu]
    by_sleeve = {}
    for s in SLEEVES:
        ids = [a for a in IDS if BY_ID[a]["sleeve"] == s]
        if len(ids) > 1:
            sub = c.loc[ids, ids].to_numpy()[np.triu_indices(len(ids), 1)]
            by_sleeve[s] = _r(np.nanmean(sub), 2)
    return {"ids": IDS, "matrix": [[_r(v, 2) for v in row] for row in c.to_numpy()],
            "avg": _r(np.nanmean(vals), 2), "min": _r(np.nanmin(vals), 2), "max": _r(np.nanmax(vals), 2),
            "share_below_03": _r(100 * np.mean(vals[~np.isnan(vals)] < 0.3), 1), "by_sleeve": by_sleeve}


def build(offline=False):
    if not offline:
        awdata.refresh_prices()
        awdata.refresh_fred()
    close, volume = load_frames()
    raw = awdata.load_fred()
    macro = engine.macro_frame(raw, awdata.EXTRA_SERIES, last=close.index[-1].date())
    g, w = engine.run(close, volume, macro, tilt=1.0)
    sc = g["score"]
    d = sc.index[-1]
    i_week, i_month = max(0, len(sc) - 6), max(0, len(sc) - 22)
    target = engine.target_weights(sc.iloc[-1].to_dict(), g["investable"].iloc[-1].to_dict(), tilt=1.0)
    static = engine.target_weights(sc.iloc[-1].to_dict(), g["investable"].iloc[-1].to_dict(), tilt=0.0)
    last_reb = sc.index[engine.rebalance_flags(sc.index)][-1]
    held = w.loc[last_reb]
    quotes = {} if offline else ucits_quotes()

    assets = []
    for a in UNIVERSE:
        k = a["id"]
        s = sc[k].iloc[-1]
        label, tone = engine.zone(s)
        assets.append({
            "id": k, "name": a["name"], "sleeve": a["sleeve"], "proxy": a["proxy"], "ucits": a["ucits"],
            "ucits_name": a["ucits_name"], "quote": quotes.get(k),
            "score": _r(s, 1), "zone": label, "tone": tone,
            "absolute": _r(g["absolute"][k].iloc[-1], 1), "rank": _r(g["rank"][k].iloc[-1], 1),
            "week": _r(sc[k].iloc[i_week], 1), "month": _r(sc[k].iloc[i_month], 1),
            "components": {c: _r(g[c][k].iloc[-1], 2) for c in engine.COMPONENTS},
            "beta": a["beta"], "base": _r(a["base"], 2),
            "static": _r(100 * static.get(k, 0), 2), "target": _r(100 * target.get(k, 0), 2),
            "held": _r(100 * held[k], 2), "vol": _r(100 * g["vol"][k].iloc[-1], 1),
            "r1y": _r(100 * (close[k].iloc[-1] / close[k].iloc[-253] - 1), 1),
        })
    m_today = macro.reindex([d], method="ffill").iloc[0]
    factors = [{"id": f, "name": engine.FACTORS[f], "desc": FACTOR_DESC[f], "value": _r(m_today[f], 2),
                "month": _r(macro[f].reindex(sc.index, method="ffill").iloc[i_month], 2),
                "parts": [{"id": p, "name": n, "value": _r(m_today[p], 2)} for p, n in FACTOR_PARTS[f]]}
               for f in engine.FACTORS]

    hist = sc.loc[HISTORY_FROM:]
    mon = hist[engine.rebalance_flags(hist.index)]
    absolute = g["absolute"].loc[HISTORY_FROM:]
    result = {
        "updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "asof": d.strftime("%Y-%m-%d"),
        "macro_asof": max(max(v) for k, v in raw.items() if k in ("DGS10", "DFF")).isoformat(),
        "capital": CAPITAL, "zones": [{"hi": hi, "label": lab, "tone": t} for hi, lab, t in engine.ZONES],
        "sleeves": SLEEVES, "components": engine.COMPONENTS, "rank_blend": engine.RANK_BLEND,
        "assets": assets, "factors": factors,
        "cash": {**CASH, "target": _r(100 * target.get(CASH["id"], 0), 2), "static": _r(100 * static.get(CASH["id"], 0), 2),
                 "held": _r(100 * held[CASH["id"]], 2), "quote": quotes.get(CASH["id"])},
        "last_rebalance": last_reb.strftime("%Y-%m-%d"),
        "history": {"dates": [x.strftime("%Y-%m-%d") for x in mon.index],
                    "scores": {k: [_r(v, 0) for v in mon[k]] for k in IDS}},
        "dispersion": dispersion(hist), "dispersion_absolute": dispersion(absolute),
        "correlation": correlations(close),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(result, separators=(",", ":"))
    OUT.write_text(f'window.nexusData=window.nexusData||{{}};window.nexusData["allweather"]={body};\n')
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)", file=sys.stderr)
    top = sorted(assets, key=lambda a: -(a["score"] or -999))
    print("Top:", ", ".join(f"{a['id']} {a['score']:+.0f}" for a in top[:3]),
          "| Bottom:", ", ".join(f"{a['id']} {a['score']:+.0f}" for a in top[-3:]), file=sys.stderr)
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", action="store_true", help="use the cached data; skip downloads")
    build(**vars(ap.parse_args()))


if __name__ == "__main__":
    main()
