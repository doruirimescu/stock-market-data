"""Companies without SEC filings (the STOXX Europe 600): statements from Yahoo Finance.

`YahooBook` answers the same queries as `xbrl.FactBook` (annual, TTM, quarter and
balance-sheet values, period ends) under the US-GAAP tag names that
`fundamentals.py` asks for, so `Fundamentals`, the multiple history and every
metric in `metrics/compute.py` run unchanged.

Differences from SEC data, and how they are handled:

  * Depth: Yahoo has about four fiscal years and the last five or six quarters.
    That covers the 3-year price-to-sales window behind the Fair Value; 5- and
    10-year growth rates and the 10-year ranges come out shorter or empty.
  * Semi-annual reporters (Nestle, most of the UK) have no quarterly income
    statement, so their TTM is the last fiscal year.
  * Currency: statements are in the reporting currency, prices in the trading
    currency (HSBC reports in USD and trades in pence). Every monetary value is
    converted at the exchange rate of its period end, so price multiples compare
    like with like.
  * Splits: share counts and EPS from before a split are restated to today's
    share basis when the count matches the pre-split basis.

`load_market_eu` builds the Market with the STOXX Europe 600 as the beta
benchmark and the trading currency's 10-year government bond yield (FRED) as the
risk-free rate.
"""

from __future__ import annotations

import io
import math
import os
import threading
import time
import urllib.request
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import yfinance as yf

from . import market
from .xbrl import FactBook

CACHE_DIR = Path(os.environ.get("FVMODEL_DATA", Path(__file__).resolve().parents[1] / "data")) / "yahoo"
MAX_AGE = 24 * 3600
BENCHMARK_EU = "^STOXX"

# US-GAAP tag -> Yahoo statement rows, best first.
FLOW_ROWS: dict[str, tuple[str, ...]] = {
    "Revenues": ("TotalRevenue", "OperatingRevenue"),
    "CostOfRevenue": ("CostOfRevenue", "ReconciledCostOfRevenue"),
    "GrossProfit": ("GrossProfit",),
    "SellingGeneralAndAdministrativeExpense": ("SellingGeneralAndAdministration",),
    "ResearchAndDevelopmentExpense": ("ResearchAndDevelopment",),
    "OperatingIncomeLoss": ("OperatingIncome", "TotalOperatingIncomeAsReported"),
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": ("PretaxIncome",),
    "IncomeTaxExpenseBenefit": ("TaxProvision",),
    "NetIncomeLoss": ("NetIncomeCommonStockholders", "NetIncome", "NetIncomeContinuousOperations"),
    "EarningsPerShareDiluted": ("DilutedEPS", "BasicEPS"),
    "OtherNonoperatingIncomeExpense": ("OtherNonOperatingIncomeExpenses",),
    "InterestExpense": ("InterestExpense", "InterestExpenseNonOperating"),
    "DepreciationDepletionAndAmortization": ("DepreciationAndAmortization", "DepreciationAmortizationDepletion",
                                             "ReconciledDepreciation"),
    "NetCashProvidedByUsedInOperatingActivities": ("OperatingCashFlow", "CashFlowFromContinuingOperatingActivities"),
    "PaymentsToAcquirePropertyPlantAndEquipment": ("CapitalExpenditure", "PurchaseOfPPE"),
    "PaymentsOfDividendsCommonStock": ("CashDividendsPaid", "CommonStockDividendPaid"),
    "PaymentsForRepurchaseOfCommonStock": ("RepurchaseOfCapitalStock", "CommonStockPayments"),
    "ProceedsFromIssuanceOfCommonStock": ("IssuanceOfCapitalStock", "CommonStockIssuance"),
    "ShareBasedCompensation": ("StockBasedCompensation",),
    "RepaymentsOfLongTermDebt": ("RepaymentOfDebt", "LongTermDebtPayments"),
    "ProceedsFromIssuanceOfLongTermDebt": ("IssuanceOfDebt", "LongTermDebtIssuance"),
    "WeightedAverageNumberOfDilutedSharesOutstanding": ("DilutedAverageShares", "BasicAverageShares"),
}
# Yahoo reports cash outflows as negative numbers; SEC "Payments..." tags are positive.
OUTFLOWS = {"PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsOfDividendsCommonStock",
            "PaymentsForRepurchaseOfCommonStock", "RepaymentsOfLongTermDebt"}

