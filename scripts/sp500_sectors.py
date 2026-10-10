#!/usr/bin/env python3
"""
Fetch the GICS sector of every S&P 500 constituent and store it as JSON.

The sector pages of the site (docs/sp500_sectors.html) group the daily
valuation snapshots by sector. The snapshots carry no sector, so the mapping
lives in its own file, refreshed now and then (index changes are rare):

    Wikipedia "List of S&P 500 companies" -> {ticker: {sector, industry}} -> JSON

Tickers keep the dotted share-class form (BRK.B, BF.B), as in the snapshots.
Publish the result for the site with
    python scripts/publish_site_data.py --sectors generated/sp500_sectors.json

Usage:
    python scripts/sp500_sectors.py                                 # -> generated/sp500_sectors.json
    python scripts/sp500_sectors.py --out some/other/path.json
"""

import argparse
import html as htmllib
import json
import os
import re
import sys

import common

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
MIN_ROWS = 450   # refuse to write a partial table (page layout changed, bad response)


def cell_text(cell):
    """Plain text of a table cell: tags dropped, entities decoded, whitespace collapsed."""
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", "", cell))).strip()


def fetch_sectors():
    """Return {ticker: {"sector": ..., "industry": ...}} from the constituents table."""
    page = common.http_get(URL, timeout=30)
    m = re.search(r'<table[^>]*id="constituents".*?</table>', page, re.S)
    if not m:
        raise RuntimeError(f"No constituents table on {URL}")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", m.group(0), re.S)
    header = [cell_text(c).lower() for c in re.findall(r"<th[^>]*>(.*?)</th>", rows[0], re.S)]
    col = {name: header.index(name) for name in ("symbol", "gics sector", "gics sub-industry")}
    out = {}
    for row in rows[1:]:
        cells = [cell_text(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
        if len(cells) < len(header):
            continue
        out[cells[col["symbol"]].upper()] = {
            "sector": cells[col["gics sector"]],
            "industry": cells[col["gics sub-industry"]],
        }
    if len(out) < MIN_ROWS:
        raise RuntimeError(f"Only {len(out)} constituents parsed from {URL}; expected ~500")
    return out


def main():
    common.force_utf8_stdout()
    ap = argparse.ArgumentParser(description="Fetch GICS sectors of the S&P 500 constituents.")
    ap.add_argument("--out", default=os.path.join(ROOT, "generated", "sp500_sectors.json"))
    args = ap.parse_args()
    sectors = fetch_sectors()
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(sectors.items())), f, indent=1, ensure_ascii=False)
        f.write("\n")
    counts = {}
    for v in sectors.values():
        counts[v["sector"]] = counts.get(v["sector"], 0) + 1
    print(f"[✓] {len(sectors)} constituents in {len(counts)} sectors -> {args.out}")
    for name, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"    {n:4d}  {name}")


if __name__ == "__main__":
    sys.exit(main())
