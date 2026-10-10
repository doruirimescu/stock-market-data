# stock-market-data

Data, reports and writing split out of
[python-trading](https://github.com/doruirimescu/python-trading). Most of the
producing code still lives there. Three self-contained parts live here: the
**AlphaSpread valuation generator** ([`scripts/`](scripts/)), the
**Fair Value valuation model** ([`fairvalue/`](fairvalue/)), and the
**calculator backend** ([`server/`](server/)), which serves the stock calculators
and loan tools.

## Layout

| Path         | Contents |
| ------------ | -------- |
| `scripts/`   | The AlphaSpread data-generation scripts — scrape index valuations and render the dated `nasdaq/` and `sp500/` charts. See [`scripts/README.md`](scripts/README.md). Also `nexus.sh`, the local launcher, and `publish_site_data.py`. |
| `fairvalue/` | Fair Value valuation model (`fvmodel`): Fair Value, Quality Score, solvency and the full Fair Value summary metrics from SEC EDGAR filings and Yahoo prices. See [`fairvalue/README.md`](fairvalue/README.md). |
| `server/`    | FastAPI backend for the calculators (PVGO, IV15, dividend sustainability) and loan tools. Fetches live data from Yahoo Finance. |
| `tests/`     | Unit tests for the backend. |
| `docs/`      | The published site — dashboards, calculators and articles. Served by GitHub Pages. |
| `docs/basket/` | Basket Rotation: results of the ratio-basket mean-reversion strategy (pages + run data). |
| `generated/` | Raw output of the daily and monthly analysis runs: `alphaspread/` (dated `nasdaq/` and `sp500/` charts plus valuation JSON), `fairvalue/` (dated valuation JSON per index), `macro/`, and the shared `sp500_weights.json`. |
| `papers/`    | Trading notes and papers, in Markdown and PDF. |

## Running locally

One script starts the whole site, including the calculators' backend:

```bash
scripts/nexus.sh --start     # site on http://localhost:8080, backend on http://localhost:8000
scripts/nexus.sh --status    # what is running
scripts/nexus.sh --stop      # stop both
scripts/nexus.sh --restart   # stop, then start
```

The first `--start` creates `.venv/` and installs
[`server/requirements.txt`](server/requirements.txt), which takes a minute. Later
starts reinstall only if that file changed. The script needs Python 3.10 or
newer with `venv` support; it skips a `python3` that can't create a venv (for
example one from another project's activated venv). Set `NEXUS_PYTHON` to choose
the interpreter yourself.

Both servers run in the background and bind to `127.0.0.1` only. Logs go to
`.run/site.log` and `.run/backend.log`. The ports are fixed: the pages call the
backend on 8000, and the backend accepts requests only from known origins
(`localhost:8080`, `file://` and the GitHub Pages site).

When a calculator page is opened on `localhost` or from disk it calls the local
backend, which needs no API token. On GitHub Pages it calls the hosted backend on
Render, which needs the token pasted into the page. The backend checks a token
only if the `API_TOKEN` environment variable is set; the launcher always unsets it.

Interactive API docs are at <http://localhost:8000/docs>. To run the tests:

```bash
.venv/bin/python -m unittest discover -s tests -t .
```

## Generating the data

```bash
pip install -r requirements.txt   # plotly + kaleido>=1.0

# AlphaSpread: daily valuation run for an index → JSON + dated HTML + PNG
python scripts/alphaspread_index.py --nasdaq100 \
    --out  generated/alphaspread/nasdaq100_valuations.json \
    --html generated/alphaspread/nasdaq/nasdaq_analysis_$(date +%F).html \
    --png  generated/alphaspread/nasdaq/nasdaq_analysis_$(date +%F).png

python scripts/alphaspread_index.py --sp500 \
    --out  generated/alphaspread/sp500_valuations.json \
    --html generated/alphaspread/sp500/sp500_analysis_$(date +%F).html \
    --png  generated/alphaspread/sp500/sp500_analysis_$(date +%F).png

# Fair Value: value every constituent → generated/fairvalue/ JSON and
# docs/fairvalue/stocks/<TICKER>.html summary pages (needs SEC_USER_AGENT)
cd fairvalue && mise run install
mise exec -- python -m fvmodel index --index nasdaq100
mise exec -- python -m fvmodel index --index sp500
cd ..

# Publish either source's run as a dated snapshot for the site
python scripts/publish_site_data.py --source fairvalue --index sp500 --date $(date +%F) \
    --src generated/fairvalue/sp500_valuations.json
```

The runs are rate-limit-safe and resumable. Full usage, flags and the
one-company lookup are documented in [`scripts/README.md`](scripts/README.md).

## Site

<https://doruirimescu.github.io/stock-market-data/>

Pages is served from the `master` branch, `/docs` folder. `docs/.nojekyll`
disables Jekyll so the HTML is published verbatim.

The valuation pages (`nasdaq_today.html`, `sp500_today.html`,
`sp500_valuation.html`) render client-side from dated snapshots in
`docs/data/{source}/{nasdaq,sp500}/YYYY-MM-DD.js`, listed in
`docs/data/{source}/manifest.js`, where source is `alphaspread` or `fairvalue`
(each is the day's JSON wrapped in one line of JavaScript so it can be loaded
with a `<script>` tag).
They open the newest date and offer a date picker (`?date=YYYY-MM-DD` links to a
specific day), plus a source switch (`?source=alphaspread|fairvalue|combined`).
Combined averages each stock's valuation gap and solvency over the sources that
value it, pairing each source's newest snapshot on or before the chosen date.
Both sources use the same record shape: valuation gap = (value − price) / value,
positive when undervalued, and a 0–100 solvency score.

`docs/fairvalue/` holds a Fair Value summary page per stock
(`stocks/<TICKER>.html`), an index of them, and the validation of the model
against values Fair Value published (`validation.html`). The daily workflow publishes each run with
`scripts/publish_site_data.py`, which skips runs where most lookups failed.
Shared styling and rendering live in `docs/assets/`. The pages work when opened
directly from disk (`file://`) as well as when served.

## Basket Rotation

<https://doruirimescu.github.io/stock-market-data/basket/>

Results of the ratio-basket mean-reversion strategy (the `mrscore` engine in
`python-trading/Trading/basket`). Every pair of disjoint equal-weight baskets
from a 9-ticker universe becomes a ratio series. The engine scores how reliably
each ratio reverts to its mean, and the best ratios are backtested as an
all-in rotation between the two baskets.

| Page | Shows |
| ---- | ----- |
| `basket/index.html` | Leaderboard of the top baskets, the score distribution over every scanned ratio, ticker membership, universe returns and correlations |
| `basket/basket.html` | One ratio in depth: events, rotation signal and leg held, equity vs buy & hold, drawdown, trade blotter, event diagnostics |
| `basket/lab.html` | Strategy Lab: edit the config and re-run the whole scan and backtests in the browser (a JavaScript port of the engine, checked against the Python run), a 2-D parameter sweep, and `config.yaml` export |
| `basket/algorithm.html` | The pipeline, event lifecycle and rotation rules, with the selected run's parameters |
| `basket/trend.html` | Sector Trend research: nine sector ETFs with a 10-month trend filter vs the S&P 500 since 2000 (growth, drawdowns, calendar years, allocation history, lookback robustness, current allocation). Data: `docs/basket/data/trend_research.js` |

Each run is one file, `docs/basket/data/runs/<run_id>.js`, listed newest-first in
`docs/basket/data/manifest.js` (key `basket_manifest`). Every page has a run picker
(`?run=<run_id>` links to one). The runs are produced and published from
`python-trading/Trading/basket`:

```bash
./web.sh export    # run config.yaml, write a new run into docs/basket/data
./web.sh trend     # run config_trend.yaml, refresh docs/basket/data/trend_research.js
./web.sh start     # preview at http://127.0.0.1:8765/basket/  (./web.sh stop to stop)
./web.sh publish   # commit docs/basket/ here and push
```

The pages also work from disk and under `scripts/nexus.sh` (`/basket/`). They link
the live Nexus stylesheet and chart helper (`nexus-design`).

## Updating

The AlphaSpread valuation generator now lives here in [`scripts/`](scripts/) and
writes straight into `generated/alphaspread/` (see above); the Fair Value
model writes into `generated/fairvalue/` and `docs/fairvalue/`. Both run daily
in `.github/workflows/daily-analysis.yml`; the Fair Value job needs the
`SEC_USER_AGENT` repository secret (`"Your Name you@example.com"`) and skips
itself with a warning until it is set. The
remaining analysis scripts (macro, SP500 weights, the `docs/` calculators) still
live in `python-trading` and, as of the split, write into their old in-repo
paths — refreshing those means copying the new output over until that pipeline is
repointed here.
