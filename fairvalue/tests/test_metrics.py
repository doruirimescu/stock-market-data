from datetime import date

import pytest

from fvmodel import compare
from fvmodel.metrics import scoring
from fvmodel.metrics.base import cagr
from fvmodel.metrics.compute import _dcf_multiple


def test_cagr_needs_positive_endpoints():
    assert cagr([100, 110, 121, 133.1], 3) == pytest.approx(10.0)
    assert cagr([-1, 2, 3, 4], 3) is None
    assert cagr([1, 2], 3) is None


def test_dcf_multiple_matches_closed_form():
    # g = 0, d = 11%: 10 years of 1/(1.11)^i plus 10 terminal years at 4%.
    d, g, t = 0.11, 0.0, 0.04
    expected = sum((1 / (1 + d)) ** i for i in range(1, 11))
    x10 = (1 / (1 + d)) ** 10
    expected += x10 * sum(((1 + t) / (1 + d)) ** j for j in range(1, 11))
    assert _dcf_multiple(g, d) == pytest.approx(expected)
    # The reference provider's published lower bound for the Projected-FCF multiple (8.35)
    # is this zero-growth multiple at an 11% discount rate.
    assert _dcf_multiple(g, d) == pytest.approx(8.35, abs=0.05)


def test_interp_and_rank_bounds():
    assert scoring.interp(5, [(0, 0), (10, 10)]) == 5
    assert scoring.interp(50, [(0, 0), (10, 10)]) == 10
    assert scoring.financial_strength_rank(None, True, 0, 10, 0.9, None) == 10
    assert scoring.fair_value_rank(0.8) == 10
    assert scoring.fair_value_rank(0.2) < 10  # very cheap is not rewarded fully


def test_predictability_stars():
    steady = [10 * 1.08**i for i in range(10)]
    assert scoring.predictability_stars(steady, steady) == 5.0
    erratic = [10, 12, 9, 14, 8, 15, 7, 16, 9, 12]
    assert scoring.predictability_stars(erratic, erratic) <= 2.0
    assert scoring.predictability_stars(steady[:5], steady[:5]) is None


def test_evaluation_date_for_month_only_reference():
    assert compare.evaluation_date("2026-06", today=date(2026, 12, 31)) == date(2026, 9, 13)
    assert compare.evaluation_date("2026-09-01", today=date(2026, 12, 31)) == date(2026, 9, 1)
    assert compare.evaluation_date("2026-09-01", today=date(2026, 8, 1)) == date(2026, 8, 1)


def test_share_count_outlier_is_rescaled():
    import pandas as pd

    from fvmodel.metrics.history import _fix_share_outliers

    frame = pd.DataFrame({"shares": [415e6, 416e6, 415e9, 416e6, 420e6], "book": [17.0, 17.2, 0.0127, 12.7, 12.6],
                          "eps": [0.78, 1.34, -2.89, -2.82, -3.18]})
    fixed = _fix_share_outliers(frame)
    assert fixed["shares"].iloc[2] == pytest.approx(416e6, rel=0.01)
    assert fixed["book"].iloc[2] == pytest.approx(12.7, rel=0.02)
    assert fixed["eps"].iloc[2] == -2.89
