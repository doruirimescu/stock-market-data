#!/usr/bin/env python3
"""
Look up a stock on AlphaSpread by company name (or ticker) and report its
valuation and solvency.

Give it a name like "Apple"; it resolves the ticker/exchange, finds the
AlphaSpread page (e.g. https://www.alphaspread.com/security/nasdaq/aapl/summary),
scrapes the server-rendered HTML, and prints:

    - Intrinsic value (AlphaSpread's estimate)
    - Valuation verdict (under/overvalued, and by how much)
    - Solvency score (out of 100)

How resolution works: the company name is resolved to a ticker + exchange via
Yahoo Finance's search API, then candidate AlphaSpread exchange slugs are probed
(AlphaSpread returns 404 for the wrong exchange, 200 for the right one).

Usage:
    python alphaspread.py "Apple"
    python alphaspread.py AAPL
    python alphaspread.py "Volkswagen" --json
    python alphaspread.py "Microsoft" --url    # just print the resolved URL
"""

import argparse
import html as htmllib
import json
import re
import sys
import urllib.error
import urllib.parse

import common

BASE = "https://www.alphaspread.com"

# Yahoo exchange label/code -> AlphaSpread URL slug (best-guess primary).
EXCHANGE_SLUGS = {
    "NASDAQ": "nasdaq", "NASDAQGS": "nasdaq", "NASDAQGM": "nasdaq",
    "NASDAQCM": "nasdaq", "NMS": "nasdaq", "NCM": "nasdaq", "NGM": "nasdaq",
    "NYSE": "nyse", "NYQ": "nyse",
    "NYSEARCA": "nysearca", "PCX": "nysearca", "ARCA": "nysearca",
    "NYSEAMERICAN": "amex", "AMEX": "amex", "ASE": "amex", "NYSE MKT": "amex",
    "OTC": "otc", "OID": "otc", "PNK": "pink", "PINK": "pink",
    "CBOE": "cboe", "BATS": "cboe",
    "XETRA": "xetra", "GER": "xetra",
    "FRANKFURT": "fra", "FRA": "fra",
    "LONDON": "lse", "LSE": "lse", "IOB": "lse",
    "TORONTO": "tsx", "TOR": "tsx", "TSX": "tsx",
    "SWISS": "six", "EBS": "six", "VTX": "six", "SIX": "six",
    "AMSTERDAM": "euronext", "PARIS": "euronext", "BRUSSELS": "euronext",
    "AUSTRALIAN": "asx", "ASX": "asx",
    "HONG KONG": "hkse", "HKG": "hkse",
    "TOKYO": "tse", "JPX": "tse",
}

# Fallbacks probed (in order) when the mapped slug misses or is unknown.
FALLBACK_SLUGS = ["nasdaq", "nyse", "amex", "nysearca", "otc", "pink", "lse",
                  "xetra", "six", "tsx", "asx", "euronext", "fra", "hkse",
                  "tse", "cboe"]

# Reporting currency by AlphaSpread exchange slug (the page serves some symbols
# as non-UTF-8 bytes, so we derive the currency from the exchange instead).
CURRENCY_BY_SLUG = {
    "nasdaq": "$", "nyse": "$", "amex": "$", "nysearca": "$", "otc": "$",
    "pink": "$", "cboe": "$",
    "xetra": "€", "fra": "€", "euronext": "€",
    "lse": "£", "six": "CHF ", "tsx": "C$", "asx": "A$",
    "hkse": "HK$", "tse": "¥",
}


# --------------------------------------------------------------------------- #
# Resolution: name/ticker -> AlphaSpread security page
# --------------------------------------------------------------------------- #
def _yahoo_quotes(query):
    """Resolve a name/ticker to candidate equity quotes via Yahoo search."""
    url = ("https://query2.finance.yahoo.com/v1/finance/search?q="
           + urllib.parse.quote(query) + "&quotesCount=6&newsCount=0")
    try:
        data = common.http_get_json(url, timeout=20)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Name lookup failed (Yahoo search): {e}")
    quotes = [q for q in data.get("quotes", []) if q.get("quoteType") == "EQUITY"]
    return quotes


def _candidate_slugs(quote):
    key = str(quote.get("exchDisp") or quote.get("exchange") or "").upper()
    slugs = []
    if key in EXCHANGE_SLUGS:
        slugs.append(EXCHANGE_SLUGS[key])
    for s in FALLBACK_SLUGS:
        if s not in slugs:
            slugs.append(s)
    return slugs


def resolve_security(query, max_probes=8):
    """Return (url, ticker, exchange_slug, html) for the best AlphaSpread match.

    Tries the query as a direct ticker first, then Yahoo-resolved candidates.
    Probes candidate exchange slugs and returns the first that yields a real
    page (HTTP 200). Raises RuntimeError if nothing matches.
    """
    attempts = []

    def try_url(slug, ticker):
        url = f"{BASE}/security/{slug}/{ticker.lower()}/summary"
        if url in attempts:
            return None
        attempts.append(url)
        try:
            return common.http_get(url, retries=1)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            raise

    # If the input looks like a bare ticker (ALL CAPS, e.g. AAPL, KO), try the
    # common US exchanges directly. Mixed-case input (e.g. "Apple", "Nestle")
    # is treated as a company name and resolved via search instead.
    if re.fullmatch(r"[A-Z][A-Z.\-]{0,5}", query.strip()):
        for slug in ("nasdaq", "nyse", "amex"):
            html = try_url(slug, query.strip())
            if html:
                return (attempts[-1], query.strip().upper(), slug, html)

    quotes = _yahoo_quotes(query)
    if not quotes:
        raise RuntimeError(f"No equity found for '{query}'.")

    probes = 0
    for q in quotes:
        base_ticker = str(q.get("symbol", "")).split(".")[0]
        if not base_ticker:
            continue
        for slug in _candidate_slugs(q):
            if probes >= max_probes:
                break
            probes += 1
            html = try_url(slug, base_ticker)
            if html:
                return (attempts[-1], base_ticker.upper(), slug, html)

    raise RuntimeError(
        f"Could not find '{query}' on AlphaSpread. Tried: "
        + ", ".join(a.replace(BASE + "/security/", "") for a in attempts[:8]))


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
def _clean(s):
    return htmllib.unescape(re.sub(r"\s+", " ", s or "")).strip()


