# The reference provider Methodology Reference (for the EDGAR-based clone)

Research date: 2026-10-10.

## How this was researched, and confidence tags

- the reference site (www, m., sgp.) returns HTTP 403 to automated fetches. web.archive.org and archive.ph could not be fetched from this environment either. All the reference provider-specific facts below come from **search-engine snippets of the reference provider term, glossary and tutorial pages**, plus prior knowledge of those pages. Cloudflare was not bypassed.
- The session's web-search budget ran out before every item could be checked. The items tagged `[recalled]` below were not re-verified.

Every formula is tagged:

| Tag | Meaning |
|---|---|
| `[confirmed]` | Wording or worked example seen in a the reference provider page snippet this session (source given). |
| `[recalled]` | Matches how the reference provider term pages are known to present it, but not re-verified this session. Implement it, then spot-check against a live the reference provider page by hand. |
| `[uncertain]` | Not published by the reference provider, or sources conflict. The text gives a recommended implementation choice; make it configurable. |

Notation: `TTM(x)` = sum of the last 4 quarterly values. `MRQ(x)` = most recent quarter's balance-sheet value. `avg(x)` = (beginning-of-period + end-of-period) / 2. `Debt` = Total Debt as defined in §0.2.

---

## 0. Global conventions

### 0.1 TTM vs MRQ vs annual `[confirmed]`
- **Flow items** (income statement, cash flow) use TTM. The reference provider pages say: "TTM ... adds up the quarterly data reported by the company within the most recent 12 months" (EBITDA page for TTD; Earnings Yield pages).
- **Balance-sheet items** use the latest quarter (MRQ).
- **Return ratios** (ROE, ROA, ROIC, ROC) use **average** balance-sheet values (beginning and end of the period). Every term page shows two variants:
  - an **annual** figure (fiscal-year flow / average of the FY-start and FY-end balances);
  - a **quarterly** figure (quarterly flow **× 4**, "annualized", / average of the quarter-start and quarter-end balances).
  
  The headline "current" value on the summary page is normally the latest quarterly annualized value or the TTM value. Example: ROIC and ROC (Greenblatt) pages use "4 times the quarterly EBIT/Operating Income". `[confirmed]` for ROIC and ROC. Which variant the summary page shows for each ratio is `[uncertain]`; the reference provider summary pages generally show TTM / annualized-quarter.
- **Per-share values** divide by **Shares Outstanding (Diluted Average)** for flow items. Book value per share uses period-end shares outstanding. `[recalled]`
- **Growth rates** use **annual (fiscal-year) data**. See §5.
- **Market data:** price and market cap are current (daily). Historical ratio charts use the price on each date against the latest data available on that date. `[recalled]`

For EDGAR: Q4 values are not filed. Derive them as FY (10-K) minus Q1–Q3 (10-Q) for flow items. Q1–Q3 cash-flow statements are year-to-date, so difference them.

### 0.2 Total Debt `[confirmed]` (components) / `[uncertain]` (operating leases)
`Total Debt = Short-Term Debt & Capital Lease Obligation + Long-Term Debt & Capital Lease Obligation`
- "Short-Term Debt & Capital Lease Obligation ... equals Short-Term Debt plus Short-Term Capital Lease Obligation", meaning the part due within 12 months. Long-term is the part due after 12 months. (Source: The reference provider term pages, short-term-debt-and-capital-lease-obligation / long-term-debt-and-capital-lease-obligation.)
- **Operating leases (ASC 842, from 2019 on):** `[uncertain]`. No snippet confirmed whether the reference provider folds operating lease liabilities into "Capital Lease Obligation". The reference provider's data has historically come from Morningstar-style templates, which put lease liabilities in the capital-lease lines after 2019. Some the reference provider pages for retailers show debt figures that include operating leases.
  - **Recommendation:** add a config flag `include_operating_leases_in_debt`, default **true**, and validate against a lease-heavy name (e.g. SBUX, TGT, MCD) on the reference provider by hand.
- For EDGAR XBRL, map:
  - **Short-term:** `DebtCurrent`, `LongTermDebtCurrent`, `ShortTermBorrowings`, `CommercialPaper`, `FinanceLeaseLiabilityCurrent`, and optionally `OperatingLeaseLiabilityCurrent`.
  - **Long-term:** `LongTermDebtNoncurrent`, `FinanceLeaseLiabilityNoncurrent`, and optionally `OperatingLeaseLiabilityNoncurrent`.

### 0.3 EBITDA and EBIT
- `EBITDA = Pretax Income + Interest Expense + Depreciation, Depletion and Amortization` `[confirmed]` (the reference provider EBITDA term page for STC:FPT: "EBITDA = Pre-Tax Income + Interest Expense + Depreciation, Depletion and Amortization").
  - The reference provider stores Interest Expense as a **negative** number and its formula display uses `-Interest Expense`. Add back the absolute value.
- The the reference provider glossary also gives an older top-down definition: Revenue − COGS − SG&A − R&D, adding back D&A if it was already deducted. This is not what the term pages compute; use the bottom-up formula. `[confirmed]` (the reference site/glossary/EBITDA)
- `EBIT = Pretax Income + |Interest Expense|` `[recalled]`. The reference provider's EBIT is not "Operating Income": it includes non-operating items. The reference provider uses this EBIT for EV/EBIT, Earnings Yield (Greenblatt), ROC (Greenblatt) and Altman Z.
- DDA comes from the **cash-flow statement** (`DepreciationDepletionAndAmortization` / `DepreciationAmortizationAndAccretionNet`). `[recalled]`

