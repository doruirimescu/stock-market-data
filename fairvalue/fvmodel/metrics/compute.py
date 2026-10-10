"""Compute the the reference provider summary-page metrics for one ticker.

Conventions follow docs/METHODOLOGY.md: flows are TTM, balances are MRQ,
return ratios use the average of the current and year-ago balance, growth rates
are per-share CAGRs on fiscal-year data, and percentages are plain numbers
(35.2 means 35.2%).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .. import config
from ..fundamentals import Fundamentals
from ..market import Market
from . import scoring
from .base import Metric, avg, cagr, clamp, div, pct
from .history import multiple_series, per_share_history, range_stats


@dataclass
class Report:
    ticker: str
    name: str
    as_of: date  # latest fiscal period end in the filings
    price: float
    price_date: date
    market_cap: float | None
    enterprise_value: float | None
    metrics: dict[str, Metric]
    annual: list[dict]
    charts: dict
    notes: list[str] = field(default_factory=list)
    closes: pd.Series | None = field(default=None, repr=False)
    financial: bool = False

    def m(self, key: str) -> float | None:
        metric = self.metrics.get(key)
        return metric.value if metric and metric.ok else None


# ---- helpers --------------------------------------------------------------


def _abs(v):
    return None if v is None else abs(v)


def _year_ago(f: Fundamentals, end: date) -> date | None:
    target = end - timedelta(days=365)
    ends = [e for e in f.book.period_ends(("EarningsPerShareDiluted", "NetIncomeLoss", "ProfitLoss"))
            if abs((e - target).days) <= 20]
    return min(ends, key=lambda e: abs((e - target).days)) if ends else None


def _rsi(closes: pd.Series, n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    delta = closes.diff().dropna()
    gain = delta.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    rs = gain.iloc[-1] / loss.iloc[-1] if loss.iloc[-1] else math.inf
    return float(100 - 100 / (1 + rs))


def _beta(stock: pd.Series, bench: pd.Series, years: int) -> float | None:
    start = stock.index[-1] - pd.DateOffset(years=years)
    if stock.index[0] > start:
        return 1.0  # the reference provider: beta = 1 with less than 3 years of history
    df = pd.concat([stock, bench], axis=1, keys=["s", "b"]).dropna()
    wk = df[df.index >= start].resample("W-FRI").last().pct_change().dropna()
    if len(wk) < 52:
        return None
    return float(np.cov(wk["s"], wk["b"])[0, 1] / np.var(wk["b"], ddof=1))


def _momentum(closes: pd.Series, months: int) -> float | None:
    """(price 1 month ago / price `months` ago - 1) in %."""
    t = closes.index[-1]
    p1 = closes[: t - pd.DateOffset(months=1)]
    p0 = closes[: t - pd.DateOffset(months=months)]
    if p1.empty or p0.empty:
        return None
    return float(p1.iloc[-1] / p0.iloc[-1] - 1) * 100


def _fy_series(f: Fundamentals, name: str, n: int = 11) -> tuple[list[date], list[float | None]]:
    series = f.annual(name)
    ends = f.fy_ends[-n:]
    return ends, [series.get(e) for e in ends]


def _growth(values: list[float | None], ends: list[date], years: int) -> float | None:
    """CAGR between the latest FY and the FY `years` earlier (checked by date)."""
    if len(values) <= years:
        return None
    if abs((ends[-1] - ends[-1 - years]).days - 365.25 * years) > 30:
        return None
    return cagr(values, years)


def _dcf_multiple(g: float, d: float) -> float:
    """Present value of 1 unit of earnings: 10 years at g, then 10 years at the terminal rate."""
    x = (1 + g) / (1 + d)
    y = (1 + config.DCF_TERMINAL_GROWTH) / (1 + d)
    n1, n2 = config.DCF_YEARS_GROWTH, config.DCF_YEARS_TERMINAL
    growth = x * (1 - x**n1) / (1 - x) if x != 1 else n1
    terminal = x**n1 * y * (1 - y**n2) / (1 - y) if y != 1 else x**n1 * n2
    return growth + terminal


def _dps_by_fy(dividends: pd.Series, ends: list[date]) -> list[float | None]:
    out = []
    for e in ends:
        lo = pd.Timestamp(e) - pd.Timedelta(days=365)
        window = dividends[(dividends.index > lo) & (dividends.index <= pd.Timestamp(e))]
        out.append(float(window.sum()))
    return out


# ---- main -----------------------------------------------------------------


# Metrics the reference provider does not compute for banks, insurers and REITs: their balance
# sheets are unclassified and "revenue" and "operating income" mean different things.
NOT_FOR_FINANCIALS = (
    "altman_z", "beneish_m", "current_ratio", "quick_ratio", "cash_ratio", "days_sales_outstanding",
    "days_inventory", "days_payable", "cash_conversion_cycle", "ncav", "nnwc", "price_to_ncav",
    "gross_margin", "roc_greenblatt", "roce", "interest_coverage", "epv", "price_to_epv",
)


def compute(ticker: str, name: str, f: Fundamentals, mk: Market, today: date | None = None,
            financial: bool = False) -> Report:
    M: dict[str, Metric] = {}
    notes: list[str] = []

    def put(key, label, value, unit="", better=None, note="", **kw):
        if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
            value = None
        M[key] = Metric(key, label, value, unit, better, note, **kw)
        return value

    as_of, prev = f.as_of, _year_ago(f, f.as_of)
    price = mk.price

    # TTM flows
    rev, cogs, gp = f.ttm("revenue"), f.ttm("cogs"), f.ttm("gross_profit")
    op_inc, pretax, tax = f.ttm("operating_income"), f.ttm("pretax_income"), f.ttm("income_tax")
    ni, eps = f.ttm("net_income"), f.ttm("eps_diluted")
    int_exp = _abs(f.ttm("interest_expense"))
    ebit, ebitda, dna = f.ttm("ebit"), f.ttm("ebitda"), f.ttm("dna")
    cfo, capex, fcf = f.ttm("cfo"), _abs(f.ttm("capex")), f.ttm("fcf")
    sga = f.ttm("sga")
    div_paid = _abs(f.ttm("dividends_paid")) or 0.0
    buybacks = _abs(f.ttm("buybacks")) or 0.0
    issuance = _abs(f.ttm("stock_issuance")) or 0.0
    debt_repaid, debt_issued = _abs(f.ttm("debt_repaid")) or 0.0, _abs(f.ttm("debt_issued")) or 0.0

    # MRQ balances
    assets, ca, cl = f.mrq("total_assets"), f.mrq("current_assets"), f.mrq("current_liabilities")
    liab, equity = f.mrq("total_liabilities"), f.mrq("equity")
    cash = f.mrq("cash_and_st_investments")
    ar, inv, ap = f.mrq("receivables"), f.mrq("inventory") or 0.0, f.mrq("payables")
    ppe, re_ = f.mrq("ppe"), f.mrq("retained_earnings")
    debt = f.mrq("total_debt") or 0.0
    tang_eq = f.mrq("tangible_equity")
    shares = f.mrq("shares_outstanding")
    sh_dil = f.quarter_shares_diluted() or shares

    # Year-ago values for averages, Piotroski and Beneish
    p = (lambda n: f.mrq(n, prev)) if prev else (lambda n: None)
    pt = (lambda n: f.ttm(n, prev)) if prev else (lambda n: None)
    avg_equity, avg_assets = avg(equity, p("equity")), avg(assets, p("total_assets"))
    avg_debt = avg(debt, p("total_debt"))

    mcap = price * shares if shares else None
    ev = None if mcap is None else mcap + debt - (cash or 0.0)
    no_debt = debt == 0

    # tax rate clipped to [0, 1]
    tax_rate = clamp(div(tax, pretax), 0.0, 1.0) if div(tax, pretax) is not None else None

    # ---- per share ------------------------------------------------------
    rev_ps, fcf_ps = div(rev, sh_dil), div(fcf, sh_dil)
    bvps, tbvps = div(equity, shares), div(tang_eq, shares)
    ebitda_ps = div(ebitda, sh_dil)

    # ---- annual history (fiscal years) ------------------------------------
    ends, a_rev = _fy_series(f, "revenue")
    _, a_sh = _fy_series(f, "shares_diluted")
    _, a_eps = _fy_series(f, "eps_diluted")
    _, a_ebitda = _fy_series(f, "ebitda")
    _, a_fcf = _fy_series(f, "fcf")
    _, a_eq = _fy_series(f, "equity")
    _, a_ni = _fy_series(f, "net_income")
    _, a_op = _fy_series(f, "operating_income")
    _, a_gp = _fy_series(f, "gross_profit")
    _, a_debt = _fy_series(f, "total_debt")
    _, a_assets = _fy_series(f, "total_assets")
    _, a_cfo = _fy_series(f, "cfo")
    _, a_capex = _fy_series(f, "capex")
    _, a_ppe = _fy_series(f, "ppe")
    _, a_tax = _fy_series(f, "income_tax")
    _, a_pretax = _fy_series(f, "pretax_income")
    _, a_sga = _fy_series(f, "sga")
    _, a_dna = _fy_series(f, "dna")
    _, a_sh_out = _fy_series(f, "shares_outstanding")

    def per_sh(vals):
        return [div(v, s) for v, s in zip(vals, a_sh)]

    a_rev_ps, a_ebitda_ps, a_fcf_ps = per_sh(a_rev), per_sh(a_ebitda), per_sh(a_fcf)
    a_bvps = [div(e, s) for e, s in zip(a_eq, a_sh_out)]
    a_bvps = [b if b is not None else div(e, s) for b, e, s in zip(a_bvps, a_eq, a_sh)]
    a_dps = _dps_by_fy(mk.dividends, ends)

    # ---- growth -----------------------------------------------------------
    g = {}
    for key, label, vals in [
        ("revenue", "Revenue per share", a_rev_ps),
        ("ebitda", "EBITDA per share", a_ebitda_ps),
        ("eps", "EPS", a_eps),
        ("fcf", "FCF per share", a_fcf_ps),
        ("book", "Book value per share", a_bvps),
        ("dividend", "Dividend per share", a_dps),
    ]:
        for n in (3, 5, 10):
            g[(key, n)] = _growth(vals, ends, n)
            put(f"{key}_growth_{n}y", f"{n}-Year {label} Growth", g[(key, n)], "%", "high")

    # ---- profitability ----------------------------------------------------
    put("gross_margin", "Gross Margin", pct(gp, rev), "%", "high")
    put("operating_margin", "Operating Margin", pct(op_inc, rev), "%", "high")
    put("net_margin", "Net Margin", pct(ni, rev), "%", "high")
    put("fcf_margin", "FCF Margin", pct(fcf, rev), "%", "high")
    put("roe", "ROE", pct(ni, avg_equity) if (avg_equity or 0) > 0 else None, "%", "high")
    put("roa", "ROA", pct(ni, avg_assets), "%", "high")

    def invested_capital(a, cur_a, cur_l, c, payables):
        if a is None:
            return None
        cur_a, cur_l, c = cur_a or 0.0, cur_l or 0.0, c or 0.0
        excess = max(0.0, c - max(0.0, cur_l - cur_a + c))
        return a - (payables or 0.0) - excess

    ic_now = invested_capital(assets, ca, cl, cash, f.mrq("payables_and_accrued"))
    ic_prev = invested_capital(p("total_assets"), p("current_assets"), p("current_liabilities"),
                               p("cash_and_st_investments"), p("payables_and_accrued"))
    nopat = None if op_inc is None or tax_rate is None else op_inc * (1 - tax_rate)
    roic = put("roic", "ROIC", pct(nopat, avg(ic_now, ic_prev)), "%", "high")

    # Annualized latest quarter (the reference provider's headline ROE/ROIC): quarter x 4
    # over the average of the quarter-start and quarter-end balances.
    pq = f.previous_period()
    if pq:
        q = lambda n: f.quarter(n)
        q_tax = div(q("income_tax"), q("pretax_income"))
        q_tax = clamp(q_tax, 0.0, 1.0) if q_tax is not None else tax_rate
        q_ni, q_op = q("net_income"), q("operating_income")
        eq_q = avg(equity, f.mrq("equity", pq))
        put("roe_quarterly", "ROE (annualized quarter)",
            pct(q_ni * 4, eq_q) if q_ni is not None and (eq_q or 0) > 0 else None, "%", "high")
        put("roa_quarterly", "ROA (annualized quarter)",
            pct(None if q_ni is None else q_ni * 4, avg(assets, f.mrq("total_assets", pq))), "%", "high")
        ic_pq = invested_capital(f.mrq("total_assets", pq), f.mrq("current_assets", pq), f.mrq("current_liabilities", pq),
                                 f.mrq("cash_and_st_investments", pq), f.mrq("payables_and_accrued", pq))
        put("roic_quarterly", "ROIC (annualized quarter)",
            pct(None if q_op is None or q_tax is None else q_op * 4 * (1 - q_tax), avg(ic_now, ic_pq)), "%", "high")

    def op_wc(ar_, inv_, ap_):
        return max(0.0, (ar_ or 0.0) + (inv_ or 0.0) - (ap_ or 0.0))

    cap_roc = avg(
        None if ppe is None else ppe + op_wc(ar, inv, ap),
        None if p("ppe") is None else p("ppe") + op_wc(p("receivables"), p("inventory"), p("payables")),
    )
    put("roc_greenblatt", "ROC (Joel Greenblatt)", pct(ebit, cap_roc), "%", "high")
    ce = avg(None if assets is None or cl is None else assets - cl,
             None if p("total_assets") is None or p("current_liabilities") is None else p("total_assets") - p("current_liabilities"))
    put("roce", "ROCE", pct(ebit, ce), "%", "high")
    last10 = [v for v in a_ni[-10:] if v is not None]
    years_profitable = sum(v > 0 for v in last10) if last10 else None
    put("years_profitable", "Years of Profitability (10Y)", years_profitable, "/10", "high")
    a_opm = [pct(o, r) for o, r in zip(a_op, a_rev)]
    opm5 = [v for v in a_opm[-5:] if v is not None]
    margin_trend = float(np.polyfit(range(len(opm5)), opm5, 1)[0]) if len(opm5) >= 3 else None
    put("operating_margin_trend", "5-Year Operating Margin Trend", margin_trend, "pp/yr", "high")

    # ---- financial strength -----------------------------------------------
    put("cash_to_debt", "Cash-to-Debt", None if no_debt else div(cash, debt), "x", "high",
        note="No debt" if no_debt else "")
    put("equity_to_asset", "Equity-to-Asset", div(equity, assets), "x", "high")
    put("debt_to_equity", "Debt-to-Equity", div(debt, equity) if (equity or 0) > 0 else None, "x", "low")
    put("debt_to_ebitda", "Debt-to-EBITDA", div(debt, ebitda) if (ebitda or 0) > 0 else None, "x", "low")
    put("debt_to_revenue", "Debt-to-Revenue", div(debt, rev), "x", "low")
    ic_note = "No debt" if no_debt else ("Interest expense not tagged in XBRL" if int_exp is None else "")
    put("interest_coverage", "Interest Coverage", div(op_inc, int_exp), "x", "high", note=ic_note)

    # Piotroski F-Score (TTM vs TTM a year earlier)
    pf = None
    if prev:
        ta0, ta1 = p("total_assets"), assets
        ni0 = pt("net_income")
        crit = [
            (ni or 0) > 0,
            (cfo or 0) > 0,
            (div(ni, ta1) or 0) > (div(ni0, ta0) or 0),
            (cfo or 0) > (ni or 0),
            (div(f.mrq("debt_noncurrent"), ta1) or 0) <= (div(p("debt_noncurrent"), ta0) or 0),
            (div(ca, cl) or 0) > (div(p("current_assets"), p("current_liabilities")) or 0),
            (sh_dil or 0) <= (f.quarter_shares_diluted(prev) or math.inf),
            (div(gp, rev) or 0) > (div(pt("gross_profit"), pt("revenue")) or 0),
            (div(rev, ta1) or 0) > (div(pt("revenue"), ta0) or 0),
        ]
        pf = sum(crit)
    put("piotroski_f", "Piotroski F-Score", pf, "/9", "high")

    # Altman Z-Score (original 1968 model)
    z = None
    if assets and liab and mcap:
        z = (1.2 * ((ca or 0) - (cl or 0)) / assets + 1.4 * (re_ or 0) / assets + 3.3 * (ebit or 0) / assets
             + 0.6 * mcap / liab + 1.0 * (rev or 0) / assets)
    zv = ("under", "Safe zone") if z and z > 2.99 else ("over", "Distress zone") if z is not None and z < 1.81 else (None, "Grey zone")
    put("altman_z", "Altman Z-Score", z, "", "high", verdict=zv[0], verdict_text=zv[1] if z is not None else "")

    # Beneish M-Score (TTM vs prior TTM)
    mscore = None
    if prev and rev and pt("revenue"):
        r1, r0 = rev, pt("revenue")
        ta1, ta0 = assets, p("total_assets")
        gm1 = div(gp, r1)
        gm0 = div(pt("gross_profit"), r0)
        ppe1, ppe0 = ppe or 0.0, p("ppe") or 0.0
        dep1, dep0 = dna or 0.0, pt("dna") or 0.0

        def safe(v, default=1.0):
            return default if v is None or v <= 0 or math.isnan(v) else v

        dsri = safe(div(div(ar, r1), div(p("receivables"), r0)))
        gmi = safe(div(gm0, gm1))
        aqi = safe(div(1 - ((ca or 0) + ppe1) / ta1, 1 - ((p("current_assets") or 0) + ppe0) / ta0) if ta1 and ta0 else None)
        sgi = safe(r1 / r0)
        depi = safe(div(div(dep0, dep0 + ppe0), div(dep1, dep1 + ppe1)))
        sgai = safe(div(div(sga, r1), div(pt("sga"), r0)))
        lvgi = safe(div(div((cl or 0) + (f.mrq("debt_noncurrent") or 0), ta1),
                        div((p("current_liabilities") or 0) + (p("debt_noncurrent") or 0), ta0)))
        tata = div((ni or 0) - (cfo or 0), ta1) or 0.0
        mscore = (-4.84 + 0.92 * dsri + 0.528 * gmi + 0.404 * aqi + 0.892 * sgi + 0.115 * depi
                  - 0.172 * sgai + 4.679 * tata - 0.327 * lvgi)
    put("beneish_m", "Beneish M-Score", mscore, "", "low",
        verdict=None if mscore is None else ("under" if mscore < -1.78 else "over"),
        verdict_text="" if mscore is None else ("Unlikely manipulator" if mscore < -1.78 else "Possible manipulator"))

    # WACC
    beta = _beta(mk.closes, mk.benchmark, config.BETA_YEARS)
    put("beta", "Beta", beta, "", None)
    ke = mk.risk_free + (beta or 1.0) * config.EQUITY_RISK_PREMIUM
    kd = div(int_exp, avg_debt) or 0.0
    wacc = None
    if mcap:
        d_ = avg_debt or 0.0
        wacc = (mcap * ke + d_ * kd * (1 - (tax_rate or 0))) / (mcap + d_) * 100
    put("wacc", "WACC", wacc, "%", "low")
    if roic is not None and wacc is not None:
        M["roic"].verdict = "under" if roic > wacc else "over"
        M["roic"].verdict_text = "ROIC > WACC" if roic > wacc else "ROIC < WACC"

    # ---- liquidity --------------------------------------------------------
    put("current_ratio", "Current Ratio", div(ca, cl), "x", "high")
    put("quick_ratio", "Quick Ratio", div(None if ca is None else ca - inv, cl), "x", "high")
    put("cash_ratio", "Cash Ratio", div(cash, cl), "x", "high")
    dso = None if ar is None or not rev else ar / rev * 365
    dio = None if not cogs else inv / cogs * 365
    dpo = None if ap is None or not cogs else ap / cogs * 365
    put("days_sales_outstanding", "Days Sales Outstanding", dso, "days", "low")
    put("days_inventory", "Days Inventory", dio, "days", "low")
    put("days_payable", "Days Payable", dpo, "days", "high")
    put("cash_conversion_cycle", "Cash Conversion Cycle",
        None if dso is None or dio is None or dpo is None else dso + dio - dpo, "days", "low")

    # ---- momentum -------------------------------------------------------
    c = mk.closes
    for n in (5, 9, 14):
        put(f"rsi_{n}", f"{n}-Day RSI", _rsi(c, n), "", None)
    m61, m121 = _momentum(c, 6), _momentum(c, 12)
    put("momentum_6_1", "6-1 Month Momentum", m61, "%", "high")
    put("momentum_12_1", "12-1 Month Momentum", m121, "%", "high")
    yr = c[c.index > c.index[-1] - pd.DateOffset(years=1)]
    put("high_52w", "52-Week High", float(yr.max()), "$")
    put("low_52w", "52-Week Low", float(yr.min()), "$")
    put("pct_below_high", "% Below 52-Week High", (1 - price / float(yr.max())) * 100, "%", "low")

    # ---- dividends & buybacks ------------------------------------------
    last_yr = mk.dividends[mk.dividends.index > c.index[-1] - pd.Timedelta(days=365)]
    dps = float(last_yr.sum())
    put("dividend_yield", "Dividend Yield", dps / price * 100, "%", "high")
    put("dividend_per_share", "Dividends per Share (TTM)", dps, "$")
    put("payout_ratio", "Dividend Payout Ratio", div(dps, eps) if (eps or 0) > 0 else None, "x", "low")
    g5div = g.get(("dividend", 5))
    put("yield_on_cost_5y", "5-Year Yield-on-Cost",
        None if g5div is None else dps / price * 100 * (1 + g5div / 100) ** 5, "%", "high")
    put("buyback_yield", "Buyback Yield", pct(buybacks - issuance, mcap), "%", "high")
    put("buyback_ratio_3y", "3-Year Share Buyback Ratio",
        None if len(a_sh) < 4 or not a_sh[-1] or not a_sh[-4] else (1 - (a_sh[-1] / a_sh[-4]) ** (1 / 3)) * 100,
        "%", "high")
    put("shareholder_yield", "Shareholder Yield",
        pct(div_paid + buybacks - issuance + debt_repaid - debt_issued, mcap), "%", "high")

    # ---- valuation ------------------------------------------------------
    put("price", "Price", price, "$")
    put("market_cap", "Market Cap", mcap, "$")
    put("enterprise_value", "Enterprise Value", ev, "$")

    hist = per_share_history(f)
    mult = multiple_series(c, hist, as_of)
    pe = div(price, eps) if (eps or 0) > 0 else None
    ps = div(price, rev_ps)
    pb = div(price, bvps) if (bvps or 0) > 0 else None
    pfcf = div(price, fcf_ps) if (fcf_ps or 0) > 0 else None
    put("pe_ttm", "PE Ratio (TTM)", pe, "x", "low", note="" if pe else "At loss",
        hist=range_stats(mult["pe"], pe))
    put("ps", "PS Ratio", ps, "x", "low", hist=range_stats(mult["ps"], ps))
    put("pb", "PB Ratio", pb, "x", "low", hist=range_stats(mult["pb"], pb))
    put("price_to_fcf", "Price-to-Free-Cash-Flow", pfcf, "x", "low", hist=range_stats(mult["pfcf"], pfcf))
    put("price_to_tangible_book", "Price-to-Tangible-Book", div(price, tbvps) if (tbvps or 0) > 0 else None, "x", "low")
    put("price_to_ocf", "Price-to-Operating-Cash-Flow", div(mcap, cfo) if (cfo or 0) > 0 else None, "x", "low")
    put("ev_to_ebit", "EV-to-EBIT", div(ev, ebit) if (ebit or 0) > 0 else None, "x", "low")
    put("ev_to_ebitda", "EV-to-EBITDA", div(ev, ebitda) if (ebitda or 0) > 0 else None, "x", "low")
    put("ev_to_revenue", "EV-to-Revenue", div(ev, rev), "x", "low")
    put("ev_to_fcf", "EV-to-FCF", div(ev, fcf) if (fcf or 0) > 0 else None, "x", "low")
    put("earnings_yield", "Earnings Yield (Greenblatt)", pct(ebit, ev), "%", "high")
    put("fcf_yield", "FCF Yield", pct(fcf, mcap), "%", "high")

    g5e = g.get(("ebitda", 5))
    put("peg", "PEG Ratio", div(pe, g5e) if pe and g5e and g5e > 0 else None, "x", "low",
        note="5-year EBITDA/share growth, as the reference provider")

    # Shiller PE: price / average inflation-adjusted EPS of the last 10 FYs
    shiller = None
    if not mk.cpi.empty and len([e for e in a_eps[-10:] if e is not None]) == 10:
        cpi_now = float(mk.cpi.iloc[-1])
        adj = []
        for e, v in zip(ends[-10:], a_eps[-10:]):
            s = mk.cpi[: pd.Timestamp(e)]
            adj.append(v * cpi_now / float(s.iloc[-1]) if len(s) else v)
        e10 = sum(adj) / 10
        shiller = div(price, e10) if e10 > 0 else None
    put("shiller_pe", "Shiller PE", shiller, "x", "low")

    # Intrinsic values
    graham = math.sqrt(22.5 * tbvps * eps) if (tbvps or 0) > 0 and (eps or 0) > 0 else None
    put("graham_number", "Graham Number", graham, "$")
    put("price_to_graham", "Price-to-Graham-Number", div(price, graham), "x", "low")

    # The reference provider uses book-value growth instead of EBITDA growth for financials.
    g_lynch = g.get(("book", 5)) if financial else g5e
    lynch = None
    if g_lynch is not None and g_lynch >= 5 and (eps or 0) > 0:
        lynch = min(g_lynch, 25) * eps
    put("peter_lynch_value", "Peter Lynch Fair Value", lynch, "$")
    put("price_to_lynch", "Price-to-Peter-Lynch-Fair-Value", div(price, lynch), "x", "low")

    ps_median = M["ps"].hist["median"] if M["ps"].hist else None
    med_ps_value = None if ps_median is None or rev_ps is None else ps_median * rev_ps
    put("median_ps_value", "Median PS Value", med_ps_value, "$")
    put("price_to_median_ps", "Price-to-Median-PS-Value", div(price, med_ps_value), "x", "low")

    d_rate = (math.ceil(mk.risk_free * 100) + 6) / 100
    g10 = g.get(("eps", 10))
    g_dcf = clamp((g10 if g10 is not None else 0) / 100, config.DCF_GROWTH_FLOOR, config.DCF_GROWTH_CAP)
    dcf = None
    if (eps or 0) > 0:
        dcf = eps * _dcf_multiple(g_dcf, d_rate)
        if config.DCF_ADD_TANGIBLE_BOOK and tbvps and tbvps > 0:
            dcf += tbvps
    put("dcf_earnings", "DCF (Earnings Based)", dcf, "$",
        note=f"growth {g_dcf*100:.1f}% for 10y, terminal {config.DCF_TERMINAL_GROWTH*100:.0f}% for 10y, discount {d_rate*100:.0f}%")
    put("price_to_dcf", "Price-to-DCF (Earnings Based)", div(price, dcf), "x", "low")

    fcf6 = [v for v in a_fcf[-6:] if v is not None]
    proj = None
    if len(fcf6) >= 4 and sh_dil and equity is not None:
        g5r = g.get(("revenue", 5)) or 0.0
        mult_g = clamp(_dcf_multiple(clamp(g5r / 100, 0, config.DCF_GROWTH_CAP), d_rate), *config.PROJ_FCF_MULTIPLE)
        proj = (mult_g * (sum(fcf6) / len(fcf6)) + config.PROJ_FCF_EQUITY_WEIGHT * equity) / sh_dil
        proj = proj if proj > 0 else None
    put("projected_fcf_value", "Intrinsic Value: Projected FCF", proj, "$")
    put("price_to_projected_fcf", "Price-to-Projected-FCF", div(price, proj), "x", "low")

    ncav = None if ca is None or liab is None or not shares else (ca - liab) / shares
    nnwc = None if liab is None or not shares else ((cash or 0) + 0.75 * (ar or 0) + 0.5 * inv - liab) / shares
    put("ncav", "Net Current Asset Value", ncav, "$")
    put("nnwc", "Net-Net Working Capital", nnwc, "$")
    put("price_to_ncav", "Price-to-Net-Current-Asset-Value", div(price, ncav) if (ncav or 0) > 0 else None, "x", "low")

    # Earnings Power Value (Greenwald)
    epv = None
    rev5 = [(r, o, s, t, pr, cx, pp, dn) for r, o, s, t, pr, cx, pp, dn in
            zip(a_rev[-6:], a_op[-6:], a_sga[-6:], a_tax[-6:], a_pretax[-6:], a_capex[-6:], a_ppe[-6:], a_dna[-6:])]
    if rev and len(rev5) == 6 and all(x[0] and x[1] is not None for x in rev5) and wacc:
        margins = [o / r for r, o, *_ in rev5[1:]]
        taxes = [clamp(t / pr, 0, 1) for _, _, _, t, pr, *_ in rev5[1:] if t is not None and pr]
        avg_tax = sum(taxes) / len(taxes) if taxes else 0.21
        norm_ebit = sum(margins) / len(margins) * rev
        maint = []
        for (r0, *_), (r1, _, _, _, _, cx, pp, _) in zip(rev5[:-1], rev5[1:]):
            growth_capex = (pp or 0) / r1 * (r1 - r0) if r1 > r0 else 0.0
            maint.append(max(0.0, abs(cx or 0) - growth_capex))
        avg_dna = sum((x[7] or 0) for x in rev5[1:]) / 5
        # Greenwald: NOPAT + D&A - maintenance capex. The 25% SG&A add-back and
        # excess-depreciation steps are omitted (see docs/METHODOLOGY.md).
        earn_power = norm_ebit * (1 - avg_tax) + avg_dna - sum(maint) / 5
        if sh_dil and earn_power > 0:
            epv = (earn_power / (wacc / 100) + (cash or 0) - debt) / sh_dil
    put("epv", "Earnings Power Value", epv, "$")
    put("price_to_epv", "Price-to-Earnings-Power-Value", div(price, epv) if (epv or 0) > 0 else None, "x", "low")

    # Yacktman forward rate of return
    fcf7 = [v for v in a_fcf_ps[-7:] if v is not None]
    g5r = g.get(("revenue", 5))
    frr = None
    if len(fcf7) >= 5 and g5r is not None:
        frr = (sum(fcf7) / len(fcf7)) / price * 100 + clamp(g5r, 0, 20)
    put("forward_rate_of_return", "Forward Rate of Return (Yacktman)", frr, "%", "high")

    # ---- Fair Value ---------------------------------------------------
    fund_now = {"pe": eps, "ps": rev_ps, "pb": bvps, "pfcf": fcf_ps}

    def fv_component(k, strict):
        series = mult[k]
        valid = series.dropna()
        min_years = 5 if strict else config.FAIR_VALUE_MIN_YEARS_FALLBACK
        if len(valid) < 250 * min_years or fund_now[k] is None or fund_now[k] <= 0:
            return None
        if strict and len(valid) < config.FAIR_VALUE_MIN_VALID_SHARE * len(series):
            return None
        return float(valid.median()) * fund_now[k]

    fv_weights = config.FAIR_VALUE_WEIGHTS_FINANCIAL if financial else config.FAIR_VALUE_WEIGHTS
    components = {k: v for k in ("pe", "ps", "pb", "pfcf") if (v := fv_component(k, strict=False)) is not None}
    parts, weights = {}, {}
    for k, w in fv_weights.items():
        v = fv_component(k, strict=True)
        if v is not None:
            parts[k], weights[k] = v, w
    others = [v for k, v in components.items() if k not in parts]
    if parts and others:
        primary = sum(parts[k] * weights[k] for k in parts) / sum(weights.values())
        ratio = primary / float(np.median(others))
        if not (1 / config.FAIR_VALUE_CONSISTENCY <= ratio <= config.FAIR_VALUE_CONSISTENCY):
            parts, weights = {}, {}  # primary is out of line with every other multiple
    if not parts and components:
        med = float(np.median(list(components.values())))
        parts, weights = {"median": med}, {"median": 1.0}
    gfv, adj = None, 1.0
    if parts:
        base = sum(parts[k] * weights[k] for k in parts) / sum(weights.values())
        if config.FAIR_VALUE_GROWTH_ADJUSTMENT:
            g_hist = g.get(("revenue", 5)) or 0
            adj = clamp((1 + g_hist / 100) / (1 + config.FAIR_VALUE_BASELINE_GROWTH), *config.FAIR_VALUE_ADJ_CLIP)
        gfv = base * adj
    p2gf = div(price, gfv)
    if p2gf is None:
        label, verdict = "", None
    elif p2gf > 1.3:
        label, verdict = "Significantly Overvalued", "over"
    elif p2gf > 1.1:
        label, verdict = "Modestly Overvalued", "over"
    elif p2gf >= 0.9:
        label, verdict = "Fairly Valued", None
    elif p2gf >= 0.7:
        label, verdict = "Modestly Undervalued", "under"
    else:
        label, verdict = "Significantly Undervalued", "under"
    put("fair_value", "Fair Value (Fair Value)", gfv, "$", verdict=verdict, verdict_text=label,
        extra={"components": parts, "adjustment": adj})
    put("price_to_fair_value", "Price-to-Fair Value", p2gf, "x", "low", verdict=verdict, verdict_text=label)
    # Signed gap to fair value, AlphaSpread's convention: (value - price) / value.
    # Positive = undervalued, negative = overvalued.
    put("valuation_score", "Valuation gap", None if not gfv else (gfv - price) / gfv * 100, "%", "high")

    if financial:
        for k in NOT_FOR_FINANCIALS:
            if k in M:
                M[k].value, M[k].note, M[k].verdict, M[k].verdict_text = None, "N/A (financial)", None, ""
        z = None

    # ---- ranks and Quality Score -----------------------------------------------
    stars = scoring.predictability_stars(a_rev_ps[-10:], a_ebitda_ps[-10:])
    put("predictability", "Predictability", stars, "/5", "high")
    strength_inputs = (M["interest_coverage"].value, no_debt, M["debt_to_revenue"].value, z,
                       M["equity_to_asset"].value, M["cash_to_debt"].value)
    put("solvency_score", "Solvency Score", scoring.solvency_score(*strength_inputs), "/100", "high",
        note="Financial Strength inputs on a 0-100 scale")
    ranks = {
        "financial_strength": scoring.financial_strength_rank(*strength_inputs),
        "profitability": scoring.profitability_rank(
            M["operating_margin"].value, pf, margin_trend, years_profitable, stars),
        "growth": scoring.growth_rank(g.get(("revenue", 5)), g.get(("ebitda", 5)), g.get(("revenue", 10))),
        "fair_value": scoring.fair_value_rank(p2gf),
        "momentum": scoring.momentum_rank(m121, m61, beta),
    }
    labels = {"financial_strength": "Financial Strength", "profitability": "Profitability Rank",
              "growth": "Growth Rank", "fair_value": "Fair Value Rank", "momentum": "Momentum Rank"}
    for k, v in ranks.items():
        put(f"rank_{k}", labels[k], v, "/10", "high")
    score = scoring.quality_score(ranks)
    band = (None if score is None else "Highest outperformance potential" if score >= 91 else
            "Good outperformance potential" if score >= 81 else "Average outperformance potential" if score >= 71 else
            "Poor future performance potential" if score >= 51 else "Poor or indeterminate")
    put("quality_score", "Quality Score (Fair Value)", score, "/100", "high", verdict_text=band or "",
        verdict=None if score is None else "under" if score >= 81 else "over" if score < 71 else None)

    # ---- notes --------------------------------------------------------------
    if financial:
        notes.append("Financial company (bank, insurer or REIT): balance-sheet ratios such as Altman Z and "
                     "liquidity are not applicable, and revenue-based metrics should be read with care.")
    for item, d in f.stale_flows.items():
        notes.append(f"{item.replace('_', ' ').capitalize()} is not tagged in the latest 10-Q; "
                     f"using the TTM to {d:%Y-%m-%d}.")
    for item, d in f.stale.items():
        notes.append(f"{item.replace('_', ' ').capitalize()} is not tagged in the latest 10-Q; using the {d:%Y-%m-%d} 10-K value.")
    if int_exp is None and not no_debt:
        notes.append("Interest expense is not reported as a standard XBRL tag; interest coverage and cost of debt are unavailable.")
    if ((today or date.today()) - as_of).days > 120:
        notes.append(f"Latest filing period ends {as_of:%Y-%m-%d}; newer quarters are not yet in SEC companyfacts.")

    # ---- annual table and charts -------------------------------------------
    annual = []
    for i, e in enumerate(ends):
        annual.append({
            "fy": e, "revenue": a_rev[i], "gross_margin": pct(a_gp[i], a_rev[i]),
            "operating_margin": pct(a_op[i], a_rev[i]), "net_income": a_ni[i], "eps": a_eps[i],
            "fcf": a_fcf[i], "dps": a_dps[i], "shares": a_sh[i], "debt": a_debt[i], "equity": a_eq[i],
            "roe": pct(a_ni[i], avg(a_eq[i], a_eq[i - 1] if i else None)) if (a_eq[i] or 0) > 0 else None,
        })

    charts = _charts(c, hist, parts, weights, adj, mult, as_of, annual)
    return Report(ticker.upper(), name, as_of, price, mk.price_date, mcap, ev, M, annual, charts, notes, c, financial)


def _charts(closes, hist, parts, weights, adj, mult, as_of, annual) -> dict:
    start = pd.Timestamp(as_of) - pd.DateOffset(years=10)
    monthly = closes[closes.index >= start].resample("ME").last().dropna()
    gfv_line = None
    if parts:
        fund = hist.daily(monthly.index)
        col = {"pe": "eps", "ps": "revenue", "pb": "book", "pfcf": "fcf"}

        def comp_line(k):
            # A non-positive fundamental (e.g. a loss year) leaves a gap, not a zero value.
            return float(mult[k].dropna().median()) * fund[col[k]].where(fund[col[k]] > 0)

        if "median" in parts:
            lines = [comp_line(k) for k in col if mult[k].dropna().size >= 250 * config.FAIR_VALUE_MIN_YEARS_FALLBACK]
            line = pd.concat(lines, axis=1).median(axis=1, skipna=True) if lines else None
        else:
            line = sum(comp_line(k) * weights[k] for k in parts) / sum(weights.values())
        gfv_line = None if line is None else (line * (adj or 1)).round(2)
    pe = mult["pe"].resample("ME").last()
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in monthly.index],
        "price": [round(float(v), 2) for v in monthly.values],
        "fair_value": None if gfv_line is None else [None if pd.isna(v) else float(v) for v in gfv_line.values],
        "pe_dates": [d.strftime("%Y-%m-%d") for d in pe.index],
        "pe": [None if pd.isna(v) else round(float(v), 2) for v in pe.values],
        "fy": [r["fy"].strftime("%Y") for r in annual],
        "revenue": [r["revenue"] for r in annual],
        "net_income": [r["net_income"] for r in annual],
        "fcf": [r["fcf"] for r in annual],
    }
