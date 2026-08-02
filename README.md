# stock-market-data

Data, reports and writing split out of
[python-trading](https://github.com/doruirimescu/python-trading), which keeps
the code that produces them.

## Layout

| Path         | Contents |
| ------------ | -------- |
| `docs/`      | The published site — dashboards, calculators and articles. Served by GitHub Pages. |
| `generated/` | Raw output of the daily and monthly analysis runs (`nasdaq/`, `sp500/`, `macro/`, plus SP500 weights and valuation JSON). |
| `papers/`    | Trading notes and papers, in Markdown and PDF. |

## Site

<https://doruirimescu.github.io/stock-market-data/>

Pages is served from the `master` branch, `/docs` folder. `docs/.nojekyll`
disables Jekyll so the HTML is published verbatim.

## Updating

The analysis scripts live in `python-trading` and, as of this split, still
write into their old in-repo paths (`Trading/generated/`, `docs/`). Refreshing
this repo means copying the new output over until that pipeline is repointed
here.
