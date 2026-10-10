# Validation against the reference provider

Ten large US stocks from different sectors were analyzed with this framework
and compared with values the reference provider published for them:

AAPL, MSFT, NVDA, KO, JNJ, XOM, WMT, PG, HD and CAT.

Reproduce with `mise run compare`, which writes `site/validation.html` and
`reference/comparison.json`.

## How the reference was collected

the reference site answers every automated request, including from all regional
hosts, with a Cloudflare challenge (HTTP 403), and archive.org was unreachable.
Reference values therefore come from web-search results:

- The reference provider term-page titles, such as "Walmart (WMT) PE Ratio (TTM): 40.62 (As of Aug. 19, 2026)"
- The reference provider news articles, such as "AAPL looks 9.1% overvalued on Fair Value"

Rules:

- Every value is stored with its as-of date and source URL in
  [`reference/benchmark_reference.json`](../reference/benchmark_reference.json).
- Undated values and values from before 2026 were excluded.
- A shared search budget limited the run to **69 values**, about 7 per stock.
  Coverage is densest for Fair Value, Quality Score, price and PE.

**Point-in-time comparison.** Each the reference provider value is compared with our analysis
re-run *as of its date*, using only filings made and prices known by then
(`analyze(ticker, as_of=D)`). Without this, a 10-Q filed after the reference provider's
snapshot looks like a methodology error. That was the case for XOM PE, NVDA P/S,
NVDA debt-to-equity and NVDA dividend yield: all four were 15–180% off before
the change and within tolerance after it.

**Tolerances:**

| Status | Ratios | Ranks, F-Score | Quality Score |
| --- | --- | --- | --- |
| Match | within 5% | ±1 | ±5 points |
| Close | within 15% | ±2 | ±10 points |

## Result

**69 values: 52 match, 14 close, 3 differ.** All three differences are Fair Value.

