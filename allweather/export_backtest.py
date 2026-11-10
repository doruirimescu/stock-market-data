"""tradelab run directories -> docs/data/allweather_backtest.js (the backtest section of the All-Weather page).

    python -m allweather.export_backtest      # uses the run dirs recorded by allweather.backtest

Reads equity.parquet, metrics.json, robustness.json and tables/year.csv of each run. The monthly allocation
history is recomputed with the same engine call the strategy makes (tradelab does not store positions).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from . import data as awdata
from . import engine
from .universe import CASH, SLEEVES, UNIVERSE

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs/data/allweather_backtest.js"
LABELS = {
    "gauges": "All-Weather gauges", "static": "Static all-weather", "sixty_forty": "60/40 (SPY/IEF)", "spy": "S&P 500 (SPY)",
    "gauges_ex_btc": "All-Weather gauges, no Bitcoin", "static_ex_btc": "Static all-weather, no Bitcoin",
}


def _r(v, nd=4):
    try:
        return None if v is None or v != v else round(float(v), nd)
    except (TypeError, ValueError):
        return None


def _equity(run_dir):
    e = pd.read_parquet(Path(run_dir) / "equity.parquet")["equity"]
    e.index = pd.DatetimeIndex(e.index).tz_convert("America/New_York").tz_localize(None).normalize()
    return e


def _series(e):
    """Weekly (Friday) samples of equity and drawdown, plus the last day."""
    wk = e.resample("W-FRI").last().dropna()
    if wk.index[-1] != e.index[-1]:
        wk = pd.concat([wk.iloc[:-1], e.iloc[-1:]])
    dd = e / e.cummax() - 1
    ddw = dd.resample("W-FRI").min().reindex(wk.index, method="ffill")
    return {"dates": [d.strftime("%Y-%m-%d") for d in wk.index], "equity": [round(v, 2) for v in wk],
            "drawdown": [round(100 * v, 2) for v in ddw]}


def _metrics(m):
    b = m.get("benchmark") or {}
    return {
        "cagr": _r(m.get("cagr")), "vol": _r(m.get("annual_vol")), "sharpe": _r(m.get("sharpe"), 3),
        "sortino": _r(m.get("sortino"), 3), "max_dd": _r(m.get("max_drawdown")), "calmar": _r(m.get("calmar"), 3),
        "final": _r(m.get("final_equity"), 2), "total_return": _r(m.get("total_return")),
        "costs": _r(m.get("total_costs"), 2), "turnover": _r(m.get("turnover_per_year"), 3),
        "worst_day": _r(m.get("worst_day")), "dd_days": m.get("max_dd_duration_days"),
        "corr_spy": _r(b.get("correlation"), 3), "beta_spy": _r(b.get("beta"), 3),
    }


def _years(run_dir):
    p = Path(run_dir) / "tables/year.csv"
    if not p.exists():
        return {}
    t = pd.read_csv(p)
    col = "return" if "return" in t.columns else t.columns[-1]
    return {str(int(y)): _r(v) for y, v in zip(t[t.columns[0]], t[col])}


def _spy(start, end, capital):
    px = awdata.load_prices(symbols=["SPY"])["SPY"]["close"]
    px = px[(px.index >= start) & (px.index <= end)]
    e = capital * px / px.iloc[0]
    r = e.pct_change().dropna()
    yrs = len(r) / 252
    dd = e / e.cummax() - 1
    ye = e.groupby(e.index.year).last()        # yearly return from the previous year's last close
    prev = pd.Series([capital] + ye.iloc[:-1].tolist(), index=ye.index)
    years = {str(y): _r(ye[y] / prev[y] - 1) for y in ye.index}
    m = {"cagr": _r((e.iloc[-1] / capital) ** (1 / yrs) - 1), "vol": _r(r.std() * 252 ** 0.5),
         "sharpe": _r(r.mean() / r.std() * 252 ** 0.5, 3), "max_dd": _r(dd.min()), "final": _r(e.iloc[-1], 2),
         "total_return": _r(e.iloc[-1] / capital - 1), "corr_spy": 1.0, "beta_spy": 1.0, "costs": 0, "turnover": 0}
    m["calmar"] = _r(m["cagr"] / abs(m["max_dd"]), 3)
    return e, m, years


def _robustness(runs):
    out = {}
    rb = json.loads((Path(runs["gauges"]) / "robustness.json").read_text())
    psr, bs = rb.get("psr", {}), rb.get("bootstrap", {})
    out["causality"] = bool(rb.get("causality", {}).get("ok"))
    out["psr0"] = _r(psr.get("psr0"), 4)
    out["bootstrap"] = {k: _r(bs.get(k), 3) for k in ("prob_sharpe_gt_0", "sharpe_p05", "sharpe_p50", "sharpe_p95",
                                                     "max_drawdown_p05", "max_drawdown_p50", "total_return_p05")}
    cs = rb.get("cost_sensitivity", {})
    out["costs"] = {"table": cs.get("table"), "breakeven": _r(cs.get("breakeven_cost_mult"), 1),
                    "positive_at_2x": cs.get("positive_at_2x")}
    reg = rb.get("regimes", {})
    out["regimes"] = {"n": reg.get("n_regimes"), "negative": reg.get("n_negative"), "worst": reg.get("worst")}
    years = _years(runs["gauges"])
    out["negative_years"] = sorted(y for y, v in years.items() if v is not None and v < 0)
    for key in ("optimize", "walkforward"):
        if key not in runs:
            continue
        r = json.loads((Path(runs[key]) / "robustness.json").read_text())
        if key == "optimize":
            g, p, ps = r.get("grid", {}), r.get("pbo", {}), r.get("psr", {})
            out["grid"] = {"n_trials": g.get("n_trials"), "best_params": g.get("best_params"),
                           "plateau": _r(g.get("plateau_score"), 3), "dsr": _r(ps.get("dsr"), 4),
                           "pbo": _r(p.get("pbo"), 3), "prob_oos_loss": _r(p.get("prob_oos_loss"), 3)}
            gp = Path(runs[key]) / "grid_results.parquet"
            if gp.exists():
                t = pd.read_parquet(gp)
                cols = [c for c in t.columns if c in ("tilt", "rebalance", "objective", "total_return", "n_trades")]
                out["grid"]["table"] = json.loads(t[cols].to_json(orient="records"))
            out["verdict"] = r.get("verdict")
        else:
            w = r.get("walkforward", {})
            out["walkforward"] = {"efficiency": _r(w.get("efficiency"), 3), "oos_sharpe": _r(w.get("oos_sharpe"), 3),
                                  "folds": w.get("n_folds"), "oos_total_return": _r(w.get("oos_total_return"), 4)}
    return out


def _allocation(start, tilt=1.0, rebalance="monthly"):
    px = awdata.load_prices()
    p2i = {a["proxy"]: a["id"] for a in UNIVERSE} | {CASH["proxy"]: CASH["id"]}
    close = pd.DataFrame({p2i[s]: d["close"] for s, d in px.items()})
    vol = pd.DataFrame({p2i[s]: d["volume"] for s, d in px.items()})
    macro = engine.macro_frame(awdata.load_fred(), awdata.EXTRA_SERIES)
    _, w = engine.run(close, vol, macro, tilt=tilt, rebalance=rebalance)
    w = w[w.index >= start]
    w = w[engine.rebalance_flags(w.index, "monthly")]
    sleeves = {s: [a["id"] for a in UNIVERSE if a["sleeve"] == s] for s in SLEEVES}
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in w.index],
        "sleeves": {s: [round(100 * v, 2) for v in w[ids].sum(axis=1)] for s, ids in sleeves.items()}
        | {"Cash": [round(100 * v, 2) for v in w[CASH["id"]]]},
    }


def export(runs, out=OUT):
    eq = {k: _equity(runs[k]) for k in ("gauges", "static", "sixty_forty", "gauges_ex_btc", "static_ex_btc") if k in runs}
    start, end = eq["gauges"].index[0], eq["gauges"].index[-1]
    capital = float(json.loads((Path(runs["gauges"]) / "metrics.json").read_text())["initial_capital"])
    result = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "start": start.strftime("%Y-%m-%d"),
              "end": end.strftime("%Y-%m-%d"), "capital": capital, "runs": {}}
    for k, e in eq.items():
        m = json.loads((Path(runs[k]) / "metrics.json").read_text())
        result["runs"][k] = {"label": LABELS[k], "metrics": _metrics(m), "years": _years(runs[k]), **_series(e)}
    se, sm, sy = _spy(start, end, capital)
    result["runs"]["spy"] = {"label": LABELS["spy"], "metrics": sm, "years": sy, **_series(se)}
    result["robustness"] = _robustness(runs)
    result["allocation"] = _allocation(start)
    out.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(result, separators=(",", ":"))
    out.write_text(f'window.nexusData=window.nexusData||{{}};window.nexusData["allweatherBacktest"]={body};\n')
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KB)", file=sys.stderr)


def main():
    from .backtest import STATE
    if not STATE.exists():
        sys.exit("No recorded runs: run `python -m allweather.backtest` first.")
    export(json.loads(STATE.read_text()))


if __name__ == "__main__":
    main()
