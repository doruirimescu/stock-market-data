from datetime import date

import numpy as np
import pandas as pd
import pytest

from fvmodel import backtest as bt


def test_membership_spells_and_dates():
    spells = bt.load_membership("ticker,start_date,end_date\nAAL,1996-01-02,1997-01-15\nAAL,2015-03-23,2024-09-23\n"
                                "NVDA,2001-11-30,\n")
    assert len(spells["AAL"]) == 2
    assert not bt.is_member(spells["AAL"], date(2010, 6, 30))
    assert bt.is_member(spells["AAL"], date(2015, 3, 31))
    assert not bt.is_member(spells["AAL"], date(2024, 9, 23))  # gone on its end date
    assert bt.is_member(spells["NVDA"], date(2026, 9, 30))
    assert bt.signal_dates(date(2013, 3, 31), date(2013, 12, 31)) == [
        date(2013, 3, 31), date(2013, 6, 30), date(2013, 9, 30), date(2013, 12, 31)]


def test_total_return_reinvests_dividends():
    idx = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03"])
    closes = pd.Series([100.0, 98.0, 99.0], idx)
    divs = pd.Series([2.0], idx[1:2])  # $2 paid as the price drops by $2
    tr = bt.total_return_index(closes, divs)
    assert tr.iloc[1] == pytest.approx(1.0)
    assert tr.iloc[2] == pytest.approx(99 / 98)


def test_forward_returns_only_when_realised():
    idx = pd.date_range("2020-01-01", "2021-06-30", freq="D")
    tr = pd.Series(np.linspace(1, 2, len(idx)), idx)
    out = bt.forward_returns(tr, date(2020, 3, 31), last_day=date(2021, 6, 30))
    assert out["3m"] == pytest.approx(tr["2020-06-30"] / tr["2020-03-31"] - 1)
    assert out["12m"] == pytest.approx(tr["2021-03-31"] / tr["2020-03-31"] - 1)
    assert out["36m"] is None


def test_quintiles_rank_highest_signal_first():
    q = bt.quintiles(pd.Series(range(10)))
    assert list(q) == [5, 5, 4, 4, 3, 3, 2, 2, 1, 1]


def test_newey_west_matches_plain_t_without_lags():
    x = np.array([0.02, -0.01, 0.03, 0.01, 0.0, 0.04])
    plain = x.mean() / (x.std() / np.sqrt(len(x)))
    assert bt.newey_west_t(x, 0) == pytest.approx(plain)
    assert bt.newey_west_t(x[:3], 1) is None


def test_signal_stats_finds_a_perfect_signal():
    rows = []
    for d in bt.signal_dates(date(2015, 3, 31), date(2016, 12, 31)):
        for i in range(bt.MIN_STOCKS):
            r = i / 1000  # return rises with the signal
            rows.append({"date": d.isoformat(), "ticker": f"T{i}", "gap": float(i), "quality": 50.0,
                         **{f"ret_{h}": r for h in bt.HORIZONS}})
    v = bt.add_signals(pd.DataFrame(rows))
    spy = pd.Series(1.0, pd.date_range("2015-01-01", "2020-01-01"))
    s = bt.signal_stats(v, "gap", spy)["horizons"]["12m"]
    assert s["ic"] == pytest.approx(1.0)
    assert s["hit_rate"] == 1.0
    assert s["excess"][0] > 0 > s["excess"][-1]