STOCK_ROWS: dict[str, tuple[str, ...]] = {
    "Assets": ("TotalAssets",),
    "AssetsCurrent": ("CurrentAssets",),
    "Liabilities": ("TotalLiabilitiesNetMinorityInterest",),
    "LiabilitiesCurrent": ("CurrentLiabilities",),
    "StockholdersEquity": ("StockholdersEquity", "CommonStockEquity"),
    "CashAndCashEquivalentsAtCarryingValue": ("CashAndCashEquivalents", "CashFinancial"),
    "ShortTermInvestments": ("OtherShortTermInvestments",),
    "AccountsReceivableNetCurrent": ("AccountsReceivable", "Receivables"),
    "InventoryNet": ("Inventory",),
    "AccountsPayableCurrent": ("AccountsPayable",),
    "AccountsPayableAndAccruedLiabilitiesCurrent": ("PayablesAndAccruedExpenses",),
    "PropertyPlantAndEquipmentNet": ("NetPPE",),
    "Goodwill": ("Goodwill",),
    "IntangibleAssetsNetExcludingGoodwill": ("OtherIntangibleAssets",),
    "RetainedEarningsAccumulatedDeficit": ("RetainedEarnings",),
    "DebtCurrent": ("CurrentDebt",),
    "LongTermDebtNoncurrent": ("LongTermDebt",),
    "OperatingLeaseLiabilityCurrent": ("CurrentCapitalLeaseObligation",),
    "OperatingLeaseLiabilityNoncurrent": ("LongTermCapitalLeaseObligation",),
    "dei:EntityCommonStockSharesOutstanding": ("OrdinarySharesNumber", "ShareIssued"),
}
SHARE_TAGS = {"WeightedAverageNumberOfDilutedSharesOutstanding", "dei:EntityCommonStockSharesOutstanding"}
PER_SHARE_TAGS = {"EarningsPerShareDiluted"}

# Price currencies quoted in minor units (pence, cents).
MINOR = {"GBp": ("GBP", 100.0), "GBX": ("GBP", 100.0), "ZAc": ("ZAR", 100.0), "ILA": ("ILS", 100.0)}
# 10-year government bond yield by price currency (FRED, monthly, %).
RISK_FREE_FRED = {"EUR": "IRLTLT01DEM156N", "GBP": "IRLTLT01GBM156N", "CHF": "IRLTLT01CHM156N",
                  "SEK": "IRLTLT01SEM156N", "DKK": "IRLTLT01DKM156N", "NOK": "IRLTLT01NOM156N",
                  "PLN": "IRLTLT01PLM156N"}
# Site label for a price currency.
LABELS = {"EUR": "€", "GBp": "GBX ", "GBX": "GBX ", "GBP": "£", "USD": "$", "CHF": "CHF ", "SEK": "SEK ",
          "DKK": "DKK ", "NOK": "NOK ", "PLN": "PLN "}


# ---- cached downloads ---------------------------------------------------------

def _cached(name: str, fetch):
    path = CACHE_DIR / f"{name}.pkl"
    if path.exists() and time.time() - path.stat().st_mtime < MAX_AGE:
        return pd.read_pickle(path)
    data = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    pd.to_pickle(data, tmp)
    tmp.replace(path)
    return data


def statements(symbol: str) -> dict:
    """Income, balance-sheet and cash-flow statements (yearly and quarterly) plus currencies."""

    def fetch():
        t = yf.Ticker(symbol)
        out = {}
        for kind, getter in (("income", t.get_income_stmt), ("balance", t.get_balance_sheet),
                             ("cash", t.get_cashflow)):
            for freq in ("yearly", "quarterly"):
                try:
                    out[f"{kind}_{freq}"] = getter(freq=freq)
                except Exception:  # a missing statement is not fatal
                    out[f"{kind}_{freq}"] = pd.DataFrame()
        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass
        out["info"] = {k: info.get(k) for k in ("currency", "financialCurrency", "longName", "shortName",
                                               "sector", "industry", "quoteType")}
        # Empty answers are usually throttling: raise, so nothing empty gets cached.
        if all(out[k].empty for k in ("income_yearly", "income_quarterly")) or not out["info"]["currency"]:
            raise ValueError(f"Yahoo returned no statements or currency for {symbol} (rate-limited?)")
        return out

    return _cached(f"stmt_{symbol}", fetch)


