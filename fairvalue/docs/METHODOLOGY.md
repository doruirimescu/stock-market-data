# Methodology

How each metric is computed. Each one follows the reference provider's published definition
where one exists. The sources and confidence of those definitions are in
[methodology-research.md](methodology-research.md). Tunable assumptions are in
[`fvmodel/config.py`](../fvmodel/config.py).

## Conventions

- **Flows** (income statement, cash flow) are TTM. **Balances** are the latest
  quarter (MRQ).
- **Return ratios** divide by the average of the current balance and the
  balance one year earlier.
  - ROE, ROA and ROIC also come in an annualized-quarter variant (quarter × 4
    over the average of the quarter-start and quarter-end balances). That is
    the headline figure on the reference provider term pages.
- **Growth** is a per-share CAGR on fiscal-year values: `(X_FY0 / X_FY-N)^(1/N) − 1`.
  - It is N/A if either endpoint is ≤ 0.
  - Flow items use diluted weighted shares; book value uses period-end shares.
- **Percentages** are plain numbers (35.2 means 35.2%).
- **Debt** = current debt (`DebtCurrent`, or the sum of the current portion of
  long-term debt, short-term borrowings and commercial paper) + long-term debt
  + operating-lease liabilities (`INCLUDE_OPERATING_LEASES_IN_DEBT`).
- **Cash** = cash and equivalents + short-term investments or marketable securities.
- **EBIT** = pretax income + interest expense, and **EBITDA** = EBIT + D&A, as
  The reference provider defines them.
- **Operating income** is `OperatingIncomeLoss`. If that tag is absent (XOM,
  JNJ), pretax income + interest expense is used instead.
- **FCF** = operating cash flow − capital expenditure.
- **EV** = market cap + debt − cash. Market cap = price × cover-page shares outstanding.
- **Tax rate** = tax / pretax, clipped to [0, 1].

## Financial strength

| Metric | Formula |
| --- | --- |
| Cash-to-Debt | cash / debt ("No debt" if debt = 0) |
| Equity-to-Asset | equity / total assets |
| Debt-to-Equity | debt / equity (N/A if equity ≤ 0) |
| Debt-to-EBITDA | debt / EBITDA TTM |
| Interest Coverage | operating income / interest expense |
| Piotroski F | 9 binary tests, TTM vs TTM a year earlier: NI > 0, CFO > 0, ROA up, CFO > NI, long-term debt/assets down, current ratio up, diluted shares not up, gross margin up, asset turnover up |
| Altman Z | original 1968 model: 1.2·WC/TA + 1.4·RE/TA + 3.3·EBIT/TA + 0.6·MktCap/TL + 1.0·Rev/TA. Safe > 2.99, distress < 1.81 |
| Beneish M | 8-variable model, TTM vs prior TTM. TATA = (NI − CFO)/TA. Likely manipulator above −1.78. A ratio that cannot be computed defaults to 1 |
| ROIC | Operating income × (1 − tax) / avg invested capital. Invested capital = total assets − (accounts payable + accrued liabilities) − excess cash, where excess cash = cash − max(0, CL − CA + cash) |
| WACC | E/(D+E)·(Rf + β·6%) + D/(D+E)·Kd·(1 − t). Rf = 10Y Treasury on the as-of date. β = 3-year weekly vs the S&P 500 (1 if under 3 years of history). Kd = interest / average debt |

## Profitability

Gross, operating, net and FCF margins are each divided by TTM revenue.

| Metric | Formula |
| --- | --- |
| ROE | NI / avg equity |
| ROA | NI / avg assets |
| ROC (Greenblatt) | EBIT / avg(net PP&E + max(0, AR + inventory − AP)) |
| ROCE | EBIT / avg(total assets − current liabilities) |
| Years profitable | fiscal years with NI > 0, out of the last 10 |
| Operating-margin trend | slope (percentage points per year) of the last 5 fiscal-year operating margins |

## Valuation

| Metric | Formula |
| --- | --- |
| PE, PS, PB, P/FCF, P/OCF, P/Tangible book | price over the per-share TTM (or MRQ) fundamental |
| EV/EBIT, EV/EBITDA, EV/Revenue, EV/FCF | EV over the TTM item |
| Earnings yield (Greenblatt) | EBIT / EV |
| FCF yield | FCF / market cap |
| PEG | PE / 5-year EBITDA-per-share growth (the reference provider uses EBITDA, not EPS) |
| Shiller PE | price / mean of the last 10 fiscal-year EPS, each CPI-adjusted to today |
| 10-year range | daily multiple = close / per-share TTM fundamental as of the latest quarter end; min / median / max and the current percentile |

### Intrinsic values

