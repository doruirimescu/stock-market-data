#!/usr/bin/env python3
"""
Publish a valuations JSON as a dated snapshot for the GitHub Pages site.

GitHub Pages serves only docs/, so the valuation pages read their data from
docs/data/, one folder per valuation source (alphaspread, fairvalue):

    docs/data/{source}/{slug}/YYYY-MM-DD.js   one snapshot per index per day
    docs/data/{source}/manifest.js            {"nasdaq": [dates newest first], "sp500": [...]}
    docs/data/sp500_weights.js                market caps for the cap-weighted average
    docs/data/sp500_sectors.js                GICS sector of each S&P 500 stock (sector pages)

Each source has its own manifest, so the AlphaSpread and Fair Value jobs never
write the same file and can publish independently.

Each file is the JSON payload behind a one-line registration,
    window.nexusData = window.nexusData || {}; window.nexusData["<key>"] = {...};
so the pages can load it with a <script> tag. Unlike fetch(), that also works
when the HTML is opened straight from disk (file://).

The pages open the newest date in the manifest by default and offer a date
picker over the rest. A run where most lookups failed (e.g. AlphaSpread
answering 403) is not published, so "latest" always points at real data.

Usage:
    # Snapshot today's run and rebuild that source's manifest
    python scripts/publish_site_data.py --source alphaspread --index nasdaq --date 2026-10-08 \
        --src generated/alphaspread/nasdaq100_valuations.json
    python scripts/publish_site_data.py --source fairvalue --index sp500 --date 2026-10-10 \
        --src generated/fairvalue/sp500_valuations.json

    # Refresh the market-cap weights
    python scripts/publish_site_data.py --weights generated/sp500_weights.json

    # Refresh the sector map (from scripts/sp500_sectors.py)
    python scripts/publish_site_data.py --sectors generated/sp500_sectors.json

    # Only rebuild the manifests from the snapshots on disk
    python scripts/publish_site_data.py --manifest-only
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "docs", "data")
SLUGS = ("nasdaq", "sp500")
SOURCES = ("alphaspread", "fairvalue")
DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.js$")
MIN_VALID_SHARE = 0.5   # publish only if at least this share of stocks was valued


def write_js(path, key, data):
    """Write data as a script that registers it under window.nexusData[key]."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f'window.nexusData=window.nexusData||{{}};window.nexusData["{key}"]={payload};\n')
    return path


def is_usable(data):
    valid = sum(1 for r in data.values()
                if isinstance(r, dict) and not r.get("error")
                and isinstance(r.get("valuation_score"), (int, float)))
    return bool(data) and valid >= MIN_VALID_SHARE * len(data)


def write_snapshot(source, slug, date, src):
    """Write docs/data/{source}/{slug}/{date}.js; return its path, or None if the run is unusable."""
    with open(src, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not is_usable(data):
        return None
    return write_js(os.path.join(DATA_DIR, source, slug, f"{date}.js"), f"{source}/{slug}/{date}", data)


def write_weights(src):
    with open(src, "r", encoding="utf-8") as f:
        weights = {k: round(v) for k, v in json.load(f).items()}
    return write_js(os.path.join(DATA_DIR, "sp500_weights.js"), "sp500_weights", weights)


def write_sectors(src):
    """Publish {ticker: sector} only; the sub-industry is not used by the pages."""
    with open(src, "r", encoding="utf-8") as f:
        sectors = {k: v["sector"] for k, v in json.load(f).items()}
    return write_js(os.path.join(DATA_DIR, "sp500_sectors.js"), "sp500_sectors", sectors)


def build_manifest(source):
    manifest = {}
    for slug in SLUGS:
        d = os.path.join(DATA_DIR, source, slug)
        names = os.listdir(d) if os.path.isdir(d) else []
        dates = [m.group(1) for m in map(DATE_RE.match, names) if m]
        manifest[slug] = sorted(dates, reverse=True)
    path = write_js(os.path.join(DATA_DIR, source, "manifest.js"), f"{source}/manifest", manifest)
    return path, manifest


def main():
    ap = argparse.ArgumentParser(description="Publish a dated valuations snapshot to docs/data/.")
    ap.add_argument("--source", choices=SOURCES, default="alphaspread", help="Valuation source.")
    ap.add_argument("--index", choices=SLUGS, help="Site slug of the index.")
    ap.add_argument("--date", help="Snapshot date, YYYY-MM-DD.")
    ap.add_argument("--src", help="Valuations JSON to snapshot.")
    ap.add_argument("--weights", help="Market-cap weights JSON to publish (sp500_weights.json).")
    ap.add_argument("--sectors", help="Sector map JSON to publish (sp500_sectors.json).")
    ap.add_argument("--manifest-only", action="store_true", help="Only rebuild the manifests.")
    args = ap.parse_args()

    if args.weights:
        print(f"[✓] Wrote weights -> {write_weights(args.weights)}")
    if args.sectors:
        print(f"[✓] Wrote sectors -> {write_sectors(args.sectors)}")
    if not (args.manifest_only or args.weights or args.sectors):
        if not (args.index and args.date and args.src):
            ap.error("--index, --date and --src are required unless --manifest-only, --weights or --sectors")
        out = write_snapshot(args.source, args.index, args.date, args.src)
        if out:
            print(f"[✓] Wrote snapshot -> {out}")
        else:
            print(f"[!] Skipped {args.source} {args.index} {args.date}: fewer than "
                  f"{MIN_VALID_SHARE:.0%} of stocks were valued", file=sys.stderr)
    sources = SOURCES if args.manifest_only else (args.source,)
    for source in sources:
        path, manifest = build_manifest(source)
        counts = ", ".join(f"{k}: {len(v)}" for k, v in manifest.items())
        print(f"[✓] Wrote manifest -> {path} ({counts})")


if __name__ == "__main__":
    main()
