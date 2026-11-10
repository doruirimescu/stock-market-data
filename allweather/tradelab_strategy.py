"""tradelab strategies for the All-Weather gauges (loaded through `strategy.path` in the run configs).

    allweather_gauges   gauge-tilted all-weather allocation (tilt 0 = the static all-weather base)
    fixed_weights       constant weights (the 60/40 benchmark)

Both are vector strategies: the weights returned for bar t are decided at t's close and filled by the
engine at t+1's open. Prices and volume come from the tradelab panel (so the causality harness covers
them); history before the panel's first bar is read from the same CSV files the panel loads, so the
indicators are warmed up on day one. Macro data comes from the FRED cache, with release lags applied by
the engine.
"""
import functools
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from allweather import data as awdata  # noqa: E402
from allweather import engine  # noqa: E402
from allweather.universe import CASH, UNIVERSE  # noqa: E402
from tradelab.strategy import Params, Strategy, register  # noqa: E402

PROXY_TO_ID = {a["proxy"]: a["id"] for a in UNIVERSE} | {CASH["proxy"]: CASH["id"]}
ID_TO_PROXY = {v: k for k, v in PROXY_TO_ID.items()}


@functools.lru_cache(maxsize=4)
def _macro(fred_path, mtime):
    return engine.macro_frame(awdata.load_fred(fred_path), awdata.EXTRA_SERIES)


@functools.lru_cache(maxsize=4)
def _history(prices_path, symbols, mtime):
    return awdata.load_prices(prices_path, list(symbols))


def _panel_frames(data, prices_path):
    """close/volume (naive date x asset id) = file history before the panel + the panel's own bars."""
    dates = pd.DatetimeIndex(data.session_dates().to_numpy()).normalize()
    syms = tuple(data.symbols)
    mt = max(Path(prices_path.format(symbol=s)).stat().st_mtime for s in syms)
    hist = _history(prices_path, syms, mt)
    out = {}
    for field in ("close", "volume"):
        panel = data.field(field).copy()
        panel.index = dates
        before = pd.DataFrame({s: hist[s][field] for s in syms})
        before = before[before.index < dates[0]]
        out[field] = pd.concat([before, panel]).rename(columns=PROXY_TO_ID)
    return out["close"], out["volume"], dates


class AllWeatherParams(Params):
    tilt: float = 1.0               # 0 = static all-weather base; 1 = gauge -50 -> 0x, +50 -> 2x
    rebalance: str = "monthly"      # monthly | weekly (first trading day)
    exclude: list[str] = []         # asset ids never held (e.g. ["BTC"])
    prices_path: str = str(awdata.PRICES / "{symbol}.csv")
    fred_path: str = str(awdata.FRED_FILE)


@register
class AllWeatherGauges(Strategy):
    name, mode = "allweather_gauges", "vector"
    Params = AllWeatherParams
    description = "All-weather base weights tilted by 22 asset-class gauges; rebalanced on the first trading day."

    def signals(self, data):
        p = self.params
        close, volume, dates = _panel_frames(data, p.prices_path)
        macro = _macro(p.fred_path, Path(p.fred_path).stat().st_mtime)
        _, w = engine.run(close, volume, macro, tilt=p.tilt, rebalance=p.rebalance, exclude=tuple(p.exclude))
        w = w.loc[dates].rename(columns=ID_TO_PROXY)
        w.index = data.index
        return w.reindex(columns=data.symbols).fillna(0.0)


class FixedParams(Params):
    weights: dict[str, float] = {"SPY": 0.6, "IEF": 0.4}


@register
class FixedWeights(Strategy):
    name, mode = "fixed_weights", "vector"
    Params = FixedParams
    description = "Constant target weights (e.g. the 60/40 benchmark)."

    def signals(self, data):
        return pd.DataFrame({s: float(self.params.weights.get(s, 0.0)) for s in data.symbols}, index=data.index)
