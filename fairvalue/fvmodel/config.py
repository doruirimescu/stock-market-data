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

# Fair Value: median price-to-sales over the last 3 years x TTM revenue per
# share x a forward-growth term (metrics/fairvalue.py). Calibrated on 2026-10-10
# against 68 Fair Values the reference provider published in Sep-Oct 2026
# (docs/VALIDATION.md): median gap 1.9%, 60 of 67 within 10%. The window is a
# sharp optimum (24 months: 36 within 10%; 48 months: 41). The previous model,
# a 10-year median PE, had 24 within 10%: decade-old multiples misprice
# companies whose margins changed (AMZN: median PE 79 from its thin-margin
# years, Fair Value 3.7x the price).
FAIR_VALUE_MONTHS = 36
FAIR_VALUE_WEIGHTS = {"ps": 1.0}  # also for financials: BAC, UNH, ARE fit within 9%
FAIR_VALUE_MIN_VALID_SHARE = 0.9  # the primary multiple needs >= 90% valid days in the window
# Forward-growth term: 1 + weight x last year's revenue-per-share growth (clipped).
# Stands in for the provider's forward estimates (NVDA, AVGO, LLY, AMD were
# 10-15% low without it). 0.25 fits best; 0 and 0.5 leave a -2.4% / +2.9% bias.
FAIR_VALUE_GROWTH_WEIGHT = 0.25
FAIR_VALUE_GROWTH_CLIP = (-0.5, 0.5)
# EPS without NRI: other non-operating income below this share of pretax income
# is treated as recurring and left in EPS (see Fundamentals.eps_without_nri).
NRI_MIN_SHARE_OF_PRETAX = 0.10

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
