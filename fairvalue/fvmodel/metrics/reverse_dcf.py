"""Reverse DCF and IV15: what growth the price implies, and the 15%-hurdle value.

Both start from owner FCF per share: TTM free cash flow minus stock-based
compensation (SBC is added back in operating cash flow but is a real cost to
shareholders), divided by diluted shares.

Reverse DCF: the growth g for which REVERSE_DCF_YEARS of owner FCF growing at g,
then growing at REVERSE_DCF_TERMINAL_GROWTH forever, discounted at the cost of
equity, is worth exactly the price.

IV15: the server calculator's model (server/calculators/iv_15.py). Owner FCF
grows at IV15_GROWTH for IV15_YEARS, is sold at IV15_TERMINAL_MULTIPLE x the
last year's cash flow, and everything is discounted at the IV15_HURDLE rate.
Its reverse is the growth needed to earn the hurdle rate at today's price.

Kept apart from compute.py so the formulas can be tested on plain numbers.
"""

from __future__ import annotations

from collections.abc import Callable

from .. import config

GROWTH_RANGE = (-0.5, 1.0)  # implied growth outside this range is reported as not found


def dcf_value(base: float, g: float, r: float, years: int | None = None, terminal: float | None = None) -> float:
    """Value of `base` cash flow: `years` at growth g, then a growing perpetuity, discounted at r."""
    years = config.REVERSE_DCF_YEARS if years is None else years
    terminal = config.REVERSE_DCF_TERMINAL_GROWTH if terminal is None else terminal
    cf, pv = base, 0.0
    for i in range(1, years + 1):
        cf *= 1 + g
        pv += cf / (1 + r) ** i
    return pv + cf * (1 + terminal) / (r - terminal) / (1 + r) ** years


def iv15_value(base: float, g: float | None = None, multiple: float | None = None,
               hurdle: float | None = None, years: int | None = None) -> float:
    """IV15 per share, as compute_iv15 in the server calculator."""
    g = config.IV15_GROWTH if g is None else g
    multiple = config.IV15_TERMINAL_MULTIPLE if multiple is None else multiple
    hurdle = config.IV15_HURDLE if hurdle is None else hurdle
    years = config.IV15_YEARS if years is None else years
    cf, pv = base, 0.0
    for i in range(1, years + 1):
        cf *= 1 + g
        pv += cf / (1 + hurdle) ** i
    return pv + cf * multiple / (1 + hurdle) ** years


def implied_growth(price: float, value_at: Callable[[float], float], tol: float = 1e-6) -> float | None:
    """The growth rate at which value_at(g) equals the price (value rises with g)."""
    lo, hi = GROWTH_RANGE
    if not (value_at(lo) <= price <= value_at(hi)):
        return None
    for _ in range(100):
        mid = (lo + hi) / 2
        if value_at(mid) < price:
            lo = mid
        else:
            hi = mid
        if hi - lo < tol:
            break
    return (lo + hi) / 2


def discount_rate(cost_of_equity: float) -> float:
    """Cost of equity, kept a margin above the terminal growth so the perpetuity stays finite."""
    return max(cost_of_equity, config.REVERSE_DCF_TERMINAL_GROWTH + config.REVERSE_DCF_MIN_SPREAD)


def growth_curve(base: float, r: float, growths: list[float]) -> dict:
    """Value per share at each growth rate under both models (for the stock-page chart)."""
    return {
        "growth": [round(g * 100, 1) for g in growths],
        "reverse_dcf": [round(dcf_value(base, g, r), 2) for g in growths],
        "iv15": [round(iv15_value(base, g), 2) for g in growths],
    }
