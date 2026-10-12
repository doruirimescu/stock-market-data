#!/usr/bin/env python3
"""
STOXX Europe 600 constituents, from the holdings of the iShares STOXX Europe 600
UCITS ETF (DE), which fully replicates the index.

Each constituent comes with its listing exchange, GICS sector, country and the
fund's EUR market value in it. The market value is proportional to the stock's
free-float market cap (the index weighting), so it serves as the cap weight.

    python scripts/stoxx600.py                # print a summary
    python scripts/stoxx600.py --json out.json
    python scripts/stoxx600.py --sectors generated/stoxx600_sectors.json   # for the sector page

Used by alphaspread_index.py --stoxx600. Stdlib only.
"""

import argparse
import csv
import io
import json
import re
import sys
import urllib.request

HOLDINGS_URL = ("https://www.ishares.com/de/privatanleger/de/produkte/251931/"
                "ishares-stoxx-europe-600-ucits-etf-de/latest-holdings.csv")
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/125.0 Safari/537.36")

# iShares (German site) sector labels -> GICS sector names used across the site.
SECTORS = {
    "IT": "Information Technology",
    "Finanzwesen": "Financials",
    "Gesundheitsversorgung": "Health Care",
    "Industrie": "Industrials",
    "Nichtzyklische Konsumgüter": "Consumer Staples",
    "Zyklische Konsumgüter": "Consumer Discretionary",
    "Energie": "Energy",
    "Materialien": "Materials",
    "Versorger": "Utilities",
    "Kommunikation": "Communication Services",
    "Immobilien": "Real Estate",
}

COUNTRIES = {
    "Vereinigtes Königreich": "United Kingdom", "Frankreich": "France", "Deutschland": "Germany",
    "Schweiz": "Switzerland", "Schweden": "Sweden", "Italien": "Italy", "Niederlande": "Netherlands",
    "Spanien": "Spain", "Dänemark": "Denmark", "Norwegen": "Norway", "Finnland": "Finland",
    "Polen": "Poland", "Belgien": "Belgium", "Griechenland": "Greece", "Österreich": "Austria",
    "Irland": "Ireland", "Portugal": "Portugal", "Luxemburg": "Luxembourg", "Jersey": "Jersey",
}

# Listing exchange (as iShares names it) -> AlphaSpread URL slugs to try, best first,
# and the price currency. Found by probing AlphaSpread (it answers 404 for a wrong slug); it
# also accepts ISO MIC codes for some venues (Brussels is only reachable as xbru).
EXCHANGES = {
    "London Stock Exchange": (["lse"], "£"),
    "Nyse Euronext - Euronext Paris": (["par", "euronext"], "€"),
    "Xetra": (["xetra", "fra"], "€"),
    "Deutsche Börse AG": (["xetra", "fra"], "€"),
    "SIX Swiss Exchange": (["six"], "CHF "),
    "Nasdaq Omx Nordic": (["sto"], "SEK "),
    "Borsa Italiana": (["mil"], "€"),
    "Euronext Amsterdam": (["aex", "ams", "euronext"], "€"),
    "Bolsa De Madrid": (["mad"], "€"),
    "Omx Nordic Exchange Copenhagen A/S": (["cse"], "DKK "),
    "Oslo Bors Asa": (["ose", "xosl"], "NOK "),
    "Nasdaq Omx Helsinki Ltd.": (["omxh", "hel", "xhel"], "€"),
    "Warsaw Stock Exchange/Equities/Main Market": (["wse", "xwar"], "PLN "),
    "Nyse Euronext - Euronext Brussels": (["xbru"], "€"),
    "Athens Exchange S.A. Cash Market": (["athex", "xath"], "€"),
    "Wiener Boerse Ag": (["vse", "vie", "xwbo"], "€"),
    "Irish Stock Exchange - All Market": (["ise", "xdub", "lse"], "€"),
    "Nyse Euronext - Euronext Lisbon": (["eli", "els", "xlis", "bvl"], "€"),
}


