"""Value every stock in an index and write AlphaSpread-compatible records.

The records use the same fields as scripts/alphaspread_index.py, so the site's
valuation pages can show either source (or both) with one renderer:

    valuation_type   "Undervalued" | "Overvalued"
    valuation_pct    |value - price| / value * 100
    valuation_score  signed: + undervalued, - overvalued
    intrinsic_value  Fair Value
    solvency_score   0-100 balance-sheet strength

plus Fair Value-specific extras (quality_score, ranks, market_cap...).
"""

from __future__ import annotations

import html as htmllib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import requests

from . import market, sec
from .metrics import analyze
from .render import render_site

SLICKCHARTS = {"sp500": "https://www.slickcharts.com/sp500", "nasdaq100": "https://www.slickcharts.com/nasdaq100"}
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"


def fetch_constituents(index: str) -> list[tuple[str, str]]:
    """(ticker, company) pairs from slickcharts, the same source the AlphaSpread run uses."""
    txt = requests.get(SLICKCHARTS[index], headers={"User-Agent": BROWSER_UA}, timeout=30).text
    pairs = re.findall(r'href="/symbol/([A-Za-z.\-]{1,6})"[^>]*>([^<]+)</a>', txt)
    names, order = {}, []
    for tk, text in pairs:
        tk, text = tk.upper(), htmllib.unescape(text).strip()
        if text.upper() != tk and tk not in names:
            names[tk] = text
            order.append(tk)
    if not order:
        raise RuntimeError(f"Could not parse constituents from {SLICKCHARTS[index]}")
    return [(tk, names[tk]) for tk in order]


# A price more than twice the fair value gives gaps of -100% and beyond (boom-cycle
# stocks reach -800%). AlphaSpread's gaps stay within about -91..+65%, so the
# snapshot caps ours at -100% to keep a handful of stocks from dominating the
# index averages; the uncapped gap is kept in valuation_score_raw.
SCORE_FLOOR = -100.0


def to_record(r, page_url: str) -> dict:
    raw = r.m("valuation_score")
    score = None if raw is None else max(raw, SCORE_FLOOR)
    return {
        "symbol": r.ticker,
        "company": r.name,
        "exchange": None,
        "url": page_url,
        "valuation_type": None if score is None else ("Undervalued" if score >= 0 else "Overvalued"),
        "valuation_pct": None if score is None else round(abs(score), 1),
        "valuation_score": None if score is None else round(score, 1),
        "valuation_score_raw": None if raw is None else round(raw, 1),
        "intrinsic_value": None if r.m("fair_value") is None else round(r.m("fair_value"), 2),
        "current_price_approx": round(r.price, 2),
        "solvency_score": r.m("solvency_score"),
        "quality_score": r.m("quality_score"),
        "rank_financial_strength": r.m("rank_financial_strength"),
        "rank_profitability": r.m("rank_profitability"),
        "rank_growth": r.m("rank_growth"),
        "market_cap": None if r.market_cap is None else round(r.market_cap),
        "fundamentals_as_of": r.as_of.isoformat(),
        "financial": r.financial,
        "error": None if score is not None else "No Fair Value (insufficient earnings history)",
    }


def _warm_shared_caches():
    """Fetch data every worker needs once, before the thread pool starts."""
    sec.lookup("AAPL")
    market._closes(market.BENCHMARK)
    market._closes(market.TREASURY_10Y)
    try:
        market._cpi()
    except Exception:
        pass


def run(index: str, out_json: Path, pages_dir: Path, dated_json: Path | None = None,
        workers: int = 4, limit: int | None = None) -> dict:
    constituents = fetch_constituents(index)[:limit]
    print(f"[{index}] {len(constituents)} constituents", file=sys.stderr)
    _warm_shared_caches()
    results, reports = {}, []
    started = time.time()

    def job(tk, name):
        return tk, name, analyze(tk)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(job, tk, name) for tk, name in constituents]
        for i, fut in enumerate(as_completed(futures), 1):
            try:
                tk, name, r = fut.result()
                results[tk] = to_record(r, f"fairvalue/stocks/{r.ticker}.html")
                reports.append(r)
            except Exception as e:  # one bad filer must not sink the run
                tk = constituents[futures.index(fut)][0]
                name = constituents[futures.index(fut)][1]
                results[tk] = {"symbol": tk, "company": name, "url": None, "valuation_type": None,
                               "valuation_pct": None, "valuation_score": None, "intrinsic_value": None,
                               "current_price_approx": None, "solvency_score": None,
                               "error": f"{type(e).__name__}: {e}"[:300]}
            if i % 25 == 0 or i == len(futures):
                ok = sum(1 for v in results.values() if v.get("valuation_score") is not None)
                print(f"[{index}] {i}/{len(futures)} done, {ok} valued, {time.time() - started:.0f}s", file=sys.stderr)

    ordered = {tk: results[tk] for tk, _ in constituents if tk in results}
    for path in filter(None, (out_json, dated_json)):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(ordered, indent=1, ensure_ascii=False))
        os.replace(tmp, path)
    render_site(reports, pages_dir)
    return ordered


def main(args) -> None:
    repo = Path(__file__).resolve().parents[2]
    slug = {"sp500": "sp500", "nasdaq100": "nasdaq"}[args.index]
    day = args.date or date.today().isoformat()
    out = Path(args.out) if args.out else repo / "generated" / "fairvalue" / f"{args.index}_valuations.json"
    dated = repo / "generated" / "fairvalue" / slug / f"{slug}_fairvalue_{day}.json"
    pages = Path(args.pages) if args.pages else repo / "docs" / "fairvalue"
    data = run(args.index, out, pages, dated, workers=args.workers, limit=args.limit)
    ok = sum(1 for v in data.values() if v.get("valuation_score") is not None)
    print(f"[{args.index}] wrote {out} ({ok}/{len(data)} valued)", file=sys.stderr)
