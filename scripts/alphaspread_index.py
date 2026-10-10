#!/usr/bin/env python3
"""
Fetch the constituents of an index (NASDAQ-100 or S&P 500), compute AlphaSpread
valuations for every company, store the results to JSON, and render an
interactive Plotly HTML chart.

Data flow:
    slickcharts (constituents) -> alphaspread.lookup() per ticker -> JSON
    -> visualize.build_html()/build_png() -> HTML + PNG

Outputs:
    JSON  : {index}_valuations.json          (stable name, keeps runs resumable)
    HTML  : {slug}_analysis_{date}.html       e.g. sp500_analysis_2026-05-14.html
    PNG   : {slug}_analysis_{date}.png        e.g. nasdaq_analysis_2026-05-14.png
  where slug is 'sp500' or 'nasdaq' and date defaults to today (override --date).

It's rate-limit-safe: runs sequentially with a delay between stocks and relies
on common.http_get()'s 429 backoff. It's also RESUMABLE -- results are saved
after every stock, and re-running skips companies already done.

Usage:
    python alphaspread_index.py --nasdaq100
    python alphaspread_index.py --sp500
    python alphaspread_index.py --nasdaq100 --limit 25 --delay 1.0
    python alphaspread_index.py --nasdaq100 --retry-errors
    python alphaspread_index.py --nasdaq100 --visualize-only   # just rebuild HTML+PNG
    python alphaspread_index.py --sp500 --date 2026-05-14       # fixed date stamp

Requires: pip install plotly kaleido   (plotly for HTML, kaleido for the PNG)
"""

import argparse
import datetime
import html as htmllib
import json
import os
import re
import sys
import time

import common
import alphaspread
import visualize

INDEX_URLS = {
    "nasdaq100": "https://www.slickcharts.com/nasdaq100",
    "sp500": "https://www.slickcharts.com/sp500",
}
INDEX_TITLES = {"nasdaq100": "NASDAQ-100", "sp500": "S&P 500"}
# Filename prefix for the dated analysis outputs (HTML/PNG).
INDEX_SLUGS = {"nasdaq100": "nasdaq", "sp500": "sp500"}


def analysis_basename(index, date=None):
    """Return the dated output stem, e.g. 'sp500_analysis_2026-05-14'."""
    date = date or datetime.date.today().isoformat()
    return f"{INDEX_SLUGS[index]}_analysis_{date}"


# --------------------------------------------------------------------------- #
# Constituents
# --------------------------------------------------------------------------- #
def fetch_constituents(index):
    """Return an ordered list of (ticker, company_name) for the index."""
    txt = common.http_get(INDEX_URLS[index], timeout=30)
    # slickcharts links both the company name and the ticker to /symbol/TICKER;
    # the company-name link is the one whose text differs from the ticker.
    pairs = re.findall(r'href="/symbol/([A-Za-z.\-]{1,6})"[^>]*>([^<]+)</a>', txt)
    names, order = {}, []
    for tk, text in pairs:
        tk = tk.upper()
        text = htmllib.unescape(text).strip()
        if text.upper() != tk and tk not in names:
            names[tk] = text
            order.append(tk)
    if not order:
        raise RuntimeError(f"Could not parse constituents from {INDEX_URLS[index]}")
    return [(tk, names[tk]) for tk in order]