| Model | Formula |
| --- | --- |
| **Fair Value** | 10-year median PE × TTM EPS (P/B × book for financials), when the PE history is ≥ 90% valid and the result is within 2× of the median of the other multiples' values (P/S, P/B, P/FCF). Otherwise the median of all available multiple-based values (each needs ≥ 3 years of history). Calibration is in VALIDATION.md. Price/Fair Value bands: > 1.3 significantly overvalued, 1.1–1.3 modestly overvalued, 0.9–1.1 fair, 0.7–0.9 modestly undervalued, < 0.7 significantly undervalued |
| **Valuation gap** | (Fair Value − price) / Fair Value × 100; positive = undervalued. Same convention as AlphaSpread, so the two sources can be averaged |
| **Solvency score** | 0–100: the five Financial Strength inputs mapped to 0–10 (same breakpoints as the rank) and averaged × 10, unrounded |
| DCF (earnings) | EPS × [10 years at g + 10 years at 4%], both finite, discounted at d. g = 10-year EPS growth clipped to [5%, 20%]. d = 10Y Treasury rounded up to a whole % + 6% |
| Projected FCF | (m × mean FCF of the last 6 FYs + 0.8 × equity) / diluted shares. m = the zero-to-5Y-growth DCF multiple, clipped to [8.35, 17.74]. The 8.35 lower bound equals the zero-growth multiple at 11%, which is checked in the tests |
| Median PS value | 10-year median PS × TTM revenue per share |
| Peter Lynch fair value | min(5-year EBITDA/share growth, 25) × EPS. N/A when growth < 5% |
| Graham Number | √(22.5 × tangible BVPS × EPS) |
| EPV (Greenwald) | [5-year average operating margin × TTM revenue × (1 − average tax) + average D&A − average maintenance capex] / WACC + cash − debt, per share. Maintenance capex = capex − (PP&E/revenue) × revenue growth. The 25% SG&A add-back and excess-depreciation steps are omitted |
| NCAV / NNWC | (CA − TL) / shares; (cash + 0.75·AR + 0.5·inventory − TL) / shares |
| Forward rate of return (Yacktman) | mean FCF/share of the last 7 FYs / price + 5-year revenue/share growth clipped to [0, 20] |

## Momentum, dividends, liquidity

- **RSI 5/9/14:** Wilder smoothing.
- **Momentum:**
  - 6-1 month = price 1 month ago / price 6 months ago − 1.
  - 12-1 month = price 1 month ago / price 12 months ago − 1.
- **Dividends:**
  - Dividend yield = dividends with ex-date in the last 365 days / price.
  - Payout = DPS / EPS.
  - Yield on cost (5Y) = yield × (1 + 5-year DPS growth)^5.
- **Buybacks:**
  - Buyback yield = (buybacks − issuance) TTM / market cap.
  - 3-year buyback ratio = 1 − (shares_FY0 / shares_FY-3)^(1/3).
  - Shareholder yield = (dividends + net buybacks + net debt repayment) / market cap.
- **Liquidity:**
  - Current, quick and cash ratios.
  - DSO = AR / revenue × 365. DIO and DPO use COGS.
  - Cash conversion cycle = DSO + DIO − DPO.

## Ranks and Fair Value Score

Each rank uses the inputs the reference provider documents. Each input is mapped to 0–10
with fixed piecewise-linear breakpoints (`scoring.py`), averaged, and rounded to 1–10.

| Rank | Inputs |
| --- | --- |
| Financial strength | interest coverage, debt/revenue, Altman Z, equity/asset, cash/debt |
| Profitability | operating margin, Piotroski F, 5-year margin trend, years profitable, Predictability |
| Growth | 5-year revenue/share, 5-year EBITDA/share, 10-year revenue/share growth |
| Fair Value | price / Fair Value. Non-monotonic: 0.7–0.9 scores 10, and very cheap stocks score lower |
| Momentum | ((12-1) + (6-1)) / 2 / β. The peak score sits below the highest momentum |

- **Predictability (1–5 stars)** is based on 10 fiscal years of revenue/share
  and EBITDA/share. It starts at 5 and loses half a star for each EBITDA
  decline, for revenue declines after the first, for a poor log-linear fit
  (R²), and a full star for a negative trend. Negative values give 1 star.
- **Fair Value Score** = `a + b × weighted average of ranks × 10`.
  - Weights: profitability 1, growth 1, financial strength 0.6, Fair Value 0.6, momentum 0.4.
  - (a, b) = (26.16, 0.815), fitted to 10 published Quality Scores (see VALIDATION.md).

## Financial companies

Companies with an EDGAR SIC code of 6000–6799 (banks, insurers, REITs) are
flagged as financial:

- **Not applicable:** Altman Z, Beneish M, liquidity and working-capital ratios,
  NCAV/NNWC, gross margin, ROC (Greenblatt), ROCE, interest coverage and EPV
  show "N/A (financial)", as on the reference provider.
- **Debt:** unclassified balance sheets fall back to `LongTermDebt`,
  `DebtLongtermAndShorttermCombinedAmount`, or secured + unsecured debt + notes payable.
- **Fair Value:** uses the 10-year median **P/B** × book value per share
  (`FAIR_VALUE_WEIGHTS_FINANCIAL`), because earnings swing with credit and
  mark-to-market. Not validated against the reference provider.
- **Peter Lynch fair value:** uses 5-year book-value growth, as the reference provider does for banks.

## Data hygiene

- **Dropped tags:** a flow tag missing from the latest 10-Q falls back to the
  TTM one quarter earlier, and the page says so. Example: RITM stopped tagging
  total `Revenues` in its June 2026 10-Q.
- **Share-count outliers:** a quarterly share count more than 5× away from the
  median of its neighbours is treated as a filer scaling error and rescaled.
  Example: RITM's Q1 2020 10-Q tagged 415.6 billion diluted shares instead of 415.6 million.

## Known deviations from the reference provider

- **No analyst estimates.** the reference provider's Fair Value blends in forward estimates; ours is purely historical.
- **No industry or universe percentiles.** Ranks use fixed breakpoints.
- **No "without NRI" adjustment.** EPS is GAAP diluted EPS.
- **Only standard XBRL tags.**
  - Company-specific items are invisible, e.g. AAPL and CAT interest expense, so
    their interest coverage is N/A.
  - JNJ's operating income falls back to pretax + interest.
- **KO lags a quarter.** EDGAR companyfacts held no newer KO quarter than April 2026 at build time.