def _num(s):
    """German number format: '1.234.567,89' -> 1234567.89."""
    return float(s.replace(".", "").replace(",", ".")) if s and s != "-" else 0.0


def ticker_variants(ticker):
    """AlphaSpread spellings to try for an exchange ticker: 'RR.' -> 'rr',
    'NOVO B' -> 'novo-b', 'novo b', 'novob'; 'NDA FI' -> 'nda-fi', 'nda'."""
    t = ticker.strip().lower().rstrip(".")
    out = [t]
    if " " in t:
        a, b = t.split(" ", 1)
        out += [f"{a}-{b}", f"{a}.{b}", a + b, a]
    if "." in t:
        out += [t.replace(".", "-"), t.replace(".", "")]
    seen, res = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


# Market suffix (Yahoo style) that disambiguates a ticker listed by two constituents
# on different exchanges: SAN is Banco Santander in Madrid and Sanofi in Paris.
SUFFIXES = {
    "London Stock Exchange": "L", "Nyse Euronext - Euronext Paris": "PA", "Xetra": "DE",
    "Deutsche Börse AG": "DE", "SIX Swiss Exchange": "SW", "Nasdaq Omx Nordic": "ST", "Borsa Italiana": "MI",
    "Euronext Amsterdam": "AS", "Bolsa De Madrid": "MC", "Omx Nordic Exchange Copenhagen A/S": "CO",
    "Oslo Bors Asa": "OL", "Nasdaq Omx Helsinki Ltd.": "HE", "Warsaw Stock Exchange/Equities/Main Market": "WA",
    "Nyse Euronext - Euronext Brussels": "BR", "Athens Exchange S.A. Cash Market": "AT", "Wiener Boerse Ag": "VI",
    "Irish Stock Exchange - All Market": "IR", "Nyse Euronext - Euronext Lisbon": "LS",
}

# Constituents AlphaSpread lists elsewhere (ticker -> "slug/ticker" candidates, best
# first). Some SIX tickers resolve to the US company with the same symbol (six/rop is
# Roper Technologies, six/rog is Rogers Corp), so Roche falls back to its US ADR; the
# valuation gap is the same company's. Novonesis is still filed under Novozymes' ticker.
ALPHASPREAD_OVERRIDES = {"ROP": ["six/ro", "otc/rhhby"], "NSIS B": ["cse/nzym b", "otc/nvzmy"],
                         "WISE": ["nasdaq/wise", "nyse/wise"], "MTLN": ["athex/mytil", "xath/mytil"]}

# Companies AlphaSpread lists under an older or longer name (ticker -> words of that name).
NAME_ALIASES = {"DHL": "deutsche post", "PEO": "kasa opieki", "AYV": "ald", "HIAB": "cargotec",
                "MTLN": "mytilineos"}

# Words that say nothing about which company it is.
_GENERIC = {"ag", "sa", "se", "nv", "plc", "spa", "ab", "asa", "as", "a/s", "oyj", "inc", "ltd", "group",
            "holding", "holdings", "the", "and", "co", "corp", "company", "n", "ps", "par", "reg", "class",
            "bearer", "pref", "ord", "de", "of", "sca", "kgaa", "publ", "bv", "aktiengesellschaft", "societe",
            "international", "industries", "bank", "deutsche", "banco", "banca", "compagnie", "generale",
            "royal", "national", "svenska", "first", "european", "euro", "general", "credit"}


def _name_tokens(name):
    t = re.sub(r"[^a-z0-9 ]", " ", (name or "").lower().replace("&", " "))
    return [w for w in t.split() if w not in _GENERIC and len(w) >= 2]