# --------------------------------------------------------------------------- #
# Result storage
# --------------------------------------------------------------------------- #
def load_results(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_results(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def build_record(symbol, name, d):
    """Turn an alphaspread.lookup() result into our stored record.

    valuation_score is signed: positive = undervalued (upside), negative =
    overvalued (downside), so the chart's bars point up/down meaningfully.
    """
    vt = d.get("valuation")
    pct = d.get("valuation_pct")
    score = None
    if vt and pct is not None:
        score = pct if vt == "Undervalued" else -pct
    return {
        "symbol": symbol,
        "company": d.get("company") or name,
        "exchange": d.get("exchange"),
        "url": d.get("url"),
        "valuation_type": vt,
        "valuation_pct": pct,
        "valuation_score": score,
        "intrinsic_value": d.get("intrinsic_value"),
        "current_price_approx": d.get("current_price_approx"),
        "solvency_score": d.get("solvency_score"),
        "error": None,
    }


def _lookup(symbol, name):
    """Look up a company, trying ticker first, then the name."""
    try:
        return alphaspread.lookup(symbol)
    except Exception:  # noqa: BLE001
        return alphaspread.lookup(name)  # may raise; caller handles


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def render_outputs(good, title, html_path, png_path):
    """Write the HTML chart and, if possible, a matching PNG image."""
    visualize.build_html(good, html_path, title=title)
    print(f"[✓] Chart: {os.path.abspath(html_path)}  ({len(good)} stocks)")
    if png_path:
        try:
            visualize.build_png(good, png_path, title=title)
            print(f"[✓] Image: {os.path.abspath(png_path)}")
        except Exception as e:  # noqa: BLE001
            print(f"[!] Could not write PNG: {e}", file=sys.stderr)
            print("    (Static images need kaleido: pip install kaleido)",
                  file=sys.stderr)


def run(index, out_path, html_path, png_path=None, limit=None, delay=1.5,
        overwrite=False, retry_errors=False):
    title = INDEX_TITLES[index]
    print(f"[+] Index: {title}")
    print(f"[+] Fetching constituents...")
    constituents = fetch_constituents(index)
    if limit:
        constituents = constituents[:limit]
    total = len(constituents)
    print(f"[+] {total} constituents. Output: {os.path.abspath(out_path)}")

    results = {} if overwrite else load_results(out_path)

    done = ok = failed = skipped = 0
    for i, (symbol, name) in enumerate(constituents, 1):
        prev = results.get(symbol)
        if prev and not overwrite:
            already_ok = prev.get("error") is None
            if already_ok or not retry_errors:
                skipped += 1
                continue

        try:
            d = _lookup(symbol, name)
            results[symbol] = build_record(symbol, name, d)
            ok += 1
            r = results[symbol]
            vt = r["valuation_type"] or "?"
            sol = r["solvency_score"]
            print(f"  [{i}/{total}] OK   {symbol:6s} {vt} "
                  f"{('%+.0f%%' % r['valuation_score']) if r['valuation_score'] is not None else ''} "
                  f"solvency={sol if sol is not None else '?'}")
        except Exception as e:  # noqa: BLE001
            results[symbol] = {"symbol": symbol, "company": name, "error": str(e)}
            failed += 1
            print(f"  [{i}/{total}] FAIL {symbol:6s} -- {e}")

        done += 1
        save_results(out_path, results)   # resumable: persist after every stock
        time.sleep(delay)

    print(f"\n[✓] Processed {done} (ok {ok}, failed {failed}), skipped {skipped} "
          f"already-done.")
    print(f"[+] JSON: {os.path.abspath(out_path)}")

    good = {k: v for k, v in results.items() if not v.get("error")}
    if good:
        try:
            render_outputs(good, title, html_path, png_path)
        except Exception as e:  # noqa: BLE001
            print(f"[!] Could not build chart: {e}", file=sys.stderr)
            print("    (Is plotly installed?  pip install plotly)", file=sys.stderr)


def main():
    common.force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Compute AlphaSpread valuations for an index and chart them.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--nasdaq100", action="store_true", help="Use the NASDAQ-100.")
    g.add_argument("--sp500", action="store_true", help="Use the S&P 500.")
    ap.add_argument("--limit", type=int, help="Only the first N constituents.")
    ap.add_argument("--delay", type=float, default=1.5,
                    help="Seconds between stocks (rate-limit politeness, default 1.5).")
    ap.add_argument("--out", help="Output JSON path.")
    ap.add_argument("--html", help="Output HTML chart path.")
    ap.add_argument("--png", help="Output PNG image path.")
    ap.add_argument("--date", help="Date stamp for the analysis filenames "
                    "(YYYY-MM-DD; default today).")
    ap.add_argument("--no-png", action="store_true",
                    help="Skip writing the PNG image.")
    ap.add_argument("--overwrite", action="store_true",
                    help="Recompute everything, ignoring existing JSON.")
    ap.add_argument("--retry-errors", action="store_true",
                    help="Retry constituents that previously failed.")
    ap.add_argument("--visualize-only", action="store_true",
                    help="Skip fetching; just (re)build the HTML from the JSON.")
    args = ap.parse_args()

    index = "sp500" if args.sp500 else "nasdaq100"
    stem = analysis_basename(index, date=args.date)
    # JSON name stays stable (undated) so re-runs stay resumable; the HTML/PNG
    # analysis artifacts are dated, e.g. sp500_analysis_2026-05-14.html/.png.
    out_path = args.out or f"{index}_valuations.json"
    html_path = args.html or f"{stem}.html"
    png_path = None if args.no_png else (args.png or f"{stem}.png")

    if args.visualize_only:
        data = load_results(out_path)
        if not data:
            print(f"[x] No data in {out_path}", file=sys.stderr)
            sys.exit(1)
        good = {k: v for k, v in data.items() if not v.get("error")}
        render_outputs(good, INDEX_TITLES[index], html_path, png_path)
        return

    try:
        run(index, out_path, html_path, png_path=png_path, limit=args.limit,
            delay=args.delay, overwrite=args.overwrite,
            retry_errors=args.retry_errors)
    except KeyboardInterrupt:
        print("\n[i] Interrupted. Progress saved -- re-run to resume.", file=sys.stderr)
        sys.exit(130)


if __name__ == "__main__":
    main()
