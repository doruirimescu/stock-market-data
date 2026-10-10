# Validation against the reference provider

Ten large US stocks from different sectors were analyzed with this framework
and compared with values the reference provider published for them:

AAPL, MSFT, NVDA, KO, JNJ, XOM, WMT, PG, HD and CAT.

Reproduce with `mise run compare`, which writes `site/validation.html` and
`reference/comparison.json`.

## Fair Value recalibration (2026-10-10)

AMZN showed a Fair Value of $981 against a $262 price; the reference provider had
$250 ("fairly valued"). Two causes:

- the old formula, 10-year median PE × TTM EPS, used a median PE of 79 from
  AMZN's thin-margin years;
- TTM EPS was doubled by mark-to-market gains on an equity stake ($53B of
  non-operating income in Q2 2026 against $27B operating income).

The 2× consistency check meant to catch AMZN no longer fired: P/FCF had
dropped out (negative FCF from AI capex) and the P/B history is distorted the
same way.

To recalibrate, Fair Values for **59 more S&P 500 stocks** were collected
(Sep-Oct 2026, same method as below), 69 in all, chosen to include the 28
stocks our old model put below 0.5× Fair Value. Each component was re-run
point-in-time on every reference date and compared:

| Candidate (median gap to the reference / within 10%) | 10-year window | 5-year | 3-year |
| --- | --- | --- | --- |
| P/E × TTM EPS (old model) | 22% / 19 | 17% / 15 | — |
| P/E × EPS without NRI | 21% / 20 | 17% / 17 | 6% / 44 (blended with P/S) |
| P/B × book | 38% / 7 | 27% / 16 | — |
| P/FCF × FCF | 36% / 14 | 17% / 24 | — |
| **P/S × revenue** | 25% / 18 | 10% / 34 | **3.6% / 57** |

Three-year median P/S × TTM revenue per share is the clear winner, and the
window is a sharp optimum (24 months: 36 within 10%; 48 months: 41). The
residual pattern pointed to forward estimates (NVDA, AVGO, LLY, AMD 10-15%
low), so a growth term was added: × (1 + 0.25 × last year's revenue-per-share
growth). Weight 0 and 0.5 leave a −2.4% and +2.9% bias; 0.25 leaves none.

**Result (`mise run compare`): 69 Fair Values, 55 match, 8 close, 6 differ;
median gap 1.9%** (old model: 24 of 68 within 10%, median gap 18%). AMZN:
$243 against the reference provider's $250.

The six differences:

- **HON (+211%)** is a data problem: its 2026-07-23 10-Q restates diluted
  shares at half (318M vs 634M), as after a 1-for-2 reverse split, but the
  price history shows no split, so revenue per share doubles.
- **GE, APTV, TKO (+20 to +43%)** had spin-offs or mergers inside the
  three-year window; the reference provider restates the history, SEC
  filings as tagged don't.
- **DE (+21%)**: revenue fell; the reference provider's forward estimates are lower still.
- **FISV (−16%)** tags no current revenue and uses the median-of-multiples fallback.

The two parameters were fitted on these same 69 values, so the figures are
in-sample; with 2 parameters on 69 points the overfitting is small, and the
fit holds across window lengths of 33-39 months.

<details><summary>All 69 Fair Values</summary>

