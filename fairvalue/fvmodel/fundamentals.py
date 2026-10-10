"""Financial statement line items built from XBRL tags.

Companies tag the same concept differently (and change tags over the years), so
every line item lists alternatives in priority order. The first alternative that
yields a value for the requested period wins. Alternatives are a tag name, a
Sum of tags (any present components are added), or a Diff of two tags.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from . import config
from .xbrl import FactBook


@dataclass(frozen=True)
class Sum:
    tags: tuple[str, ...]

    def __init__(self, *tags: str):
        object.__setattr__(self, "tags", tags)


@dataclass(frozen=True)
class Diff:
    a: str
    b: str


Alt = str | Sum | Diff

# Duration items (income statement, cash flow): TTM or fiscal-year sums.
FLOWS: dict[str, tuple[Alt, ...]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
    ),
    "cogs": (
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
    ),
    "gross_profit": ("GrossProfit",),
    "sga": ("SellingGeneralAndAdministrativeExpense",),
    "rnd": ("ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
    "operating_income": ("OperatingIncomeLoss",),
    "pretax_income": (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    ),
    "income_tax": ("IncomeTaxExpenseBenefit",),
    "net_income": ("NetIncomeLoss", "ProfitLoss", "NetIncomeLossAvailableToCommonStockholdersBasic"),
    "eps_diluted": ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"),
    # "Other income (expense)": investment gains and losses, FX, pension items.
    # Interest is tagged separately and is not part of it.
    "other_nonoperating": ("OtherNonoperatingIncomeExpense",),
    "interest_expense": (
        "InterestExpense",
        "InterestExpenseNonoperating",
        "InterestExpenseDebt",
        "InterestAndDebtExpense",
        "InterestPaidNet",
    ),
    "dna": (
        "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet",
        "DepreciationAndAmortization",
        "DepreciationAmortizationAndOther",
        Sum("Depreciation", "AmortizationOfIntangibleAssets"),
    ),
    "cfo": (
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    ),
    "capex": (
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsToAcquireOtherPropertyPlantAndEquipment",
    ),
    "dividends_paid": ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends", "PaymentsOfOrdinaryDividends"),
    "buybacks": ("PaymentsForRepurchaseOfCommonStock",),
    "stock_issuance": ("ProceedsFromIssuanceOfCommonStock", "ProceedsFromStockOptionsExercised"),
    "sbc": ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
    "debt_repaid": ("RepaymentsOfLongTermDebt", "RepaymentsOfDebt"),
    "debt_issued": ("ProceedsFromIssuanceOfLongTermDebt", "ProceedsFromIssuanceOfDebt"),
    "shares_diluted": (
        "WeightedAverageNumberOfDilutedSharesOutstanding",
        "WeightedAverageNumberOfShareOutstandingBasicAndDiluted",
        "WeightedAverageNumberOfSharesOutstandingBasic",
    ),
}

# Instant items (balance sheet).
STOCKS: dict[str, tuple[Alt, ...]] = {
    "total_assets": ("Assets",),
    "current_assets": ("AssetsCurrent",),
    "total_liabilities": (
        "Liabilities",
        Diff("LiabilitiesAndStockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    ),
    "current_liabilities": ("LiabilitiesCurrent",),
    "equity": ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"),
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ),
    "st_investments": (
        "ShortTermInvestments",
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "OtherShortTermInvestments",
    ),
    "receivables": (
        "AccountsReceivableNetCurrent",
        "ReceivablesNetCurrent",
        "AccountsNotesAndLoansReceivableNetCurrent",
    ),
    "inventory": (
        "InventoryNet",
        Sum("InventoryCrudeOilProductsAndMerchandise", "InventoryPartsAndComponentsNetOfReserves"),
        "EnergyRelatedInventory",
    ),
    "payables": ("AccountsPayableCurrent", "AccountsPayableTradeCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"),
    # The reference provider "Accounts Payable & Accrued Expense" (used in invested capital)
    "payables_and_accrued": (
        "AccountsPayableAndAccruedLiabilitiesCurrent",
        Sum("AccountsPayableCurrent", "AccruedLiabilitiesCurrent"),
        Sum("AccountsPayableTradeCurrent", "AccruedLiabilitiesCurrent"),
    ),
    "ppe": (
        "PropertyPlantAndEquipmentNet",
        "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
    ),
    "goodwill": ("Goodwill",),
    "intangibles": ("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
    "retained_earnings": ("RetainedEarningsAccumulatedDeficit",),
    "debt_current": (
        "DebtCurrent",
        "LongTermDebtAndCapitalLeaseObligationsCurrent",
        Sum("LongTermDebtCurrent", "ShortTermBorrowings", "CommercialPaper", "OtherShortTermBorrowings"),
    ),
    "debt_noncurrent": (
        "LongTermDebtNoncurrent",
        "LongTermDebtAndCapitalLeaseObligations",
        Diff("LongTermDebt", "LongTermDebtCurrent"),
        # Unclassified balance sheets (financial companies): total debt in one line
        "LongTermDebt",
        "DebtLongtermAndShorttermCombinedAmount",
        Sum("SecuredDebt", "UnsecuredDebt", "NotesPayable"),
    ),
    "operating_lease": (
        "OperatingLeaseLiability",
        Sum("OperatingLeaseLiabilityCurrent", "OperatingLeaseLiabilityNoncurrent"),
    ),
    "shares_outstanding": ("dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"),
}

# A balance-sheet item missing at the latest quarter falls back to the last
# fiscal-year-end value (some items, e.g. lease liabilities or CAT's segment
# debt, are only tagged in the 10-K). Such items are recorded in `stale`.
STALE_FALLBACK_DAYS = 400
ANCHOR_TAGS = ("EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted", "NetIncomeLoss", "ProfitLoss")


def _fix_share_scale(shares: float, outstanding: float | None) -> float | None:
    """Undo a filer's scale error (shares tagged in thousands or millions).

    Weighted diluted shares are always within a few percent of the shares
    outstanding, so a ratio beyond 100x either way is a units mistake (seen in
    MCD filings): rescale by the power of 1000 that brings it back in line. A
    count no power of 1000 explains (e.g. BKR's predecessor LLC reporting 100
    units) is not a share count of this company, so it is dropped.
    """
    if not outstanding or not shares or shares <= 0:
        return shares
    ratio = shares / outstanding
    if 0.01 <= ratio <= 100:
        return shares
    k = round(-math.log(ratio, 1000))
    fixed = shares * 1000**k
    return fixed if 0.5 <= fixed / outstanding <= 2 else None


def _resolve(alts: tuple[Alt, ...], get: Callable[[str], float | None]) -> float | None:
    for alt in alts:
        if isinstance(alt, str):
            v = get(alt)
        elif isinstance(alt, Sum):
            parts = [get(t) for t in alt.tags]
            v = sum(p for p in parts if p is not None) if any(p is not None for p in parts) else None
        else:
            a, b = get(alt.a), get(alt.b)
            v = a - b if a is not None and b is not None else None
        if v is not None:
            return v
    return None


@dataclass
class Fundamentals:
    """Statement data for one company: TTM/MRQ snapshots and fiscal-year history."""

    book: FactBook
    as_of: date = field(init=False)
    fy_ends: list[date] = field(init=False)
    stale: dict[str, date] = field(init=False, default_factory=dict)
    stale_flows: dict[str, date] = field(init=False, default_factory=dict)

    def __post_init__(self):
        ends = self.book.period_ends(ANCHOR_TAGS)
        if not ends:
            raise ValueError("No 10-K/10-Q periods found")
        self.as_of = ends[-1]
        self.fy_ends = self.book.fiscal_year_ends(ANCHOR_TAGS)

    # ---- raw accessors ---------------------------------------------------

    def ttm(self, name: str, end: date | None = None) -> float | None:
        end = end or self.as_of
        if name in DERIVED:
            return DERIVED[name](self, lambda n: self.ttm(n, end), lambda n: self.mrq(n, end))
        v = _resolve(FLOWS[name], lambda t: self.book.ttm(t, end))
        if v is None and end == self.as_of:
            # Tag dropped from the latest 10-Q: use the TTM one quarter earlier.
            prev = self.previous_period(end)
            if prev:
                v = _resolve(FLOWS[name], lambda t: self.book.ttm(t, prev))
                if v is not None:
                    self.stale_flows[name] = prev
        return v

    def eps_without_nri(self, end: date | None = None) -> float | None:
        """TTM diluted EPS without material other non-operating income.

        Large mark-to-market gains on equity stakes (AMZN's Anthropic stake
        in 2025-26) can double reported EPS for a few quarters. The reference
        provider values stocks on "EPS without NRI"; this approximates it by
        scaling EPS by (pretax - other non-operating) / pretax, i.e. at the
        company's own tax rate, when that item exceeds
        config.NRI_MIN_SHARE_OF_PRETAX of pretax income. Uses the exact TTM
        only (no stale fallback): a missing tag means no adjustment.
        """
        end = end or self.as_of
        eps = self.ttm("eps_diluted", end)
        other = _resolve(FLOWS["other_nonoperating"], lambda t: self.book.ttm(t, end))
        pretax = _resolve(FLOWS["pretax_income"], lambda t: self.book.ttm(t, end))
        if eps is None or other is None or not pretax or pretax <= 0:
            return eps
        if abs(other) < config.NRI_MIN_SHARE_OF_PRETAX * pretax:
            return eps
        core = pretax - other
        return eps * core / pretax if core > 0 else None

    def quarter(self, name: str, end: date | None = None) -> float | None:
        """Single fiscal-quarter flow ending at `end` (default: latest quarter)."""
        end = end or self.as_of
        if name in DERIVED:
            return DERIVED[name](self, lambda n: self.quarter(n, end), lambda n: self.mrq(n, end))
        return _resolve(FLOWS[name], lambda t: self.book.quarter(t, end))

    def previous_period(self, end: date | None = None) -> date | None:
        end = end or self.as_of
        ends = [e for e in self.book.period_ends(ANCHOR_TAGS) if 70 <= (end - e).days <= 110]
        return ends[-1] if ends else None

    def mrq(self, name: str, end: date | None = None) -> float | None:
        """Balance-sheet value at the most recent quarter end (or `end`)."""
        end = end or self.as_of
        if name in DERIVED:
            return DERIVED[name](self, lambda n: self.ttm(n, end), lambda n: self.mrq(n, end))
        if name == "shares_outstanding":
            return self._shares_outstanding(end)
        v = _resolve(STOCKS[name], lambda t: self.book.instant(t, end))
        if v is None:
            prior = [d for d in self.fy_ends if d < end and (end - d).days <= STALE_FALLBACK_DAYS]
            if prior:
                v = _resolve(STOCKS[name], lambda t: self.book.instant(t, prior[-1]))
                if v is not None and end == self.as_of:
                    self.stale[name] = prior[-1]
        return v

    def _shares_outstanding(self, end: date) -> float | None:
        # Cover-page share count is dated after the period end (filing date).
        for tag in STOCKS["shares_outstanding"]:
            pts = sorted(self.book.instants(tag).items())
            pts = [(d, v) for d, v in pts if d <= end + timedelta(days=120)]
            if pts:
                return pts[-1][1]
        return None

    def quarter_shares_diluted(self, end: date | None = None) -> float | None:
        end = end or self.as_of
        for tag in FLOWS["shares_diluted"]:
            v = self.book.latest_quarter(tag, end)
            if v is None:
                v = self.book.annual(tag).get(end)
            if v is not None:
                return _fix_share_scale(v, self._shares_outstanding(end) or self._nearest_shares_outstanding(end))
        return None

    def _nearest_shares_outstanding(self, end: date) -> float | None:
        """Cover-page share count closest in time (used only as a scale reference)."""
        for tag in STOCKS["shares_outstanding"]:
            pts = self.book.instants(tag)
            if pts:
                return pts[min(pts, key=lambda d: abs((d - end).days))]
        return None

    def annual(self, name: str) -> dict[date, float | None]:
        """Fiscal-year series (flows: FY totals, stocks: FY-end balances)."""
        out = {}
        for fy in self.fy_ends:
            flow = lambda n, fy=fy: self._annual_flow(n, fy)
            stock = lambda n, fy=fy: self._annual_stock(n, fy)
            if name in DERIVED:
                out[fy] = DERIVED[name](self, flow, stock)
            elif name in FLOWS:
                out[fy] = flow(name)
            else:
                out[fy] = stock(name)
        return out

    def _annual_flow(self, name: str, fy: date) -> float | None:
        if name in DERIVED:
            return DERIVED[name](self, lambda n: self._annual_flow(n, fy), lambda n: self._annual_stock(n, fy))
        return _resolve(FLOWS[name], lambda t: self.book.annual(t).get(fy))

    def _annual_stock(self, name: str, fy: date) -> float | None:
        if name in DERIVED:
            return DERIVED[name](self, lambda n: self._annual_flow(n, fy), lambda n: self._annual_stock(n, fy))
        if name == "shares_outstanding":
            return self._shares_outstanding(fy)
        return _resolve(STOCKS[name], lambda t: self.book.instant(t, fy))


# ---- derived items ------------------------------------------------------
# Each takes (fundamentals, flow_getter, stock_getter) for one period.


def _nz(*vals):
    return sum(v for v in vals if v is not None)


def _derive_gross_profit(f, flow, stock):
    rev, cogs = flow("revenue"), flow("cogs")
    gp = flow("_gross_profit_tag")
    if gp is not None:
        return gp
    return rev - cogs if rev is not None and cogs is not None else None


def _derive_operating_income(f, flow, stock):
    oi = flow("_operating_income_tag")
    if oi is not None:
        return oi
    pretax = flow("pretax_income")
    if pretax is None:
        return None
    return pretax + (flow("interest_expense") or 0.0)


def _derive_debt(f, flow, stock):
    parts = [stock("debt_current"), stock("debt_noncurrent")]
    if config.INCLUDE_OPERATING_LEASES_IN_DEBT:
        parts.append(stock("operating_lease"))
    return _nz(*parts) if any(p is not None for p in parts) else None


def _derive_cash_total(f, flow, stock):
    cash = stock("cash")
    return None if cash is None else cash + (stock("st_investments") or 0.0)


def _derive_ebit(f, flow, stock):
    pretax = flow("pretax_income")
    if pretax is None:
        return flow("operating_income")
    return pretax + (flow("interest_expense") or 0.0)


def _derive_ebitda(f, flow, stock):
    ebit = flow("ebit")
    return None if ebit is None else ebit + (flow("dna") or 0.0)


def _derive_fcf(f, flow, stock):
    cfo = flow("cfo")
    return None if cfo is None else cfo - abs(flow("capex") or 0.0)


def _derive_tangible_equity(f, flow, stock):
    eq = stock("equity")
    return None if eq is None else eq - (stock("goodwill") or 0.0) - (stock("intangibles") or 0.0)


DERIVED: dict[str, Callable] = {
    "gross_profit": _derive_gross_profit,
    "operating_income": _derive_operating_income,
    "total_debt": _derive_debt,
    "cash_and_st_investments": _derive_cash_total,
    "ebit": _derive_ebit,
    "ebitda": _derive_ebitda,
    "fcf": _derive_fcf,
    "tangible_equity": _derive_tangible_equity,
}

# Tag-only versions of items that have a derived fallback.
FLOWS["_gross_profit_tag"] = FLOWS.pop("gross_profit")
FLOWS["_operating_income_tag"] = FLOWS.pop("operating_income")