### 0.4 Enterprise Value `[confirmed]`
`EV = Market Cap + Total Debt + Preferred Stock + Minority Interest − Cash, Cash Equivalents & Marketable Securities`

The reference provider wording: "market cap plus debt and minority interest and preferred shares, minus total cash, cash equivalents, and marketable securities." the reference provider subtracts short-term marketable securities as well as cash.

### 0.5 Free Cash Flow `[recalled]`
`FCF = Cash Flow from Operations − Capital Expenditure`

Capex is purchases of PP&E (and capitalized software and intangibles where the reference provider classifies them as capex). Acquisitions are **not** deducted. SBC is **not** deducted.

### 0.6 Tax rate `[confirmed]`
`Tax Rate = TTM Tax Expense / TTM Pretax Income`, clipped to **[0%, 100%]**: above 100% becomes 100%, below 0% becomes 0%. (the reference provider WACC and ROIC pages.)

### 0.7 "without NRI"
EPS without NRI excludes non-recurring items (the reference provider's own judgement: impairments, restructuring, gains on sales, discontinued operations, etc.). `[uncertain]` as a reproducible rule. The reference provider does not publish its NRI list.

**Recommendation:** `EPS_wo_NRI = (Net Income from continuing ops − after-tax unusual items) / diluted shares`. Unusual items come from XBRL (`GoodwillImpairmentLoss`, `AssetImpairmentCharges`, `RestructuringCharges`, `GainLossOnSaleOfPropertyPlantEquipment`, `GainLossOnInvestments`), taxed at the effective rate. Expect differences from the reference provider.

---

## 1. Fair Value

### 1.1 Published definition `[confirmed]`
Fair Value is "the reference provider' own valuation method" with three components:
1. **Historical multiples:** PE, PS, PB, and Price-to-FCF that the stock has traded at.
2. **A the reference provider adjustment factor** "based on the company's past returns and growth".
3. **Future estimates of business performance:** analyst estimates. A 2018 the reference provider article attributes these to Morningstar analysts; current pages say "estimates".

The reference provider also says the method studies "how the stock price has historically related to revenue, earnings, free cash flow and book value ... then uses the most relevant relationships".

**Sources:** reference-site/term/gf-value (snippet); a financial-news article (fetched; it confirms no formula is disclosed).

### 1.2 What is NOT published `[uncertain]`
- The weights between the 4 multiples.
- The lookback window. 10 years is commonly assumed; not confirmed.
- The functional form of the adjustment factor.
- How estimates are blended. A third-party review claims weights shift with predictability, with more history for predictable firms. Not confirmed by the reference provider.

The reference provider calls the method proprietary.

### 1.3 Recommended reproducible implementation (clone's own; label it "Fair Value", not Fair Value)
1. For each multiple M in {PE w/o NRI, PS, PB, P/FCF}, compute the stock's historical daily (or month-end) series over the last 10 years. Take a robust central value (median) `M̄`. Drop multiples where the fundamental is ≤ 0 or where fewer than about 5 years are valid.
2. Intrinsic value per multiple is `M̄ × fundamental_per_share`. Use a forward fundamental if estimates exist, otherwise TTM.
3. Blend: take the median, or an equal-weight average, of the available per-multiple values.
4. Adjustment factor: scale by `clip((1 + g_hist) / (1 + g_baseline), 0.7, 1.3)`, using 5Y revenue-per-share or EBITDA-per-share CAGR versus a market baseline. This is invented; tune it to the reference provider's charts if desired.
5. Without analyst estimates (EDGAR has none), extrapolate the forward fundamental with historical CAGR, capped (e.g. 20%).

### 1.4 Price-to-Fair Value and labels
- `Price-to-Fair Value = Price / Fair Value` `[confirmed]`.
- Valuation labels shown on the reference provider summary pages `[recalled]`:

  | Price / Fair Value | Label |
  |---|---|
  | > 1.3 | Significantly Overvalued |
  | 1.1 – 1.3 | Modestly Overvalued |
  | 0.9 – 1.1 | Fairly Valued |
  | 0.7 – 0.9 | Modestly Undervalued |
  | < 0.7 | Significantly Undervalued |

  The reference provider also shows "Possible Value Trap, Think Twice" when the ratio is very low and quality ranks are poor. The trap criteria are `[uncertain]`.

---

## 2. Quality Score and component ranks

### 2.1 Quality Score `[confirmed]` structure / `[uncertain]` weights
- Score range is 0–100. It combines 5 ranks, each on a **1–10** scale: Financial Strength, Profitability, Growth, Fair Value, Momentum.
- The reference provider says the components are weighted differently based on a 2006–2021 backtest. "Profitability Rank and Growth Rank are weighted fully, while other parameters have less weight." **Exact weights are not published.**
- Interpretation bands `[confirmed]`:

  | Quality Score | Outperformance potential |
  |---|---|
  | 91–100 | Highest |
  | 81–90 | Good |
  | 71–80 | Average |
  | 51–70 | Poor |
  | 0–50 | Worst or indeterminate |

- **Recommended implementation (clone's own; make it configurable):**
  - `Quality Score = 10 × Σ wᵢ·rankᵢ / Σ wᵢ`
  - Placeholder weights: Profitability 1.0, Growth 1.0, Financial Strength 0.6, Fair Value 0.6, Momentum 0.4. These are not the reference provider's weights.

**Sources:** reference-site/tutorial/article/28/gf-score ; reference-site/term/gf-score/GOOG ; reference-site/news/1674028/benchmark-exclusive-ranking-system-the-gf-score (all snippets).

### 2.2 Financial Strength Rank (1–10)
- **Inputs** `[confirmed]` (the reference provider "Behind the Numbers" news 1473737 and the rank-balancesheet pages):
  - **Interest Coverage**: higher is better.
  - **Debt-to-Revenue**: lower is better.
  - **Altman Z-Score**: higher is better.
  
  The the reference provider news explainer also lists **Equity-to-Asset** and **Cash-to-Debt** (higher is better).
- Interpretation `[confirmed]`: ≥ 7 means financially stable; ≤ 3 suggests potential distress.
- Mapping to 1–10 and weighting `[uncertain]`. **Recommendation:** compute each input's percentile across the universe, average them, then bucket into deciles. Alternatively, use fixed thresholds.
- `Debt-to-Revenue = Total Debt / TTM Revenue`.

### 2.3 Profitability Rank (1–10)
- **Inputs** `[confirmed]` (rank-profitability pages, news 1473737):
  1. Operating Margin (higher is better).
  2. Piotroski F-Score.
  3. **Trend** of operating margin: the 5-year trend. An uptrend ranks higher.
  4. **Consistency** of profitability: the number of profitable years in the past 10 `[recalled]`.
  5. Predictability Rank.
- Combination and weights `[uncertain]`. Use the same percentile-bucketing approach as §2.2.

### 2.4 Growth Rank (1–10)
- **Inputs** `[confirmed]`:
  - **5-Year Revenue (per share) growth rate**;
  - **5-Year EBITDA (per share) growth rate**.
  
  The reference provider chose EBITDA over EPS so that more companies can be ranked; growth must be positive. Growth is the second most return-sensitive of the five ranks.
- Combination `[uncertain]`. Also `[uncertain]` whether the reference provider's Growth Rank adds 3Y rates or growth consistency.

### 2.5 Fair Value Rank (1–10)
- Determined by Price-to-Fair Value `[confirmed]`. It is **non-monotonic**: The reference provider's backtest found both the most-expensive and the cheapest P/Fair Value groups performed worst, so the very cheapest stocks do **not** get a 10.
- Bucket cutoffs `[uncertain]`. **Recommendation:** rank 10 for P/the reference provider in about 0.7–0.9, and decline on both sides.

### 2.6 Momentum Rank (1–10) `[confirmed]`
- `Standardized momentum ratio = ((12-1 month return) + (6-1 month return)) / 2 / Beta(12M)`, plus unnamed "other momentum indicators".
- The reference provider uses traditional (not residual) momentum.
- The **~70th percentile** of the momentum ratio gets the top score of 10. The highest-momentum stocks underperform, so the mapping is non-monotonic.
- Which "other indicators" are used (RSI?) is `[uncertain]`.
- **Beta:** 12-month beta versus the S&P 500 `[uncertain]` on frequency. Use daily returns over 1 year (or weekly over 3 years for WACC beta; see §3.10).

**Source:** reference-site/term/rank-momentum/CSL (snippet).

### 2.7 Predictability Rank (stars)
- `[confirmed]`: 1 to 5 stars in half-star steps (1, 1.5, ..., 5). 1 star means "not predictable". It is based on the **consistency of Revenue per Share and EBITDA per Share over the past 10 fiscal years** (10 years covers a full business cycle). Origin: The reference provider research covering 1998–2008, in which about 76% of stocks were 1-star.
- `[recalled]`: the rank requires about 10 years of data; banks and companies with insufficient history are not ranked. Declines in EBITDA/share in the history lower the rank sharply.
- Exact scoring `[uncertain]`. **Recommended implementation:**
  1. Fit OLS of `ln(revenue/share)` and `ln(EBITDA/share)` on year, over 10 FYs.
  2. Use R² (smoothness) and slope (growth).
  3. Penalize each year-over-year decline.
  4. Map to stars, e.g.:
     - 5★: R² ≥ 0.95 on both, slope > 0, no EBITDA/share declines.
     - Step down 0.5★ per weaker band.
     - 1★: R² < 0.6, or any negative EBITDA.

**Sources:** reference-site/news/36158 ; reference-site/tutorial/article/168/what-worked-in-2008-predictability-rank (snippets).

---

## 3. Financial strength items

### 3.1 Cash-to-Debt `[recalled]`
`Cash-to-Debt = Cash, Cash Equivalents & Marketable Securities (MRQ) / Total Debt (MRQ)`

When Debt is 0, the reference provider displays "No Debt" (stored internally as a very large number, 10000).

### 3.2 Equity-to-Asset `[confirmed]` (as an FS input) / formula `[recalled]`
`Equity-to-Asset = Total Stockholders Equity (MRQ) / Total Assets (MRQ)`

The reference provider uses equity attributable to the parent, excluding minority interest.

### 3.3 Debt-to-Equity `[recalled]`
`Debt-to-Equity = Total Debt / Total Stockholders Equity` (MRQ)

N/A if equity ≤ 0 `[uncertain]`; the reference provider sometimes shows negative values.

### 3.4 Debt-to-EBITDA `[recalled]`
`Debt-to-EBITDA = Total Debt (MRQ) / EBITDA (TTM)`

Quarterly variant: EBITDA × 4. The reference provider shows N/A when EBITDA ≤ 0 `[uncertain]`.

### 3.5 Interest Coverage `[confirmed]`
`Interest Coverage = Operating Income (TTM) / |Interest Expense (TTM)|`

- The reference provider uses **Operating Income**, not EBIT.
- With no interest expense and no debt, the reference provider displays "No Debt".
- Some pages fall back to net interest income when interest expense is missing.
- Not computed for banks.

### 3.6 Piotroski F-Score (0–9) `[confirmed]` structure / period basis `[recalled]`
One point for each criterion met. "Current" is the TTM / latest data; "prior" is the same measure one year earlier. The reference provider's term page shows TTM versus TTM a year ago `[recalled]`.

| # | Criterion |
|---|---|
| 1 | Net Income > 0 |
| 2 | Cash Flow from Operations > 0 |
| 3 | ROA_t > ROA_{t-1}, with ROA = Net Income / Total Assets |
| 4 | CFO > Net Income (accruals) |
| 5 | Long-term debt / Total assets decreased versus prior year |
| 6 | Current Ratio increased |
| 7 | No new shares issued: Shares Outstanding (diluted avg) not higher than a year ago |
| 8 | Gross Margin increased |
| 9 | Asset Turnover (Revenue / Total Assets) increased |

- Interpretation `[confirmed]`: 0–3 poor, 4–6 stable, 7–9 very healthy.
- Piotroski's original paper uses beginning-of-year total assets for ROA and CFO scaling. The reference provider's denominator choice (average vs beginning) is `[uncertain]`; use the average.

**Sources:** reference-site/glossary/fscore ; reference-site/news/1473737 (snippets).

### 3.7 Altman Z-Score `[confirmed]`
The reference provider uses the **original 1968 public-manufacturer model** (not Z' or Z''):

`Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5`

| Term | Definition |
|---|---|
| X1 | Working Capital / Total Assets, where WC = Total Current Assets − Total Current Liabilities |
| X2 | Retained Earnings / Total Assets |
| X3 | EBIT (TTM) / Total Assets |
| X4 | **Market Cap** / Total Liabilities |
| X5 | Revenue (TTM) / Total Assets |

- Balance-sheet items are MRQ; market cap is current.
- **Zones:** Distress < 1.81; Grey 1.81–2.99; Safe > 2.99. Some the reference provider pages round these to 1.8 / 3.0.
- **Quirks:**
  - Not calculated when X4 or X5 = 0.
  - Not applicable to banks and insurers. The reference provider shows N/A for financials.

**Source:** reference-site/term/zscore (snippets incl. ALG page).

### 3.8 Beneish M-Score `[confirmed]`
`M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI`

`t` = current period (the reference provider: TTM `[recalled]`); `t-1` = one year earlier.

| Variable | Formula |
|---|---|
| DSRI | (AR_t / Rev_t) / (AR_{t-1} / Rev_{t-1}) |
| GMI | GM_{t-1} / GM_t, where GM = (Rev − COGS) / Rev |
| AQI | [1 − (CA_t + NetPPE_t) / TA_t] / [1 − (CA_{t-1} + NetPPE_{t-1}) / TA_{t-1}] |
| SGI | Rev_t / Rev_{t-1} |
| DEPI | [Dep_{t-1} / (Dep_{t-1} + NetPPE_{t-1})] / [Dep_t / (Dep_t + NetPPE_t)] |
| SGAI | (SGA_t / Rev_t) / (SGA_{t-1} / Rev_{t-1}) |
| LVGI | [(CL_t + LTD_t) / TA_t] / [(CL_{t-1} + LTD_{t-1}) / TA_{t-1}] |
| TATA | (Net Income from continuing ops_t − CFO_t) / TA_t `[recalled]`. The reference provider uses this cash-flow version, not Beneish's original working-capital-change version. |

- **Threshold:** M > −1.78 means "likely manipulator". This is the reference provider's current term pages (MSCI example). The older the reference provider Singapore glossary used −2.22 `[confirmed conflict]`. Use −1.78.
- **Sources:** reference-site/term/mscore ; reference-site/term/mscore/MSCI ; reference-site/glossary/mscore (snippets).

### 3.9 ROIC `[confirmed]`
`ROIC % = NOPAT / Average Invested Capital`
- `NOPAT = Operating Income × (1 − Tax Rate)`. The tax rate is clipped to [0, 100%] (§0.6). Quarterly: Operating Income × 4.
- `Invested Capital = Total Assets − Accounts Payable & Accrued Expense − Excess Cash` (AAPL ROIC page).
- `Excess Cash = Cash, Cash Equivalents & Marketable Securities − max(0, Total Current Liabilities − Total Current Assets + Cash, Cash Equivalents & Marketable Securities)` `[recalled]`. The idea: cash not needed to cover the gap between current liabilities and non-cash current assets. Floor it at 0.
- The average is (beginning + end) / 2 over the period.
- **Quirk:** older the reference provider glossary/calculator pages used `(EBIT − adjusted taxes) / (Book Debt + Book Equity − Cash)`. The current term pages use the asset-side definition above.

**Sources:** reference-site/term/roic/AAPL ; reference-site/term/roic/MSCI (snippets).

### 3.10 WACC `[confirmed]`
`WACC = E/(E+D) × Ke + D/(E+D) × Kd × (1 − Tax Rate)`

| Input | the reference provider definition |
|---|---|
| E | Market cap (market value of equity) |
| D | Book value of debt = latest one-year quarterly average of (Short-Term Debt & Capital Lease Obligation + Long-Term Debt & Capital Lease Obligation), i.e. the average of the last 5 (or 4) quarter-ends `[uncertain which]` |
| Ke | CAPM: `Rf + β × 6%`. **Market premium is fixed at 6%.** |
| Rf | **10-Year Treasury Constant Maturity Rate** (FRED `DGS10`), updated daily |
| β | Stock beta. **If price history < 3 years, β = 1.** Frequency/window `[uncertain]`; likely 3 years of returns vs the S&P 500 (use weekly returns over 3 years, or monthly over 5 years). |
| Kd | `TTM |Interest Expense| / D` (the one-year average debt above) |
| Tax Rate | TTM tax expense / TTM pretax income, clipped to [0%, 100%] |

Worked example (FICO page): Rf 5.165%, β 1.5902, so Ke = 5.165 + 1.5902 × 6 = 14.71%.

**Sources:** reference-site/term/wacc ; reference-site/term/wacc/FICO ; the reference site/term/wacc/* (snippets).

---

## 4. Profitability

| Metric | Formula | Tag |
|---|---|---|
| Operating Margin % | Operating Income / Revenue (TTM) | `[confirmed]` (GES example: 145.652 / 891.05 = 16.35%) |
| Net Margin % | Net Income / Revenue (TTM). The reference provider uses Net Income attributable to common. | `[recalled]` |
| FCF Margin % | Free Cash Flow / Revenue (TTM) | `[recalled]` |
| Gross Margin % | Gross Profit / Revenue | `[recalled]` |
| ROE % | Net Income / avg(Total Stockholders Equity). Quarterly: NI × 4. | `[recalled]` |
| ROA % | Net Income / avg(Total Assets). Quarterly: NI × 4. | `[recalled]` |
| ROC (Joel Greenblatt) % | EBIT / avg(Net PPE + Net Working Capital) | `[confirmed]` |
| ROCE % | EBIT / avg(Capital Employed), with Capital Employed = Total Assets − Total Current Liabilities | `[recalled]`; the reference provider's EBIT-vs-Operating-Income choice here is `[uncertain]` |
| Years profitable over past 10Y | Count of the last 10 fiscal years with Net Income > 0 (shown as e.g. "10/10") | `[recalled]` |

### ROC (Greenblatt) quirks `[confirmed]`
- Net Working Capital is operating only:
  - Assets side: Accounts Receivable + Inventories + Other Current Assets.
  - Minus: Accounts Payable & Accrued Expense + Deferred Revenue (current) + Other Current Liabilities.
  - **Excludes** cash and marketable securities, and **excludes** interest-bearing short-term debt.
- If NWC < 0, use 0.
- Quarterly variant: EBIT × 4.

**Source:** reference-site/term/roc-joel/GWW (snippet).

---

## 5. Growth rates

### 5.1 Method `[confirmed]`
The reference provider growth rates are **per share**:
- Revenue per Share
- EBITDA per Share
- EPS without NRI
- FCF per Share
- Book Value per Share
- Dividends per Share

The reference provider on the 3-year revenue rate: "This is the 3-year average growth rate of Revenue per Share. The growth rate is calculated using **exponential compounding based on the latest four year annual data**." This is a point-to-point CAGR on fiscal-year values:

```
growth_N = (X_FY0 / X_FY-N) ^ (1/N) − 1     # N = 3, 5, 10; uses N+1 annual points
```

- **Not** a regression. Use the latest fiscal year as FY0, not TTM. The reference provider also shows separate "TTM / YoY" growth figures.
- **Quirks:**
  - If the start or end value is ≤ 0, the rate is N/A `[recalled]`.
  - Values display with 1 decimal place.
  - Per-share uses diluted average shares for flow items and period-end shares for book value.

**Source:** reference-site/term/rvn-growth-3y/GOOG (snippet).

### 5.2 Uses elsewhere
- PEG and Peter Lynch Fair Value use the **5-Year EBITDA-per-share growth rate**.
- The Earnings DCF uses the 10Y EPS-without-NRI growth rate.

---

## 6. Momentum / technicals

### 6.1 6-1 and 12-1 Month Momentum `[confirmed]`
```
6-1 Month Momentum %  = (Price_1m_ago / Price_6m_ago  − 1) × 100
12-1 Month Momentum % = (Price_1m_ago / Price_12m_ago − 1) × 100
```
These skip the most recent month. Use calendar-month offsets on daily closes; use adjusted closes for splits. Whether the reference provider includes dividends is `[uncertain]`.

### 6.2 RSI 5 / 9 / 14 `[uncertain]` (the reference provider variant not documented)
Standard Wilder RSI over N daily closes:
```
gain_t = max(C_t − C_{t-1}, 0);  loss_t = max(C_{t-1} − C_t, 0)
AvgGain_N = Wilder smoothing (first value = SMA over N, then (prev × (N−1) + gain_t) / N); same for AvgLoss
RS = AvgGain / AvgLoss;  RSI = 100 − 100 / (1 + RS)
```
Use Wilder smoothing; it is the convention most data vendors follow.

---

## 7. Valuation

### 7.1 Multiples

| Metric | Formula (the reference provider) | Tag / quirk |
|---|---|---|
| PE (TTM) | Price / EPS Diluted (TTM) | `[recalled]`; EPS ≤ 0 shows "At Loss" (N/A) |
| PE without NRI | Price / EPS without NRI (TTM) | `[recalled]`; see §0.7 |
| Shiller PE | Price / E10 | `[confirmed]` concept. **E10** = average of inflation-adjusted EPS over the past 10 years; each period's diluted EPS is scaled by `CPI_latest / CPI_period` (US CPI). The reference provider appears to adjust **quarterly** EPS (40 quarters, sum / 10) `[uncertain]`; the annual variant is acceptable. N/A without 10 years of history. |
| PEG | PE without NRI / (5-Year EBITDA-per-share growth rate as a whole number, e.g. 8.6) | `[confirmed]`; N/A if growth ≤ 0 (GNP example: 9.50 / 8.60 = 1.10). **Deviation from textbook:** uses EBITDA/share growth, not EPS growth. |
| PS | Market Cap / Revenue (TTM), equivalently Price / Revenue per Share (TTM) | `[recalled]` |
| PB | Price / Book Value per Share (MRQ) | `[recalled]` |
| Price-to-Tangible-Book | Price / Tangible Book per Share; Tangible Book = Total Stockholders Equity − Intangible Assets (goodwill + other intangibles) | `[recalled]`; whether preferred stock is also deducted is `[uncertain]` |
| Price-to-FCF | Market Cap / FCF (TTM) | `[recalled]`; N/A if FCF ≤ 0 |
| Price-to-Operating-CF | Market Cap / CFO (TTM) | `[recalled]` |
| EV-to-EBIT | EV / EBIT (TTM) | `[recalled]`; EBIT per §0.3 |
| EV-to-EBITDA | EV / EBITDA (TTM) | `[recalled]` |
| EV-to-Revenue | EV / Revenue (TTM) | `[recalled]` |
| EV-to-FCF | EV / FCF (TTM) | `[recalled]` |
| Earnings Yield (Greenblatt) % | EBIT (TTM) / EV | `[confirmed]`; uses EV, not market cap |
| FCF Yield % | FCF (TTM) / Market Cap | `[recalled]` |

### 7.2 Forward Rate of Return (Yacktman) `[confirmed]` concept / details `[uncertain]`
`Forward Rate of Return = Normalized FCF yield + real growth + inflation`

The reference provider uses "the normalized Free Cash Flow of the past seven years" and adds growth.

**Recommended implementation:**
```
Normalized FCF/share = mean(FCF per share over last 7 FYs)
FRR % = Normalized FCF/share / Price + g
```
- `g` = 5Y or 10Y FCF-per-share (or revenue-per-share) CAGR, clipped to [0%, 20%].
- The reference provider's exact growth series and caps were not confirmed.

### 7.3 Graham Number `[confirmed]`
`Graham Number = sqrt(22.5 × Tangible Book Value per Share (MRQ) × EPS without NRI (TTM))`

- **Deviation from textbook:** uses **tangible** BVPS and EPS **without NRI**; the textbook uses BVPS and EPS.
- N/A if either input ≤ 0.
- Example (GES): sqrt(22.5 × 12.278 × 3.14) = 29.45.

**Source:** reference-site/term/graham-number/GES

### 7.4 Peter Lynch Fair Value `[confirmed]`
`Peter Lynch Fair Value = PEG(=1) × 5-Year EBITDA-per-share growth rate (whole number) × EPS without NRI (TTM)`

- Growth > 25% is capped at 25.
- Growth < 5% means the value is **not calculated**.
- Banks use 5Y Book-Value-per-share growth instead of EBITDA.
- Example (PDEX): 6.6 × 1.264 = 8.34.
- Separate from the "Peter Lynch Chart", which uses a fixed PE of 15.

**Source:** reference-site/term/peter-lynch-fair-value/PDEX

### 7.5 Median PS Value `[confirmed]`
`Median PS Value = Revenue per Share (TTM) × 10-Year Median PS Ratio`

Example (GES): 41.161 × 0.603 = 24.82. Price-to-Median-PS-Value = Price / Median PS Value.

**Source:** reference-site/term/medpsvalue/GES

### 7.6 Intrinsic Value: Projected FCF `[confirmed]` structure / constants `[uncertain]`
`IV_ProjFCF = (Growth Multiple × FCF (average of last 6 FYs) + 0.8 × Total Stockholders Equity (MRQ)) / Diluted Shares`

- Smooths FCF over the past 6–7 years.
- Growth Multiple is capped to **[8.35, 17.74]**. It derives from a DCF on the historical growth rate; the exact mapping from growth to multiple is not published `[uncertain]`.
- The reference provider snippets conflict on the equity term: `+ 0.8 × Equity` versus `+ Equity / 0.8`. The narrative ("80% was chosen as a happy median") supports **0.8 × Equity**.
- `Price-to-Projected-FCF = Price / IV_ProjFCF`. Example (LE): 13.01 / 17.44 = 0.75.

**Source:** the reference site/term/iv_dcf_share/* (snippets).

### 7.7 DCF (Earnings Based) `[confirmed]` parameters / closed form `[recalled]`
Two-stage model; **both stages are finite (10 + 10 years)**. There is no perpetuity. This deviates from the textbook Gordon terminal value.

| Parameter | the reference provider value |
|---|---|
| E | EPS without NRI (TTM) by default. The FCF-based DCF uses FCF per share. |
| Growth stage | 10 years at `g` = average 10-year EPS-without-NRI (per share) growth rate. |
| Growth cap | `g` capped at **20%**. One the reference provider FAQ also floors it at **5%**; the glossary says only "or 20%, whichever is less" `[uncertain]`. Use: cap 20%; floor 5% when history is positive. |
| Terminal stage | 10 years at `t` = **4%** (must be < d). |
| Discount rate `d` | Current the reference provider practice: 10Y Treasury yield **rounded up to a whole %** + **6%** (e.g. 4.31% → 5% + 6% = 11%). Legacy default: 12%. |

Closed form, with `x = (1+g)/(1+d)` and `y = (1+t)/(1+d)`:
```
Growth Value   = E × x × (1 − x^10) / (1 − x)
Terminal Value = E × x^10 × y × (1 − y^10) / (1 − y)
IV = Growth Value + Terminal Value  (+ Tangible Book Value per Share, an optional the reference provider calculator toggle) [uncertain]
Margin of Safety = (IV − Price) / IV
```

**Sources:** reference-site/glossary/Intrinsic_Value_DE ; reference-site/news/2715667 (snippets).

### 7.8 Net Current Asset Value (NCAV) `[recalled]`
`NCAV per share = (Total Current Assets − Total Liabilities − Preferred Stock − Minority Interest) / Shares Outstanding`

The reference provider's NCAV URLs (term/NCAV/...) actually display **Net-Net Working Capital**, so the two labels are partly conflated on the reference provider `[confirmed conflict]`.

### 7.9 Net-Net Working Capital `[confirmed]`
`NNWC = Cash & Short-Term Investments + 0.75 × Accounts Receivable + 0.5 × Inventory − Total Liabilities − Preferred Stock − Minority Interest`

Divide by shares outstanding for the per-share value. The reference provider's Graham screener flags Price < ⅔ × NNWC.

**Source:** reference-site/glossary/NCAV ; reference-site/term/net-net-working-capital/HLF

### 7.10 Earnings Power Value (Greenwald) `[confirmed]` steps / constants partly `[recalled]`
1. **Normalized EBIT** = Average operating margin (5 years) × Sustainable Revenue (TTM / latest) + Adjusted SG&A, where Adjusted SG&A = **25%** × SG&A (the reference provider's default within a 15–50% judgement range).
2. **NOPAT** = Normalized EBIT × (1 − average tax rate over 5 years).
3. **Excess depreciation** = Average DDA × % excess depreciation × ½ × average tax rate. Add it back to get Normalized Earnings. The exact % is `[uncertain]`.
4. **Maintenance Capex** (Greenwald):
   - If revenue fell year over year, Maintenance Capex = Capex.
   - Otherwise, Maintenance Capex = Capex − Growth Capex, where Growth Capex = (Net PPE / Revenue ratio) × ΔRevenue.
   - Average over 5 years (the reference provider tables show "average over last 20 quarters").
5. **Earnings Power** = Normalized Earnings − Average Maintenance Capex.
6. **EPV per share** = (Earnings Power / WACC + Cash & equivalents − Total Debt) / Diluted Shares.
   - Worked examples use the stock's WACC; some show a 9% floor `[uncertain]`.
   - The reference provider does not store EPV when average Maintenance Capex = 0.

**Sources:** reference-site/term/epv/OVV ; reference-site/term/EPV/EVI (snippets).

---

## 8. Dividends and buybacks

| Metric | Formula | Tag |
|---|---|---|
| Dividend Yield % | Dividends per Share (TTM, declared/paid) / Price | `[recalled]` |
| Dividend Payout Ratio | Dividends per Share (TTM) / EPS Diluted (TTM). Whether the reference provider uses EPS without NRI is `[uncertain]`. | `[recalled]` |
| 3-Year Dividend Growth Rate | Per-share CAGR on 4 annual DPS points (§5.1) | `[recalled]` via the §5.1 method |
| 5-Year Yield-on-Cost % | Dividend Yield × (1 + 5-Year Dividend Growth Rate)^5 | `[confirmed]` (reference-site/glossary/yield_on_cost) |
| Buyback Yield % | −(Repurchase of Stock + Issuance of Stock) / Market Cap = net repurchases (TTM; quarterly × 4) / Market Cap | `[confirmed]` (reference-site/term/buyback-yield/RS) |
| 3-Year Share Buyback Ratio % | Average annual reduction in shares outstanding: `1 − (Shares_FY0 / Shares_FY-3)^(1/3)`. Positive means net buybacks. | `[recalled]` / `[uncertain]` on the exact share series |
| Shareholder Yield % | Dividend Yield + Buyback Yield + Net Debt Paydown Yield = (Dividends paid + Net repurchases + Net debt repayment, all TTM) / Market Cap | `[uncertain]` (the reference provider definition not retrieved; this is Meb Faber's definition, which the reference provider is believed to follow) |

---

## 9. Liquidity

| Metric | Formula | Tag |
|---|---|---|
| Current Ratio | Total Current Assets / Total Current Liabilities (MRQ) | `[recalled]` |
| Quick Ratio | (Total Current Assets − Total Inventories) / Total Current Liabilities | `[recalled]`; the reference provider does not also subtract prepaids `[uncertain]` |
| Cash Ratio | Cash, Cash Equivalents & Marketable Securities / Total Current Liabilities | `[recalled]` |
| Days Sales Outstanding | Accounts Receivable / Revenue × Days in period (annual 365; quarterly 365/4) | `[recalled]`; end-of-period vs average AR is `[uncertain]` |
| Days Inventory | Total Inventories / COGS × Days in period | `[recalled]`; average vs end inventory is `[uncertain]` |
| Days Payable | Accounts Payable / COGS × Days in period | `[recalled]` |
| Cash Conversion Cycle | DSO + Days Inventory − Days Payable | `[confirmed]` (via the stockR wrapper of the reference provider data: https://rdrr.io/github/OliverHennhoefer/stockR/man/get_cash_conv_cycle.html) |

For TTM ratios, use TTM revenue/COGS with 365 days. For quarterly values, use quarterly flows with 91.25 days.

---

## 10. Summary of what is uncertain (implementation must make these configurable)

1. **Fair Value:** multiple weights, lookback, adjustment-factor formula and estimate blending are proprietary.
2. **Quality Score:** component weights are unpublished (only "Profitability and Growth weighted fully").
3. **Rank mappings:** how each rank's inputs map to 1–10, for all five ranks and the Predictability stars.
4. **Operating leases:** whether they are inside Total Debt.
5. **NRI:** which items count as non-recurring.
6. **WACC beta:** frequency and window.
7. **Projected FCF:** growth-multiple mapping (cap 8.35–17.74), and the 0.8 placement.
8. **Earnings DCF:** the 5% growth floor, and the tangible-book add-on.
9. **Shiller E10:** quarterly vs annual CPI adjustment.
10. **Forward Rate of Return:** growth series and caps.
11. **Shareholder Yield, Buyback Ratio:** exact definitions.
12. **Days metrics:** average vs end-of-period balances.

## 11. Source list (the reference provider pages seen via search snippets; direct fetch returned 403)
- reference-site/term/gf-value ; a financial-news article (fetched)
- reference-site/tutorial/article/28/gf-score ; reference-site/term/gf-score/GOOG ; reference-site/news/1674028/benchmark-exclusive-ranking-system-the-gf-score
- reference-site/news/1473737/behind-the-numbers-benchmark-financial-strength-and-profitability
- reference-site/term/rank-profitability/GES ; reference-site/term/rank-growth/GES ; reference-site/term/rank-momentum/CSL ; reference-site/term/rank-gf-value/GES
- reference-site/news/36158 ; reference-site/tutorial/article/168/what-worked-in-2008-predictability-rank
- reference-site/term/zscore ; reference-site/term/mscore ; reference-site/glossary/fscore
- reference-site/term/roic/AAPL ; reference-site/term/wacc ; reference-site/term/wacc/FICO
- reference-site/term/roc-joel/GWW ; reference-site/term/earning-yield-greenblatt/PEG
- reference-site/term/EBITDA/STC:FPT ; reference-site/glossary/EBITDA ; reference-site/term/enterprise-value/^GC
- reference-site/term/short-term-debt-and-capital-lease-obligation/CSCO ; reference-site/term/long-term-debt-and-capital-lease-obligation/SHOP
- reference-site/term/rvn-growth-3y/GOOG
- reference-site/term/pchange-6-1m/VRSK ; reference-site/term/pchange_12_1m/MCO
- reference-site/term/peg-ratio/GES ; reference-site/term/peter-lynch-fair-value/PDEX ; reference-site/term/medpsvalue/GES ; reference-site/term/graham-number/GES
- reference-site/term/e10/NOTE ; reference-site/term/iv_dcf_share/LE ; reference-site/glossary/Intrinsic_Value_DE ; reference-site/news/2715667
- reference-site/glossary/NCAV ; reference-site/term/net-net-working-capital/HLF
- reference-site/term/epv/OVV ; reference-site/term/EPV/EVI
- reference-site/glossary/yield_on_cost ; reference-site/term/buyback-yield/RS
- reference-site/term/rate-of-return-value/BMY
- https://rdrr.io/github/OliverHennhoefer/stockR/man/get_cash_conv_cycle.html ; https://rdrr.io/github/OliverHennhoefer/stockR/man/get_cash_to_debt.html
