# scripts/ — AlphaSpread data generation

Vendored generator that scrapes [AlphaSpread](https://www.alphaspread.com)
valuation + solvency for every constituent of an index and renders a dated
chart. Output lands in [`../generated/`](../generated/) using this repo's
convention: `nasdaq_analysis_YYYY-MM-DD.{html,png}` /
`sp500_analysis_YYYY-MM-DD.{html,png}`.

## Files

| File | Role |
| ---- | ---- |
| `common.py` | Polite HTTP GET helpers (gzip-aware, 429 backoff). **Stdlib only.** |
| `alphaspread.py` | Look up one company/ticker → intrinsic value, valuation verdict, solvency. Resolves ticker+exchange via Yahoo search, then scrapes the AlphaSpread page. |
| `alphaspread_index.py` | Driver: fetch index constituents (slickcharts) → `alphaspread.lookup()` per ticker → JSON → HTML + PNG. Rate-limit-safe and **resumable**. |
| `visualize.py` | Render a valuations JSON to a Plotly bar chart — `build_html()` (interactive) and `build_png()` (static). |

Data flow: `slickcharts → alphaspread.lookup() → {index}_valuations.json → visualize → HTML + PNG`.

## Install

```bash
pip install -r ../requirements.txt   # plotly + kaleido>=1.0
```

Only `plotly` (HTML) and `kaleido>=1.0` (PNG) are third-party; everything else is
the Python 3 standard library. `kaleido` renders PNGs through a headless Chrome it
locates on the system. **kaleido 0.2.x hangs with plotly 6.x — use 1.0+.**

## Usage

Filenames are dated automatically: `{slug}_analysis_{date}.{html,png}`, where
`slug` is `sp500` or `nasdaq` and `date` defaults to today (override `--date`).
The JSON name stays undated so re-runs resume instead of restarting.

```bash
# Full run (fetch + JSON + dated HTML + PNG), writing into generated/
python scripts/alphaspread_index.py --nasdaq100 \
    --out  generated/nasdaq100_valuations.json \
    --html generated/nasdaq/nasdaq_analysis_$(date +%F).html \
    --png  generated/nasdaq/nasdaq_analysis_$(date +%F).png

python scripts/alphaspread_index.py --sp500 \
    --out  generated/sp500_valuations.json \
    --html generated/sp500/sp500_analysis_$(date +%F).html \
    --png  generated/sp500/sp500_analysis_$(date +%F).png

# Re-render charts only, from an existing JSON (no network):
python scripts/alphaspread_index.py --sp500 --visualize-only \
    --out generated/sp500_valuations.json \
    --html generated/sp500/sp500_analysis_$(date +%F).html \
    --png  generated/sp500/sp500_analysis_$(date +%F).png

# One company, ad hoc:
python scripts/alphaspread.py "Apple"
python scripts/alphaspread.py NVDA --json
```

Handy flags on `alphaspread_index.py`: `--limit N` (first N constituents),
`--delay S` (politeness between stocks, default 1.5), `--date YYYY-MM-DD`,
`--overwrite`, `--retry-errors`, `--no-png`.

## Notes

- **Resumable:** results are saved to the JSON after every stock; re-running
  skips already-done tickers (use `--retry-errors` to re-attempt failures,
  `--overwrite` to recompute all).
- **Scraping:** valuations come from AlphaSpread's server-rendered HTML, so the
  regexes in `alphaspread.py` are the fragile part if their markup changes.
