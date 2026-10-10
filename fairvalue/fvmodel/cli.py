"""Command line: `fvmodel analyze AAPL MSFT` and `fvmodel compare`."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from . import compare as cmp
from .metrics import analyze
from .render import render_site

DEFAULT_TICKERS = ["AAPL", "MSFT", "NVDA", "KO", "JNJ", "XOM", "WMT", "PG", "HD", "CAT"]


def _analyze_all(tickers):
    reports = []
    for t in tickers:
        try:
            reports.append(analyze(t))
            print(f"  {t}: ok", file=sys.stderr)
        except Exception as e:  # keep going; one bad filer should not sink the batch
            print(f"  {t}: FAILED ({e})", file=sys.stderr)
    return reports


def _comparison(reports):
    ref = cmp.load_reference()
    cache = {}

    def analyze_at(ticker, when):
        if (ticker, when) not in cache:
            cache[(ticker, when)] = analyze(ticker, as_of=when)
        return cache[(ticker, when)]

    rows = [row for r in reports for row in cmp.compare_ticker(r.ticker, ref.get(r.ticker, {}), analyze_at)]
    return {"rows": rows, "summary": cmp.summarize(rows), "tickers": sorted({r.ticker for r in rows})}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fvmodel")
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="analyze tickers and build the dashboard site")
    a.add_argument("tickers", nargs="*", default=DEFAULT_TICKERS)
    a.add_argument("--out", default="site")
    c = sub.add_parser("compare", help="analyze the reference tickers and compare with Fair Value values")
    c.add_argument("--out", default="site")
    i = sub.add_parser("index", help="value a whole index and publish pages + AlphaSpread-style records")
    i.add_argument("--index", choices=["sp500", "nasdaq100"], required=True)
    i.add_argument("--date", help="snapshot date YYYY-MM-DD (default today)")
    i.add_argument("--out", help="latest-run JSON (default ../generated/fairvalue/<index>_valuations.json)")
    i.add_argument("--pages", help="where stock pages go (default ../docs/fairvalue)")
    i.add_argument("--workers", type=int, default=4)
    i.add_argument("--limit", type=int, help="only the first N constituents (testing)")
    args = ap.parse_args(argv)
    if args.cmd == "index":
        from . import indexrun

        indexrun.main(args)
        return

    tickers = args.tickers if args.cmd == "analyze" else sorted(cmp.load_reference()) or DEFAULT_TICKERS
    reports = _analyze_all([t.upper() for t in tickers])
    comparison = _comparison(reports) if args.cmd == "compare" and cmp.REFERENCE.exists() else None
    out = Path(args.out)
    render_site(reports, out, comparison)
    if comparison:
        dump = {"summary": comparison["summary"], "rows": [asdict(r) for r in comparison["rows"]]}
        cmp.REFERENCE.with_name("comparison.json").write_text(json.dumps(dump, indent=1, default=str))
        s = comparison["summary"]["by_status"]
        print(f"Compared {comparison['summary']['total']} values: {s}", file=sys.stderr)
    print(f"Wrote {out}/index.html", file=sys.stderr)


if __name__ == "__main__":
    main()
