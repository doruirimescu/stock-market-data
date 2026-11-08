"""All-Weather gauges: causality (no look-ahead) and allocation rules, on synthetic data (no network)."""
import unittest
from datetime import date, timedelta

import numpy as np
import pandas as pd

from allweather import data as awdata
from allweather import engine
from allweather.universe import CASH, IDS, MAX_WEIGHT

MONTHLY = {"UNRATE", "PCEPILFE", "CFNAIMA3"}
WEEKLY = {"ICSA", "STLFSI4"}
QUARTERLY = {"GDP"}
START = date(1995, 1, 2)
END = date(2014, 12, 31)


def synthetic_fred(seed=1):
    rng = np.random.default_rng(seed)
    raw = {}
    for s in awdata.LAGS:
        if s in MONTHLY:
            dates = pd.date_range(START, END, freq="MS")
        elif s in QUARTERLY:
            dates = pd.date_range(START, END, freq="QS")
        elif s in WEEKLY:
            dates = pd.date_range(START, END, freq="W-SAT")
        else:
            dates = pd.bdate_range(START, END)
        steps = rng.normal(0, 0.01, len(dates))
        if s in ("DFEDTAR", "DFEDTARU"):
            steps = np.where(rng.random(len(dates)) < 0.01, rng.choice([-0.25, 0.25], len(dates)), 0.0)
        level = 3 + np.cumsum(steps)
        if s in ("PCEPILFE", "GDP", "ICSA", "DTWEXBGS"):
            level = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.005, len(dates))))
        raw[s] = {d.date(): float(v) for d, v in zip(dates, level)}
    return raw


def synthetic_prices(seed=2):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2000-01-03", END)
    ids = IDS + [CASH["id"]]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, (len(idx), len(ids))), axis=0)),
                         index=idx, columns=ids)
    volume = pd.DataFrame(1e6, index=idx, columns=ids)
    for late, listed in (("BTC", "2009-06-01"), (CASH["id"], "2003-03-03"), ("HYG", "2004-01-02")):
        pre = idx < pd.Timestamp(listed)
        close.loc[pre, late] = close.loc[~pre, late].iloc[0]
        volume.loc[pre, late] = 0.0
    return close, volume


def truncate_fred(raw, t):
    """Observations published by date t (observation date + release lag <= t)."""
    return {s: {d: v for d, v in obs.items() if d + timedelta(days=awdata.LAGS[s]) <= t} for s, obs in raw.items()}


class AllWeatherCausality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = synthetic_fred()
        cls.close, cls.volume = synthetic_prices()
        cls.macro = engine.macro_frame(cls.raw, awdata.EXTRA_SERIES)
        cls.g, cls.w = engine.run(cls.close, cls.volume, cls.macro)

    def test_prefix_invariance(self):
        """Scores and weights up to T are identical when everything after T is unknown."""
        for t in ("2006-03-15", "2009-07-01", "2012-11-30"):
            t = pd.Timestamp(t)
            macro_t = engine.macro_frame(truncate_fred(self.raw, t.date()), awdata.EXTRA_SERIES, last=t.date())
            g_t, w_t = engine.run(self.close.loc[:t], self.volume.loc[:t], macro_t)
            for name, full, cut in (("score", self.g["score"], g_t["score"]), ("weights", self.w, w_t)):
                a, b = full.loc[:t].to_numpy(), cut.loc[:t].to_numpy()
                self.assertTrue(np.allclose(a, b, equal_nan=True, atol=1e-9), f"{name} differs before {t.date()}")

    def test_future_poison(self):
        """Garbage prices after T change nothing up to T."""
        t = pd.Timestamp("2010-05-03")
        close = self.close.copy()
        close.loc[close.index > t] *= np.random.default_rng(9).uniform(0.2, 5.0, close.loc[close.index > t].shape)
        g_p, w_p = engine.run(close, self.volume, self.macro)
        self.assertTrue(np.allclose(self.w.loc[:t], w_p.loc[:t], equal_nan=True))
        self.assertTrue(np.allclose(self.g["score"].loc[:t], g_p["score"].loc[:t], equal_nan=True))


class AllWeatherAllocation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        close, volume = synthetic_prices()
        macro = engine.macro_frame(synthetic_fred(), awdata.EXTRA_SERIES)
        cls.g, cls.w = engine.run(close, volume, macro)

    def test_weights_valid(self):
        w = self.w.dropna()
        w = w[w.index >= w.index[(w.sum(axis=1) > 0).to_numpy().argmax()]]   # uninvested until assets have history
        self.assertTrue((w >= -1e-12).all().all())
        self.assertTrue(np.allclose(w.sum(axis=1), 1.0))
        self.assertLessEqual(w[IDS].max().max(), MAX_WEIGHT + 1e-9)

    def test_not_investable_before_history(self):
        btc = self.w["BTC"]
        self.assertEqual(btc.loc[:"2010-06-01"].abs().max(), 0.0)    # listed 2009-06, needs ~a year

    def test_weights_change_only_on_rebalance_days(self):
        w = self.w.dropna()
        changed = (w.diff().abs().sum(axis=1) > 1e-12).to_numpy()
        flags = engine.rebalance_flags(w.index)
        self.assertFalse((changed & ~flags).any())

    def test_static_is_base(self):
        row = {a: 0.0 for a in IDS}
        w = engine.target_weights(row, {a: True for a in IDS}, tilt=0.0)
        self.assertAlmostEqual(w["IEF"], 0.15)
        self.assertAlmostEqual(w[CASH["id"]], 0.0)

    def test_tilt_multiplier(self):
        self.assertEqual(engine.multiplier(-50, 1.0), 0.0)
        self.assertEqual(engine.multiplier(0, 1.0), 1.0)
        self.assertEqual(engine.multiplier(50, 1.0), 2.0)
        self.assertEqual(engine.multiplier(100, 1.0), 2.5)

    def test_every_zone_occupied(self):
        """The rank blend puts the best asset at >= +50 and the worst at <= -50 whenever their absolute scores
        are on the right side of zero."""
        s = self.g["score"].dropna(how="all").iloc[-1].dropna()
        a = self.g["absolute"].dropna(how="all").iloc[-1].dropna()
        if a.max() >= 0:
            self.assertGreaterEqual(s.max(), 50)
        if a.min() <= 0:
            self.assertLessEqual(s.min(), -50)


if __name__ == "__main__":
    unittest.main()
