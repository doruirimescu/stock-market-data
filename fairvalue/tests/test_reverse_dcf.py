import pytest

from fvmodel.metrics import reverse_dcf as rdcf


def test_iv15_defaults_are_thirty_times_owner_fcf():
    # Growth equal to the hurdle: each of the 15 years is worth today's cash flow,
    # and the 15x exit is worth 15 more.
    assert rdcf.iv15_value(1.0) == pytest.approx(30.0)


def test_iv15_matches_the_server_calculator():
    # compute_iv15 in server/calculators/iv_15.py, for $10 of owner FCF at 10% growth and 20x.
    cfs = [10 * 1.10**i for i in range(1, 16)]
    expected = sum(cf / 1.15**i for i, cf in enumerate(cfs, 1)) + cfs[-1] * 20 / 1.15**15
    assert rdcf.iv15_value(10, g=0.10, multiple=20) == pytest.approx(expected)


def test_dcf_value_is_gordon_growth_when_growth_equals_terminal():
    assert rdcf.dcf_value(1.0, 0.03, 0.09, years=10, terminal=0.03) == pytest.approx(1.03 / 0.06)


def test_implied_growth_round_trips():
    price = rdcf.dcf_value(2.0, 0.12, 0.10)
    assert rdcf.implied_growth(price, lambda g: rdcf.dcf_value(2.0, g, 0.10)) == pytest.approx(0.12, abs=1e-5)
    assert rdcf.implied_growth(rdcf.iv15_value(2.0), lambda g: rdcf.iv15_value(2.0, g)) == pytest.approx(0.15, abs=1e-5)


def test_implied_growth_outside_the_range_is_none():
    value = lambda g: rdcf.dcf_value(1.0, g, 0.10)
    assert rdcf.implied_growth(1e9, value) is None
    assert rdcf.implied_growth(0.0, value) is None


def test_discount_rate_stays_above_terminal_growth():
    assert rdcf.discount_rate(0.04) == pytest.approx(0.06)
    assert rdcf.discount_rate(0.11) == pytest.approx(0.11)
