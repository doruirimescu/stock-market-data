# fairvalue (fvmodel)

Part of [stock-market-data](../README.md): the Fair Value valuation source
of the Investing Nexus valuation pages, next to AlphaSpread.

Fair Value stock summary dashboards built only from public data: SEC EDGAR
XBRL filings for fundamentals, Yahoo Finance for prices and dividends, and FRED
for CPI. Pages use the [Nexus design system](https://github.com/doruirimescu/nexus-design).

For each ticker the dashboard shows the metrics on a the reference provider summary page:

- Fair Value and Fair Value Score, with the five ranks and Predictability stars
- financial strength, including Piotroski F, Altman Z, Beneish M and WACC vs ROIC
- profitability
- per-share growth over 3, 5 and 10 years
- valuation ratios against their own 10-year range
- intrinsic values: DCF, Projected FCF, Median PS, Peter Lynch, Graham, EPV and NCAV
- momentum, dividends and buybacks, liquidity
- a 10-year financials table

## Quick start

```bash
mise install              # Python 3.12 + uv, creates .venv
mise run install          # installs the package and pytest
# create mise.local.toml as shown below, then:
mise run analyze AAPL MSFT KO   # writes site/index.html and site/stocks/<TICKER>.html
mise run serve            # http://localhost:8100 (FVMODEL_PORT=… to change)
```

`mise.local.toml` (git-ignored, loaded by mise automatically):

```toml
[env]
SEC_USER_AGENT = "Your Name you@example.com"
```

SEC EDGAR rejects requests that don't carry a contact email in the User-Agent.

Value a whole index (what the daily workflow runs):

```bash
mise exec -- python -m fvmodel index --index sp500       # or nasdaq100; --date, --workers
```

This writes `../generated/fairvalue/<index>_valuations.json` (latest) and
`../generated/fairvalue/<slug>/<slug>_fairvalue_<date>.json` (dated), in the
same record shape as the AlphaSpread run, plus a summary page per stock in
`../docs/fairvalue/stocks/`. The two numbers the site summarizes are:

- **valuation gap** = (Fair Value − price) / Fair Value, positive when
  undervalued (AlphaSpread's convention). In the index snapshots it is capped at
  −100% (price over twice the value) so boom-cycle stocks don't dominate the
  averages; the uncapped figure is in `valuation_score_raw` and on the stock page;
- **solvency score** (0–100) = the Financial Strength inputs (interest coverage,
  debt/revenue, Altman Z, equity/asset, cash/debt) averaged on a 0–100 scale.
  The reference provider only publishes the 1–10 rank; this is the continuous score behind it.

Other tasks:

| Task | What it does |
| --- | --- |
| `mise run compare` | Analyzes the reference stocks and compares them with the reference provider-published values, then writes `site/validation.html` and `reference/comparison.json`. |
| `mise run test` | Runs the unit tests. |

Downloads are cached in `data/` for a day.

## Documentation

| Doc | Contents |
| --- | --- |
| [docs/PLAN.md](docs/PLAN.md) | Goals, architecture, data sources, decisions, roadmap |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Every formula as implemented, and where it deviates from the reference provider |
| [docs/VALIDATION.md](docs/VALIDATION.md) | The 10-stock comparison with the reference provider and an explanation of each gap |
| [docs/methodology-research.md](docs/methodology-research.md) | Research notes on the reference provider definitions, with sources and confidence tags |

## Limits

- US SEC filers only. Banks and insurers are not handled specially.
- Fair Value and Quality Score are proprietary. Ours are labelled **Fair Value** and calibrated against published values; see VALIDATION.md.
- Not investment advice.