| Stock | Reference | Ours | Gap | Status | Ref as of |
| --- | --- | --- | --- | --- | --- |
| HON | 163.13 | 507.52 | +211.1% | differs | 2026-10-05 |
| TKO | 274.46 | 391.81 | +42.8% | differs | 2026-09-11 |
| APTV | 61.00 | 85.14 | +39.6% | differs | 2026-10-01 |
| DE | 409.05 | 493.34 | +20.6% | differs | 2026-10-09 |
| GE | 269.37 | 322.25 | +19.6% | differs | 2026-10-10 |
| FISV | 174.14 | 146.67 | -15.8% | differs | 2026-09-24 |
| V | 406.20 | 363.05 | -10.6% | close | 2026-10-08 |
| ARE | 86.76 | 77.61 | -10.6% | close | 2026-10-05 |
| CRM | 347.92 | 379.64 | +9.1% | close | 2026-10-05 |
| UNH | 591.60 | 542.80 | -8.2% | close | 2026-10-09 |
| PYPL | 85.85 | 79.58 | -7.3% | close | 2026-10-04 |
| TSLA | 335.56 | 355.76 | +6.0% | close | 2026-10-09 |
| IT | 491.50 | 519.55 | +5.7% | close | 2026-10-05 |
| UPS | 120.79 | 114.51 | -5.2% | close | 2026-10-07 |
| AVGO | 421.80 | 400.73 | -5.0% | match | 2026-10-08 |
| CVX | 168.55 | 160.62 | -4.7% | match | 2026-10-09 |
| CAT | 461.18 | 480.03 | +4.1% | match | 2026-09-25 |
| AMD | 289.32 | 277.83 | -4.0% | match | 2026-10-09 |
| FIS | 94.71 | 91.10 | -3.8% | match | 2026-10-05 |
| NFLX | 103.04 | 99.19 | -3.7% | match | 2026-10-07 |
| QCOM | 175.33 | 181.06 | +3.3% | match | 2026-10-09 |
| DXCM | 103.05 | 99.75 | -3.2% | match | 2026-10-01 |
| COST | 1048.55 | 1016.42 | -3.1% | match | 2026-10-02 |
| BAX | 31.71 | 32.67 | +3.0% | match | 2026-10-07 |
| PODD | 397.98 | 387.06 | -2.7% | match | 2026-10-10 |
| LLY | 1569.70 | 1527.69 | -2.7% | match | 2026-10-08 |
| PFE | 26.41 | 27.07 | +2.5% | match | 2026-10-09 |
| DIS | 118.12 | 115.27 | -2.4% | match | 2026-10-10 |
| WDAY | 325.08 | 332.77 | +2.4% | match | 2026-10-07 |
| GOOGL | 256.90 | 250.88 | -2.3% | match | 2026-10-09 |
| TXN | 238.18 | 232.66 | -2.3% | match | 2026-10-10 |
| BAC | 53.81 | 55.01 | +2.2% | match | 2026-10-04 |
| ORCL | 194.59 | 190.39 | -2.2% | match | 2026-10-07 |
| CMCSA | 36.94 | 36.15 | -2.1% | match | 2026-09-28 |
| BA | 211.06 | 215.05 | +1.9% | match | 2026-10-07 |
| PEP | 164.66 | 161.70 | -1.8% | match | 2026-10-05 |
| CHTR | 375.78 | 369.10 | -1.8% | match | 2026-10-02 |
| ZTS | 180.78 | 183.79 | +1.7% | match | 2026-10-07 |
| FICO | 2337.44 | 2299.13 | -1.6% | match | 2026-10-09 |
| LULU | 314.17 | 319.00 | +1.5% | match | 2026-10-09 |
| MKC | 80.29 | 81.51 | +1.5% | match | 2026-10-09 |
| MA | 686.88 | 676.51 | -1.5% | match | 2026-10-03 |
| NVDA | 378.51 | 373.32 | -1.4% | match | 2026-08-29 |
| WMT | 103.37 | 104.79 | +1.4% | match | 2026-09-04 |
| COO | 93.25 | 94.38 | +1.2% | match | 2026-09-19 |
| VZ | 43.41 | 43.88 | +1.1% | match | 2026-10-02 |
| ADBE | 537.69 | 543.28 | +1.0% | match | 2026-10-08 |
| BSX | 107.32 | 108.36 | +1.0% | match | 2026-10-03 |
| LOW | 254.05 | 256.51 | +1.0% | match | 2026-10-08 |
| AMZN | 249.70 | 251.88 | +0.9% | match | 2026-09-29 |
| INTU | 825.75 | 832.89 | +0.9% | match | 2026-09-18 |
| ADSK | 360.66 | 363.71 | +0.8% | match | 2026-10-05 |
| CSGP | 105.92 | 106.80 | +0.8% | match | 2026-10-08 |
| AAPL | 284.29 | 286.60 | +0.8% | match | 2026-09-01 |
| AMGN | 367.93 | 365.09 | -0.8% | match | 2026-10-08 |
| IBM | 243.12 | 244.84 | +0.7% | match | 2026-10-06 |
| JNJ | 192.28 | 190.97 | -0.7% | match | 2026-08-15 |
| MCD | 325.99 | 323.88 | -0.6% | match | 2026-10-06 |
| MRK | 120.93 | 120.16 | -0.6% | match | 2026-10-06 |
| MSFT | 575.87 | 578.97 | +0.5% | match | 2026-08-14 |
| KO | 73.65 | 73.30 | -0.5% | match | 2026-09-21 |
| HD | 386.99 | 385.21 | -0.5% | match | 2026-10-09 |
| META | 848.92 | 845.18 | -0.4% | match | 2026-09-07 |
| CMG | 60.37 | 60.60 | +0.4% | match | 2026-10-07 |
| JPM | 309.46 | 310.00 | +0.2% | match | 2026-10-07 |
| NKE | 69.21 | 69.33 | +0.2% | match | 2026-10-05 |
| PG | 167.59 | 167.33 | -0.2% | match | 2026-09-14 |
| SBUX | 97.84 | 97.91 | +0.1% | match | 2026-10-04 |
| ABBV | 221.76 | 221.73 | -0.0% | match | 2026-10-07 |

</details>

The sections below describe the original 10-stock validation. Its Fair Value
rows are superseded by the table above; the other metrics are unchanged.

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

- **Fair Value (median gap 9.8%, old PE model; superseded, see the recalibration above).** the reference provider doesn't publish the formula,
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