def parse_summary(html):
    """Pull company name, intrinsic value and valuation verdict off the page."""
    out = {"company": None, "intrinsic_value": None, "currency": "$",
           "valuation": None, "valuation_pct": None, "current_price_approx": None}

    title = re.search(r"<title>(.*?)</title>", html, re.S)
    if title:
        parts = [p.strip() for p in _clean(title.group(1)).split(" - ")]
        # "AAPL Intrinsic Valuation ... - Apple Inc - Alpha Spread"
        if len(parts) >= 3:
            out["company"] = parts[-2]
        elif parts:
            out["company"] = parts[0]

    # Grab just the number after the recommended-intrinsic-value label,
    # skipping any leading currency glyph (which may be a mangled byte).
    iv = re.search(r'mos-entry-recommended__title-price[^>]*>\s*'
                   r'[^\d<]{0,4}([\d,]+(?:\.\d+)?)', html)
    if iv:
        out["intrinsic_value"] = float(iv.group(1).replace(",", ""))

    verdict = re.search(r'(Under|Over)valued\s*by\s*([\d.]+)\s*%', html, re.I)
    if verdict:
        out["valuation"] = verdict.group(1).capitalize() + "valued"
        out["valuation_pct"] = float(verdict.group(2))

    # AlphaSpread reports valuation relative to intrinsic value, so we can
    # derive the (approximate) current price from the two.
    if out["intrinsic_value"] is not None and out["valuation_pct"] is not None:
        factor = 1 + out["valuation_pct"] / 100 if out["valuation"] == "Overvalued" \
            else 1 - out["valuation_pct"] / 100
        out["current_price_approx"] = round(out["intrinsic_value"] * factor, 2)
    return out


def fetch_solvency_score(url_summary):
    """Fetch the /solvency page and extract the score out of 100."""
    url = url_summary.rsplit("/", 1)[0] + "/solvency"
    try:
        html = common.http_get(url, retries=2)
    except Exception:  # noqa: BLE001
        return None
    m = re.search(r'solvency score is\s*(\d{1,3})\s*/\s*100', html, re.I)
    if not m:
        # Fallback: any "NN / 100" near the word "solvency".
        m = re.search(r'solvency[^0-9]{0,80}(\d{1,3})\s*/\s*100', html, re.I)
    return int(m.group(1)) if m else None


def lookup(query):
    """Resolve + parse everything into one result dict."""
    url, ticker, exchange, html = resolve_security(query)
    data = parse_summary(html)
    data["currency"] = CURRENCY_BY_SLUG.get(exchange, "$")
    data.update({
        "query": query,
        "ticker": ticker,
        "exchange": exchange,
        "url": url,
        "solvency_score": fetch_solvency_score(url),
    })
    return data


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #
def format_report(d):
    cur = d.get("currency") or "$"
    iv = d.get("intrinsic_value")
    price = d.get("current_price_approx")
    lines = []
    name = d.get("company") or d.get("ticker") or d.get("query")
    lines.append(f"{name}  ({d['ticker']} - {d['exchange'].upper()})")
    lines.append(d["url"])
    lines.append("")
    if d.get("valuation") and d.get("valuation_pct") is not None:
        lines.append(f"  Valuation      : {d['valuation']} by {d['valuation_pct']:.0f}%")
    else:
        lines.append("  Valuation      : (not found)")
    lines.append(f"  Intrinsic value: {cur}{iv:,.2f}" if iv is not None
                 else "  Intrinsic value: (not found)")
    lines.append(f"  Current price  : ~{cur}{price:,.2f} (derived)" if price is not None
                 else "  Current price  : (n/a)")
    score = d.get("solvency_score")
    lines.append(f"  Solvency score : {score}/100" if score is not None
                 else "  Solvency score : (not found)")
    return "\n".join(lines)


def main():
    common.force_utf8_stdout()
    ap = argparse.ArgumentParser(
        description="Look up a stock's valuation and solvency on AlphaSpread.")
    ap.add_argument("query", help="Company name or ticker, e.g. \"Apple\" or AAPL.")
    ap.add_argument("--json", action="store_true", help="Print raw JSON.")
    ap.add_argument("--url", action="store_true",
                    help="Only resolve and print the AlphaSpread URL.")
    args = ap.parse_args()

    try:
        if args.url:
            url, ticker, exch, _ = resolve_security(args.query)
            print(url)
            return
        data = lookup(args.query)
    except Exception as e:  # noqa: BLE001
        print(f"[x] {e}", file=sys.stderr)
        sys.exit(1)

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(format_report(data))


if __name__ == "__main__":
    main()
