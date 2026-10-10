# Plan and architecture

## Goal

Given a ticker, reproduce the metrics on a the reference provider stock summary page from
public data only, render them as a dashboard in the Nexus style, and measure how
close the numbers are to the reference provider's.

## Data sources

| Need | Source | Notes |
| --- | --- | --- |
| Financial statements | SEC EDGAR `companyfacts` (XBRL) | Free, 15+ years. Needs `SEC_USER_AGENT` with an email. Only standard `us-gaap`/`dei` tags; company-specific extension tags are not included. |
| Ticker → CIK | `sec.gov/files/company_tickers.json` | Predecessor registrants are merged in via `sec.PREDECESSOR_CIKS` (XOM moved to a new holding-company CIK in 2026). |
| Prices, dividends, splits | Yahoo Finance via `yfinance` | Split-adjusted daily closes. Not total-return. |
| Benchmark, risk-free rate | `^GSPC`, `^TNX` via `yfinance` | Used for beta and the cost of equity. |
| CPI | FRED `CPIAUCSL` | Used for the Shiller PE. |

The reference provider itself (all hosts) returns HTTP 403 behind a Cloudflare challenge.
It is never scraped. The validation reference values were collected from dated
The reference provider page titles and articles in web-search results (see VALIDATION.md).

## Architecture

```
sec.py          download + cache companyfacts; predecessor CIKs
xbrl.py         FactBook: dedupe facts (latest filing wins), split-adjust,
                point-in-time filter (filed_by), annual / TTM / quarter / instant
fundamentals.py line items as prioritized XBRL tag alternatives (+ Sum/Diff),
                derived items (EBIT, EBITDA, FCF, total debt...), stale fallback
market.py       prices, dividends, splits, ^GSPC, ^TNX, CPI; truncation to a date
metrics/
  history.py    quarterly TTM per-share history -> daily multiple series
  compute.py    all summary-page metrics -> Report
  scoring.py    1-10 ranks, Predictability stars, Quality Score
  base.py       Metric record, helpers
config.py       every assumption the reference provider doesn't publish
compare.py      point-in-time comparison against reference/benchmark_reference.json
render.py       Jinja2 -> site/ (index, stocks/<T>.html, validation.html)
templates/      Nexus-style pages (linked live stylesheet + nexus.js for Plotly)
```

### Key design decisions

1. **TTM from year-to-date facts.** 10-Qs report year-to-date cash flows and
   10-Ks have no Q4. TTM = prior fiscal year + current YTD − prior-year YTD.
   Q4 values are derived as FY − 9M.
2. **Latest filing wins.** Each period is reported several times; the latest
   filing carries any restatement.
3. **Split adjustment by filing date.** Per-share and share-count facts filed
   before a split are converted to today's share basis. Old periods are never
   re-filed after a split, so without this, 10-year per-share growth is wrong
   (AAPL showed −3.7% instead of +10.6%).
4. **Tag fallbacks per period.** Companies change tags over time (AAPL revenue
   moved from `SalesRevenueNet` to `RevenueFromContract…`). Each line item tries
   its alternatives in order for every period.
5. **Stale balance-sheet fallback.** Some items appear only in the 10-K, e.g.
   lease liabilities, and CAT's debt, which is tagged quarterly only with segment
   dimensions. These use the last 10-K value, and the page says so.
6. **Point-in-time analysis.** `analyze(ticker, as_of=D)` uses only filings made
   and prices known by D. This makes validation fair and makes backtests
   possible.
7. **Assumptions in config.** the reference provider does not publish its Fair Value weights,
   Quality Score weights or rank breakpoints. Every such choice lives in `config.py`
   or `scoring.py`, with the calibration evidence in comments.
8. **Design system linked, not copied.** Pages link the live `nexus.css` and
   `nexus.js`, so style changes reach the dashboards without a rebuild.

## Status

Done:

- Data layer.
- All summary-page metric groups.
- Fair Value and Fair Value Score.
- Static dashboard, index and validation pages.
- Point-in-time comparison against 69 the reference provider values for 10 stocks.
- 12 unit tests.

## Roadmap

1. **More reference data.** Coverage is about 7 values per stock, limited by the
   search budget. The the reference provider API (paid) or values exported from a logged-in
   browser would allow checking every metric. `reference/benchmark_reference.json`
   is the input format.
2. **Industry ranking.** the reference provider ranks each metric against its industry. That
   needs a universe: run `analyze` over the S&P 500 and add industry
   percentiles, using SIC codes from EDGAR `submissions`.
3. **Universe-based ranks.** Replace the fixed rank breakpoints with
   percentiles over that universe, which is how the reference provider does it, then refit
   `QUALITY_SCORE_LINEAR`.
4. **EPS without NRI.** Strip impairments, restructuring and disposal gains
   (XBRL tags exist) for PE without NRI, the Graham Number and the DCF.
5. **Financial companies.** Partly done: financials are detected by SIC code,
   non-applicable metrics are hidden, and Fair Value is book-based. Still
   missing: bank line items (net interest income, provisions) and validation of
   the book-based value against the reference provider.
6. **Multi-class shares** (e.g. GOOGL). The cover-page share count must be
   summed across classes.
7. **Hosting.** Publish `site/` to GitHub Pages on a daily schedule.
