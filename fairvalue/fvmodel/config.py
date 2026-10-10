"""Tunable assumptions. The reference provider does not publish these; see docs/METHODOLOGY.md."""

# Debt includes operating-lease liabilities (the reference provider folds leases into
# "capital lease obligation" after ASC 842; unconfirmed).
INCLUDE_OPERATING_LEASES_IN_DEBT = True

# CAPM inputs (the reference provider: 10Y Treasury + beta x 6%).
EQUITY_RISK_PREMIUM = 0.06
BETA_YEARS = 3  # weekly returns over 3 years vs the S&P 500

# Earnings DCF (the reference provider defaults).
DCF_YEARS_GROWTH = 10
DCF_YEARS_TERMINAL = 10
DCF_TERMINAL_GROWTH = 0.04
DCF_GROWTH_CAP = 0.20
DCF_GROWTH_FLOOR = 0.05
DCF_ADD_TANGIBLE_BOOK = False

# Projected FCF growth-multiple bounds published by the reference provider.
PROJ_FCF_MULTIPLE = (8.35, 17.74)
PROJ_FCF_EQUITY_WEIGHT = 0.8

# Fair Value: 10-year median multiple x current TTM fundamental.
# Calibrated against the reference provider-published Fair Values for 9 stocks (docs/VALIDATION.md):
# the PE-based value alone fits best (mean abs error ~10%); an equal blend of
# PE/PS/PB/P-FCF fits worse (~17%) because the other multiples sit
# systematically below the reference provider. Fallbacks apply when EPS is negative or the
# PE history is too short.
FAIR_VALUE_YEARS = 10
FAIR_VALUE_WEIGHTS = {"pe": 1.0}
# Banks, insurers and REITs: earnings swing with credit and mark-to-market, and
# book value is the usual anchor. Not validated against the reference provider.
FAIR_VALUE_WEIGHTS_FINANCIAL = {"pb": 1.0}
FAIR_VALUE_FALLBACK = ("pfcf", "ps")
FAIR_VALUE_MIN_VALID_SHARE = 0.9  # the primary multiple needs >= 90% valid days in the window
# Robustness for a broad universe: the primary (PE, or PB for financials) value
# is used only if it is within this factor of the median of the other
# multiples' values; otherwise the median of all available components is used.
# Catches distorted histories (AMZN's thin-margin years gave a 10y median PE of
# ~80 and a "fair value" 4x the PS-based one). All 9 calibration stocks pass it.
FAIR_VALUE_CONSISTENCY = 2.0
# Young companies (recent IPOs and spin-offs) get a median-of-multiples value
# from as little as 3 years of trading history.
FAIR_VALUE_MIN_YEARS_FALLBACK = 3
FAIR_VALUE_GROWTH_ADJUSTMENT = False
FAIR_VALUE_ADJ_CLIP = (0.7, 1.3)
FAIR_VALUE_BASELINE_GROWTH = 0.05  # growth that earns no adjustment

# Quality Score weights over the five 1-10 ranks (the reference provider: profitability and
# growth weighted fully, the rest less).
QUALITY_SCORE_WEIGHTS = {
    "profitability": 1.0,
    "growth": 1.0,
    "financial_strength": 0.6,
    "fair_value": 0.6,
    "momentum": 0.4,
}

# Linear map from the weighted rank average (0-100) to the Quality Score:
# score = a + b * weighted_rank. Fitted to the 10 the reference provider-published Quality Scores
# in reference/ (in-sample MAE 3.5 points, leave-one-out MAE 4.4; uncalibrated
# MAE 12.6). The reference provider ranks against its whole universe, so large quality
# companies score higher than our fixed breakpoints alone suggest.
QUALITY_SCORE_LINEAR = (26.16, 0.815)