def _fx_series(pair: str) -> pd.Series:
    def fetch():
        h = yf.Ticker(pair).history(period="10y", auto_adjust=False, actions=False)
        s = h["Close"].dropna()
        s.index = s.index.tz_localize(None).normalize()
        return s

    return _cached(f"fx_{pair.replace('=', '')}", fetch)


def fx_converter(fin: str | None, px: str | None):
    """Function date -> factor turning a reporting-currency amount into price-currency units."""
    px = px or fin or "USD"
    fin = fin or px
    major, scale = MINOR.get(px, (px, 1.0))
    if fin == major:
        return lambda d: scale
    series, invert = None, False
    for pair, inv in ((f"{fin}{major}=X", False), (f"{major}{fin}=X", True)):
        try:
            s = _fx_series(pair)
            if len(s):
                series, invert = s, inv
                break
        except Exception:
            continue
    if series is None:
        raise ValueError(f"No exchange rate for {fin}->{major}")

    def at(d: date) -> float:
        s = series[: pd.Timestamp(d)]
        v = float(s.iloc[-1]) if len(s) else float(series.iloc[0])
        return (1 / v if invert else v) * scale

    return at


def risk_free(px_currency: str | None) -> float | None:
    """Latest 10-year government bond yield (decimal) for the price currency, from FRED."""
    major = MINOR.get(px_currency or "", (px_currency, 1.0))[0]
    sid = RISK_FREE_FRED.get(major or "")
    if not sid:
        return None

    def fetch():
        # Plain urllib on purpose: FRED's CDN stalls requests with a custom User-Agent.
        text = urllib.request.urlopen(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}", timeout=60).read().decode()
        df = pd.read_csv(io.StringIO(text), parse_dates=[0], index_col=0)
        return pd.to_numeric(df.iloc[:, 0], errors="coerce").dropna()

    try:
        s = _cached(f"rf_{sid}", fetch)
        return float(s.iloc[-1]) / 100 if len(s) else None
    except Exception:
        return None


# ---- the book -------------------------------------------------------------------

def _rows(frame: pd.DataFrame, names: tuple[str, ...]) -> dict[date, float]:
    """First row of `names` present in a Yahoo statement, as {period end: value} (NaNs dropped)."""
    if frame is None or frame.empty:
        return {}
    out = {}
    for name in names:
        if name in frame.index:
            for col, v in frame.loc[name].items():
                if v is None or (isinstance(v, float) and math.isnan(v)):
                    continue
                d = pd.Timestamp(col).date()
                out.setdefault(d, float(v))
    return out


def _near(a: date, b: date, tol: int) -> bool:
    return abs((a - b).days) <= tol