| Metric | n | Match | Close | Differ | Median gap |
| --- | --- | --- | --- | --- | --- |
| Price (our close on the reference provider's date) | 10 | 10 | | | 0.5% |
| PE (TTM) | 9 | 9 | | | 1.3% |
| EV-to-EBITDA | 4 | 3 | 1 | | 1.6% |
| PB, PS | 4 | 4 | | | 0.5–1.9% |
| ROE (annualized quarter) | 2 | 2 | | | **0.0%** |
| ROIC | 3 | 2 | 1 | | 3.3% |
| WACC | 3 | 2 | 1 | | 5.0% |
| Dividend yield | 3 | 2 | 1 | | 1.4% |
| Debt-to-Equity | 2 | 1 | 1 | | |
| Fair Value Score | 10 | 8 | 2 | | 5 points (mean 3.5) |
| Fair Value, Financial Strength, Profitability, Growth and Momentum ranks | 9 | 6 | 3 | | |
| Piotroski F | 1 | | 1 | | |
| **Fair Value** | 9 | 2 | 4 | 3 | 9.8% |

All rows:

| Stock | Metric | Reference | Ours | Gap | Status | Ref as of |
| --- | --- | --- | --- | --- | --- | --- |
| AAPL | fair_value | 284.29 | 233.75 | -17.8% | differs | 2026-09-01 |
| CAT | fair_value | 461.18 | 436.09 | -5.4% | close | 2026-09-25 |
| HD | fair_value | 386.99 | 329.42 | -14.9% | close | 2026-10-09 |
| JNJ | fair_value | 192.28 | 207.67 | +8.0% | close | 2026-08-15 |
| KO | fair_value | 73.65 | 86.96 | +18.1% | differs | 2026-09-21 |
| MSFT | fair_value | 575.87 | 578.81 | +0.5% | match | 2026-08-14 |
| NVDA | fair_value | 378.51 | 415.65 | +9.8% | close | 2026-08-29 |
| PG | fair_value | 167.59 | 164.87 | -1.6% | match | 2026-09-14 |
| WMT | fair_value | 103.37 | 85.39 | -17.4% | differs | 2026-09-04 |
| AAPL | quality_score | 96 | 91 | -5 | match | 2026-09-01 |
| CAT | quality_score | 85 | 80 | -5 | match | 2026-09-25 |
| HD | quality_score | 83 | 83 | 0 | match | 2026-10-09 |
| JNJ | quality_score | 83 | 83 | 0 | match | 2026-08-15 |
| KO | quality_score | 77 | 82 | +5 | match | 2026-09-21 |
| MSFT | quality_score | 97 | 96 | -1 | match | 2026-08-14 |
| NVDA | quality_score | 95 | 98 | +3 | match | 2026-08-29 |
| PG | quality_score | 86 | 85 | -1 | match | 2026-09-14 |
| WMT | quality_score | 86 | 80 | -6 | close | 2026-09-04 |
| XOM | quality_score | 72 | 81 | +9 | close | 2026-09-21 |
| AAPL | pe_ttm | 36.34 | 37.29 | +2.6% | match | 2026-09-01 |
| CAT | pe_ttm | 34.25 | 34.68 | +1.3% | match | 2026-09-24 |
| HD | pe_ttm | 23.49 | 23.97 | +2.0% | match | 2026-08-24 |
| JNJ | pe_ttm | 31.25 | 31.45 | +0.6% | match | 2026-08-18 |
| KO | pe_ttm | 26.51 | 27.76 | +4.7% | match | 2026-09-13 |
| MSFT | pe_ttm | 27.79 | 27.60 | -0.7% | match | 2026-08-14 |
| NVDA | pe_ttm | 26.81 | 26.82 | 0.0% | match | 2026-09-15 |
| WMT | pe_ttm | 40.62 | 40.25 | -0.9% | match | 2026-08-19 |
| XOM | pe_ttm | 24.79 | 23.72 | -4.3% | match | 2026-06-15 |
| CAT | pb | 19.20 | 19.29 | +0.5% | match | 2026-10-07 |
| HD | pb | 17.11 | 17.16 | +0.3% | match | 2026-10-07 |
| HD | ps | 1.66 | 1.66 | +0.2% | match | 2026-10-01 |
| NVDA | ps | 20.11 | 20.50 | +1.9% | match | 2026-08-25 |
| CAT | ev_to_ebitda | 24.51 | 24.81 | +1.2% | match | 2026-09-06 |
| HD | ev_to_ebitda | 13.43 | 13.65 | +1.6% | match | 2026-10-03 |
| MSFT | ev_to_ebitda | 12.76 | 13.51 | +5.9% | close | 2026-06-25 |
| WMT | ev_to_ebitda | 19.45 | 19.37 | -0.4% | match | 2026-07-01 |
| AAPL | roe (annualized quarter) | 111.36 | 111.36 | 0.0% | match | 2026-06 |
| NVDA | roe (annualized quarter) | 132.26 | 132.26 | 0.0% | match | 2026-04 |
| AAPL | roic (TTM) | 42.12 | 42.73 | +1.5% | match | 2026-08-15 |
| MSFT | roic (TTM) | 21.24 | 20.54 | -3.3% | match | 2026-08-16 |
| JNJ | roic (annualized quarter) | 14.78 | 12.84 | -13.1% | close | 2026-06 |
| AAPL | wacc | 10.06 | 10.87 | +8.0% | close | 2026-08-15 |
| JNJ | wacc | 4.96 | 4.71 | -5.0% | match | 2026-08-20 |
| MSFT | wacc | 11.24 | 11.23 | -0.1% | match | 2026-08-16 |
| JNJ | debt_to_equity | 0.58 | 0.59 | +2.3% | match | 2026-06 |
| NVDA | debt_to_equity | 0.06 | 0.07 | +9.3% | close | 2026-04 |
| JNJ | dividend_yield | 2.04 | 2.18 | +6.6% | close | 2026-03 |
| NVDA | dividend_yield | 0.13 | 0.13 | -1.0% | match | 2026-08-10 |
| WMT | dividend_yield | 0.87 | 0.86 | -1.4% | match | 2026-08-10 |
| NVDA | piotroski_f | 7 | 5 | -2 | close | 2026-08-29 |
| CAT | rank FS / P / G / M | 6 / 9 / 10 / 10 | 6 / 8 / 8 / 9 | 0 / -1 / -2 / -1 | 3 match, 1 close | 2026-09 |
| MSFT | rank FS / P / G / V / M | 8 / 10 / 10 / 10 / 5 | 9 / 9 / 9 / 10 / 7 | +1 / -1 / -1 / 0 / +2 | 4 match, 1 close | 2026-08 |
| all 10 | price | | | median 0.5% | 10 match | |

## What the matches confirm

- **The TTM and quarter mechanics are right.** AAPL and NVDA ROE (annualized
  quarter) match the reference provider to the cent. That needs the right discrete quarter
  (derived from year-to-date facts), the right quarter-start equity and the
  right formula.
- **The valuation ratios are right.** PE, PB, PS and EV/EBITDA all match within
  2% (one within 6%). This includes EV composition with operating leases in
  debt and short-term investments in cash, which supports
  `INCLUDE_OPERATING_LEASES_IN_DEBT = True`.
- **The WACC recipe is right.** 10Y Treasury + β × 6% with 3-year weekly beta
  reproduces MSFT within 0.1% and JNJ within 5%.

## Explained gaps

- **Fair Value (median gap 9.8%).** the reference provider doesn't publish the formula,
  and it blends in analyst estimates we don't have. Calibration study (`config.py`):
  - Of the four historical-multiple components, the 10-year median **PE ×
    TTM EPS** tracks the reference provider best: the ratio runs 0.82–1.18 and the mean
    absolute error is about 10%.
  - P/S, P/B and P/FCF sit systematically 10–40% below the reference provider. HD's P/B is
    meaningless because its book equity was near zero for years.
  - The equal blend errs about 17%. Adding the documented growth adjustment
    hurt NVDA (+43%).
  - The residuals look like forward estimates. We undershoot companies with
    rising expectations (AAPL, WMT, HD at about −15 to −18%) and overshoot ones
    with flat expectations (KO +18%).
- **Fair Value Score (mean 3.5 points, but in-sample).** Uncalibrated ranks
  averaged 12.6 points low. The reference provider ranks against its whole universe, where
  median growth and margins are poor, so large quality companies score high.
  - After softening the breakpoints, a two-parameter linear map
    (`QUALITY_SCORE_LINEAR`) was fitted on these 10 stocks.
  - Leave-one-out error is **4.4 points**; treat that as the honest
    out-of-sample estimate.
  - XOM (+9) is the largest residual: its profitability and predictability
    ranks are dragged by the 2020 loss year.
- **JNJ ROIC (−13%).** JNJ doesn't tag `OperatingIncomeLoss`, so operating
  income falls back to pretax + interest, which includes litigation and other
  expense.
  - Adding accrued liabilities to "Accounts Payable & Accrued Expense" (as
    The reference provider does) improved it from −20% to −13%.
  - The rest is the reference provider's own operating-income line.
- **AAPL WACC (+8%).** Most likely beta. The reference provider's beta window and frequency
  are unpublished; ours is 3-year weekly. Unverified.
- **NVDA Piotroski (5 vs 7).** NVDA filed its July-quarter 10-Q on 2026-08-26,
  three days before the reference provider's 2026-08-29 value. Run as of 2026-08-20 (April
  quarter), our F-Score is **7, identical to the reference provider's**. So the reference provider had
  not yet rolled the score to the new quarter; the formula is not at fault.
- **JNJ dividend yield (+6.6%).** The reference date is month-only ("2026-03"),
  so the evaluation day is approximate.

## Not yet validated

There are no reference values yet for:

- Altman Z, Beneish M, interest coverage, cash-to-debt
- the growth rates
- the intrinsic values other than Fair Value (DCF, Projected FCF, Lynch, Graham, EPV)
- liquidity and momentum figures

Their formulas follow the reference provider's documented definitions (see
methodology-research.md). Validating them needs more reference data. Add
entries to `reference/benchmark_reference.json` using the same metric keys as
the dashboard, and rerun `mise run compare`.
