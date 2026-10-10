"""Fair Value: a recent median multiple times today's TTM fundamental.

Fair Value = median price-to-sales over the last FAIR_VALUE_MONTHS
             x TTM revenue per share
             x (1 + FAIR_VALUE_GROWTH_WEIGHT x last year's revenue-per-share growth)

Calibrated against 68 Fair Values the reference provider published in
Sep-Oct 2026 (docs/VALIDATION.md): median gap 1.9%, 60 of 67 within 10%.
The growth term stands in for the provider's forward estimates, which fast
growers would otherwise miss by 10-15%.

When the primary multiple is unavailable (no revenue tag, too little
history), the median of the other multiples' values over the same window is used.

Kept apart from compute.py so the calibration can re-run it on stored inputs
with different settings in config.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .. import config
from .base import clamp

# Multiple -> the per-share fundamental it divides the price by (history.MULTIPLES).
FUNDAMENTAL = {"pe": "eps", "pe_nri": "eps_nri", "ps": "revenue", "pb": "book", "pfcf": "fcf"}
COMPONENTS = ("ps", "pe_nri", "pb", "pfcf")


def window(mult: pd.DataFrame) -> pd.DataFrame:
    """The last FAIR_VALUE_MONTHS of the daily multiple series."""
    if mult.empty:
        return mult
    return mult[mult.index >= mult.index[-1] - pd.DateOffset(months=config.FAIR_VALUE_MONTHS)]


def window_medians(mult: pd.DataFrame, strict: bool) -> dict[str, float]:
    """Median of each multiple over the window, where there is enough history.

    strict (the primary multiple): valid on FAIR_VALUE_MIN_VALID_SHARE of the
    window's trading days (about 252 a year, so a listing younger than the
    window fails). Otherwise one year of valid days is enough.
    """
    w = window(mult)
    need = config.FAIR_VALUE_MIN_VALID_SHARE * 252 * config.FAIR_VALUE_MONTHS / 12 if strict else 250
    return {k: float(w[k].median()) for k in w.columns if w[k].notna().sum() >= need}


def fair_value(mult: pd.DataFrame, fund_now: dict, revenue_growth: float | None,
               ) -> tuple[float | None, dict, dict, float]:
    """Return (fair value, parts, weights, growth adjustment).

    parts/weights say which multiple values the base came from; the fair value
    is their weighted mean times the adjustment.
    """
    def value(k, medians):
        now = fund_now.get(FUNDAMENTAL[k])
        return medians[k] * now if k in medians and now is not None and now > 0 else None

    strict, loose = window_medians(mult, True), window_medians(mult, False)
    parts, weights = {}, {}
    for k, w in config.FAIR_VALUE_WEIGHTS.items():
        if (v := value(k, strict)) is not None:
            parts[k], weights[k] = v, w
    if not parts:
        others = [v for k in COMPONENTS if (v := value(k, loose)) is not None]
        if not others:
            return None, {}, {}, 1.0
        parts, weights = {"median": float(np.median(others))}, {"median": 1.0}
    adj = 1.0
    if revenue_growth is not None:
        adj = 1 + config.FAIR_VALUE_GROWTH_WEIGHT * clamp(revenue_growth, *config.FAIR_VALUE_GROWTH_CLIP)
    base = sum(parts[k] * weights[k] for k in parts) / sum(weights.values())
    return base * adj, parts, weights, adj