class YahooBook(FactBook):
    """FactBook interface over Yahoo statements (see the module docstring)."""

    source = "yahoo"   # read by compute() to word its notes

    def __init__(self, stmts: dict, splits: list[tuple[date, float]] | None = None):
        info = stmts.get("info", {})
        self.currency = info.get("currency")
        self.financial_currency = info.get("financialCurrency") or self.currency
        fx = fx_converter(self.financial_currency, self.currency)
        self._annual: dict[str, dict[date, float]] = {}
        self._quarter: dict[str, dict[date, float]] = {}
        self._inst: dict[str, dict[date, float]] = {}

        def conv(tag, series):
            if tag in SHARE_TAGS:
                return dict(series)
            return {d: (abs(v) if tag in OUTFLOWS else v) * fx(d) for d, v in series.items()}

        for tag, rows in FLOW_ROWS.items():
            for freq, store in (("yearly", self._annual), ("quarterly", self._quarter)):
                series = {}
                for kind in ("income", "cash"):
                    for d, v in _rows(stmts.get(f"{kind}_{freq}"), rows).items():
                        series.setdefault(d, v)
                if series:
                    store[tag] = conv(tag, series)
        for tag, rows in STOCK_ROWS.items():
            series = {}
            for freq in ("quarterly", "yearly"):
                for d, v in _rows(stmts.get(f"balance_{freq}"), rows).items():
                    series.setdefault(d, v)
            if series:
                self._inst[tag] = conv(tag, series)
        self._restate_splits(splits or [])

    # Share counts reported before a split, on the old basis, are restated.
    def _restate_splits(self, splits):
        current = self._latest_shares()
        if not current or not splits:
            return
        for store in (self._annual, self._quarter, self._inst):
            for tag in list(store):
                if tag not in SHARE_TAGS and tag not in PER_SHARE_TAGS:
                    continue
                for d in list(store[tag]):
                    factor = 1.0
                    for when, ratio in splits:
                        if d < when:
                            factor *= ratio
                    if factor == 1.0:
                        continue
                    shares = self._shares_near(d)
                    # Only restate when the reported count sits on the pre-split basis.
                    if shares and abs(math.log(shares * factor / current)) < abs(math.log(shares / current)):
                        store[tag][d] = store[tag][d] * factor if tag in SHARE_TAGS else store[tag][d] / factor

    def _latest_shares(self):
        for tag in ("dei:EntityCommonStockSharesOutstanding", "WeightedAverageNumberOfDilutedSharesOutstanding"):
            for store in (self._inst, self._quarter, self._annual):
                s = store.get(tag)
                if s:
                    return s[max(s)]
        return None

    def _shares_near(self, d):
        for store in (self._annual, self._quarter, self._inst):
            for tag in ("WeightedAverageNumberOfDilutedSharesOutstanding", "dei:EntityCommonStockSharesOutstanding"):
                s = store.get(tag, {})
                hit = next((v for k, v in s.items() if _near(k, d, 10)), None)
                if hit:
                    return hit
        return None

    # ---- FactBook interface ----------------------------------------------------

    def has(self, tag: str) -> bool:
        return tag in self._annual or tag in self._quarter or tag in self._inst

    def facts(self, tag: str):
        return []

    def annual(self, tag: str) -> dict[date, float]:
        return dict(self._annual.get(tag, {}))

    def _q(self, tag: str, end: date) -> float | None:
        return next((v for d, v in self._quarter.get(tag, {}).items() if _near(d, end, 6)), None)

    def ttm(self, tag: str, end: date) -> float | None:
        a = next((v for d, v in self._annual.get(tag, {}).items() if _near(d, end, 6)), None)
        if a is not None:
            return a
        qs = [self._q(tag, end - timedelta(days=91 * i)) for i in range(4)]
        if any(v is None for v in qs):
            return None
        return sum(qs) / 4 if tag in SHARE_TAGS else sum(qs)

    def quarter(self, tag: str, end: date) -> float | None:
        return self._q(tag, end)

    def latest_quarter(self, tag: str, end: date) -> float | None:
        return self._q(tag, end)

    def instants(self, tag: str) -> dict[date, float]:
        if tag == "OperatingLeaseLiability":   # one line in SEC data, two in Yahoo
            cur, non = self._inst.get("OperatingLeaseLiabilityCurrent", {}), self._inst.get("OperatingLeaseLiabilityNoncurrent", {})
            return {d: cur.get(d, 0.0) + non.get(d, 0.0) for d in set(cur) | set(non)}
        return dict(self._inst.get(tag, {}))

    def period_ends(self, tags: tuple[str, ...]) -> list[date]:
        ends = set()
        for tag in tags:
            ends.update(self._annual.get(tag, {}))
            # A quarter end counts only when its TTM is complete (four quarters).
            ends.update(d for d in self._quarter.get(tag, {}) if self.ttm(tag, d) is not None)
        return sorted(ends)

    def fiscal_year_ends(self, tags: tuple[str, ...]) -> list[date]:
        ends = set()
        for tag in tags:
            ends.update(self._annual.get(tag, {}))
        return sorted(ends)


# ---- market -----------------------------------------------------------------------

def splits(symbol: str) -> list[tuple[date, float]]:
    h = market._history(symbol)
    s = h["Stock Splits"] if "Stock Splits" in h else pd.Series(dtype=float)
    return [(d.date(), float(r)) for d, r in s.items() if r and r != 1]


def load_market_eu(symbol: str, px_currency: str | None) -> market.Market:
    h = market._history(symbol)
    closes = h["Close"].dropna()
    if closes.empty:
        raise ValueError(f"No prices for {symbol}")
    rf = risk_free(px_currency)
    if rf is None:
        rf = float(market._closes(market.TREASURY_10Y).iloc[-1]) / 100
    return market.Market(symbol, closes, market._dividends(symbol), market._closes(BENCHMARK_EU), rf,
                         pd.Series(dtype=float))  # no European CPI: Shiller PE is left out


def currency_label(code: str | None) -> str:
    return LABELS.get(code or "", f"{code} " if code else "")