def names_match(ours, theirs, ticker=None):
    """Loose company-name match (iShares 'ROCHE PS PAR AG' vs AlphaSpread 'Roche Holding AG').

    True when a distinctive word of one name shares its first 4 letters (or the
    whole word, if shorter) with a word of the other, or the initials of one spell
    a word of the other ('LVMH'). Guards against a ticker that AlphaSpread maps
    to another company on that exchange (six/rop is Roper Technologies, not Roche).
    """
    if ticker and ticker in NAME_ALIASES and NAME_ALIASES[ticker] in (theirs or "").lower():
        return True
    a, b = _name_tokens(ours), _name_tokens(theirs)
    if not a or not b:
        return True   # nothing to compare: don't reject
    key = lambda w: w[:4]
    if {key(w) for w in a} & {key(w) for w in b}:
        return True
    initials = lambda ws: "".join(w[0] for w in ws)
    ja, jb = "".join(a), "".join(b)
    joined = lambda n: re.sub(r"[^a-z0-9]", "", (n or "").lower())   # "l'oreal" -> "loreal"
    return (initials(a) in b or initials(b) in a
            or any(w in jb or w in joined(theirs) for w in a if len(w) >= 4)
            or any(w in ja or w in joined(ours) for w in b if len(w) >= 4))


def fetch_holdings(url=HOLDINGS_URL):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8-sig", "replace")
    lines = text.splitlines()
    as_of = None
    m = re.search(r'"([^"]+)"', lines[0]) if lines else None
    if m:
        as_of = m.group(1)
    start = next(i for i, l in enumerate(lines) if l.startswith("Emittententicker"))
    return as_of, list(csv.DictReader(io.StringIO("\n".join(lines[start:]))))


def constituents():
    """[(symbol, name, meta)] for every equity holding with a positive weight, largest first."""
    as_of, rows = fetch_holdings()
    out = []
    for r in rows:
        if r.get("Anlageklasse") != "Aktien":
            continue
        mv = _num(r.get("Marktwert", "0"))
        if mv <= 0:      # leftovers after an index deletion
            continue
        exch = r.get("Börse", "").strip()
        slugs, cur = EXCHANGES.get(exch, ([], "€"))
        sector_raw = r.get("Sektor", "").replace("\xa0", " ").strip()
        country_raw = r.get("Standort", "").strip()
        out.append((r["Emittententicker"].strip(), r["Name"].strip().title(), {
            "ticker": r["Emittententicker"].strip(),
            "exchange_name": exch,
            "slugs": slugs,
            "currency": cur,
            "sector": SECTORS.get(sector_raw, sector_raw or "Unclassified"),
            "country": COUNTRIES.get(country_raw, country_raw or "Other"),
            "weight": round(_num(r.get("Gewichtung (%)", "0")), 4),
            "market_value_eur": round(mv),
            "holdings_as_of": as_of,
        }))
    out.sort(key=lambda x: -x[2]["market_value_eur"])
    # Tickers listed by two constituents get a market suffix, so records stay distinct.
    seen = {}
    for sym, _, _ in out:
        seen[sym] = seen.get(sym, 0) + 1
    out = [(f"{sym}.{SUFFIXES.get(m['exchange_name'], 'X')}" if seen[sym] > 1 else sym, n, m) for sym, n, m in out]
    if len(out) < 500:
        raise RuntimeError(f"Only {len(out)} STOXX 600 holdings parsed from {HOLDINGS_URL}")
    return out


def main():
    ap = argparse.ArgumentParser(description="STOXX Europe 600 constituents from iShares holdings.")
    ap.add_argument("--json", help="Write [{symbol, name, ...meta}] to this file.")
    ap.add_argument("--sectors", help="Write {symbol: {sector, country}} (publish_site_data.py --sectors).")
    args = ap.parse_args()
    cons = constituents()
    unknown = sorted({m["exchange_name"] for _, _, m in cons if not m["slugs"]})
    print(f"{len(cons)} constituents (holdings as of {cons[0][2]['holdings_as_of']}); "
          f"unmapped exchanges: {unknown or 'none'}", file=sys.stderr)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump([{"symbol": s, "name": n, **m} for s, n, m in cons], f, indent=1, ensure_ascii=False)
    if args.sectors:
        with open(args.sectors, "w", encoding="utf-8") as f:
            json.dump({s: {"sector": m["sector"], "country": m["country"]} for s, _, m in cons}, f,
                      indent=1, ensure_ascii=False, sort_keys=True)


if __name__ == "__main__":
    main()
