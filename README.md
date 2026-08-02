# stock-market-data

Data, reports and writing split out of
[python-trading](https://github.com/doruirimescu/python-trading). Most of the
producing code still lives there; the self-contained **AlphaSpread valuation
generator** is vendored here under [`scripts/`](scripts/).

## Layout

| Path         | Contents |
| ------------ | -------- |
| `scripts/`   | The AlphaSpread data-generation scripts — scrape index valuations and render the dated `nasdaq/` and `sp500/` charts. See [`scripts/README.md`](scripts/README.md). |
| `docs/`      | The published site — dashboards, calculators and articles. Served by GitHub Pages. |
| `generated/` | Raw output of the daily and monthly analysis runs (`nasdaq/`, `sp500/`, `macro/`, plus SP500 weights and valuation JSON). |
| `papers/`    | Trading notes and papers, in Markdown and PDF. |

## Generating the data

```bash
pip install -r requirements.txt   # plotly + kaleido>=1.0

# Daily valuation run for an index → JSON + dated HTML + PNG in generated/
python scripts/alphaspread_index.py --nasdaq100 \
    --out  generated/nasdaq100_valuations.json \
    --html generated/nasdaq/nasdaq_analysis_$(date +%F).html \
    --png  generated/nasdaq/nasdaq_analysis_$(date +%F).png

python scripts/alphaspread_index.py --sp500 \
    --out  generated/sp500_valuations.json \
    --html generated/sp500/sp500_analysis_$(date +%F).html \
    --png  generated/sp500/sp500_analysis_$(date +%F).png
```

The runs are rate-limit-safe and resumable. Full usage, flags and the
one-company lookup are documented in [`scripts/README.md`](scripts/README.md).

## Site

<https://doruirimescu.github.io/stock-market-data/>

Pages is served from the `master` branch, `/docs` folder. `docs/.nojekyll`
disables Jekyll so the HTML is published verbatim.

## Updating

The AlphaSpread valuation generator now lives here in [`scripts/`](scripts/) and
writes straight into `generated/nasdaq/` and `generated/sp500/` (see above). The
remaining analysis scripts (macro, SP500 weights, the `docs/` calculators) still
live in `python-trading` and, as of the split, write into their old in-repo
paths — refreshing those means copying the new output over until that pipeline is
repointed here.
