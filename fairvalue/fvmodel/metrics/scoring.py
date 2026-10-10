"""Fair Value ranks (1-10), Predictability stars and the Quality Score.

The reference provider publishes the inputs of each rank but not the mapping to 1-10.
The reference provider ranks against its whole universe; we have no universe, so each input
is mapped to 0-10 with fixed breakpoints (piecewise linear) and averaged.
"""

from __future__ import annotations

import math

import numpy as np

from .. import config


def interp(x: float | None, points: list[tuple[float, float]]) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    xs, ys = zip(*points)
    return float(np.interp(x, xs, ys))


def _rank(subscores: list[float | None]) -> int | None:
    vals = [s for s in subscores if s is not None]
    if not vals:
        return None
    return int(max(1, min(10, round(sum(vals) / len(vals)))))


def _strength_subscores(interest_coverage, no_debt, debt_to_revenue, altman_z, equity_to_asset, cash_to_debt):
    ic = 10.0 if no_debt else interp(interest_coverage, [(0, 0), (1.5, 2), (3, 4), (5, 6), (10, 8), (20, 10)])
    return [
        ic,
        interp(debt_to_revenue, [(0, 10), (0.25, 8), (0.5, 6), (1, 4), (2, 2), (4, 0)]),
        interp(altman_z, [(0, 0), (1.81, 3), (2.99, 6), (4, 8), (6, 10)]),
        interp(equity_to_asset, [(0, 1), (0.2, 4), (0.4, 7), (0.6, 9), (0.8, 10)]),
        10.0 if no_debt else interp(cash_to_debt, [(0, 1), (0.2, 4), (0.5, 6), (1, 8), (2, 10)]),
    ]


def financial_strength_rank(*inputs):
    return _rank(_strength_subscores(*inputs))


def solvency_score(*inputs) -> int | None:
    """0-100 balance-sheet strength: the Financial Strength inputs averaged, unrounded.

    The reference provider publishes only the 1-10 rank; this is the continuous score behind it,
    comparable in spirit to AlphaSpread's 0-100 solvency score.
    """
    vals = [v for v in _strength_subscores(*inputs) if v is not None]
    return int(round(sum(vals) / len(vals) * 10)) if len(vals) >= 2 else None


def profitability_rank(operating_margin, piotroski, margin_trend, years_profitable, predictability):
    return _rank([
        interp(operating_margin, [(-10, 0), (0, 3), (5, 6), (10, 7), (15, 8), (20, 9), (30, 10)]),
        None if piotroski is None else piotroski / 9 * 10,
        interp(margin_trend, [(-3, 2), (0, 6), (2, 10)]),
        None if years_profitable is None else years_profitable,
        None if predictability is None else 2 + (predictability - 1) / 4 * 8,
    ])


def growth_rank(rev_growth_5y, ebitda_growth_5y, rev_growth_10y):
    pts = [(-10, 0), (0, 3), (3, 5), (5, 6), (10, 8), (15, 9), (20, 10)]
    return _rank([interp(rev_growth_5y, pts), interp(ebitda_growth_5y, pts), interp(rev_growth_10y, pts)])


def fair_value_rank(price_to_fair_value):
    # Non-monotonic: The reference provider found the very cheapest stocks underperform too.
    return _rank([interp(price_to_fair_value, [(0.3, 6), (0.5, 8), (0.7, 10), (0.9, 10), (1.1, 7), (1.3, 4), (1.6, 2), (2.0, 1)])])


def momentum_rank(mom_12_1, mom_6_1, beta):
    if mom_12_1 is None or mom_6_1 is None:
        return None
    ratio = (mom_12_1 + mom_6_1) / 2 / max(beta or 1.0, 0.3)
    # Top score near the 70th percentile, not at the extreme.
    return _rank([interp(ratio, [(-40, 1), (-20, 3), (0, 5), (10, 7), (20, 10), (40, 9), (80, 6)])])


def predictability_stars(rev_ps: list[float], ebitda_ps: list[float]) -> float | None:
    """1-5 stars in half steps from 10 fiscal years of revenue and EBITDA per share."""
    if len(rev_ps) < 10 or len(ebitda_ps) < 10:
        return None
    rev, ebitda = rev_ps[-10:], ebitda_ps[-10:]
    if any(v is None or v <= 0 for v in rev + ebitda):
        return 1.0

    def r2(ys):
        x = np.arange(len(ys))
        y = np.log(ys)
        slope, icpt = np.polyfit(x, y, 1)
        resid = y - (slope * x + icpt)
        tot = ((y - y.mean()) ** 2).sum()
        return (1 - (resid**2).sum() / tot if tot else 1.0), slope

    r2_rev, s_rev = r2(rev)
    r2_eb, s_eb = r2(ebitda)
    declines_eb = sum(b < a * 0.98 for a, b in zip(ebitda, ebitda[1:]))
    declines_rev = sum(b < a * 0.98 for a, b in zip(rev, rev[1:]))
    stars = 5.0 - 0.5 * declines_eb - 0.5 * max(0, declines_rev - 1)
    worst = min(r2_rev, r2_eb)
    stars -= 0.5 * (worst < 0.9) + 0.5 * (worst < 0.75) + 0.5 * (worst < 0.5)
    if s_rev <= 0 or s_eb <= 0:
        stars -= 1
    return max(1.0, min(5.0, round(stars * 2) / 2))


def weighted_rank(ranks: dict[str, int | None]) -> float | None:
    """Weighted average of the available ranks, on a 0-100 scale."""
    w = config.QUALITY_SCORE_WEIGHTS
    have = {k: v for k, v in ranks.items() if v is not None and k in w}
    if len(have) < 3:
        return None
    return 10 * sum(w[k] * v for k, v in have.items()) / sum(w[k] for k in have)


def quality_score(ranks: dict[str, int | None]) -> int | None:
    s = weighted_rank(ranks)
    if s is None:
        return None
    a, b = config.QUALITY_SCORE_LINEAR
    return int(round(max(0, min(100, a + b * s))))
