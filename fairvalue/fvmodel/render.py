"""Render reports to static HTML pages in the Nexus style."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from .metrics.base import Metric


def money(v) -> str:
    if v is None:
        return "–"
    a = abs(v)
    for div_, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div_:
            return f"{'-' if v < 0 else ''}${a / div_:.2f}{suffix}"
    return f"{'-' if v < 0 else ''}${a:,.2f}"


def count(v) -> str:
    return "–" if v is None else money(v).replace("$", "")


def num(v) -> str:
    return "–" if v is None else f"{v:,.2f}"


def pctf(v) -> str:
    return "–" if v is None else f"{v:.1f}%"


def fmt(m: Metric) -> str:
    if not m.ok:
        return m.note if m.note in ("No debt", "At loss", "N/A (financial)") else "–"
    v, u = m.value, m.unit
    if u == "%":
        return f"{v:.2f}%"
    if u == "$":
        return money(v) if abs(v) >= 1e6 else f"{'-' if v < 0 else ''}${abs(v):,.2f}"
    if u in ("/10", "/9", "/100"):
        return f"{int(v)}"
    if u == "/5":
        return f"{v:.1f}"
    if u == "days":
        return f"{v:.1f}"
    if u == "pp/yr":
        return f"{v:+.2f} pp/yr"
    return f"{v:.2f}"


def _env() -> Environment:
    env = Environment(loader=PackageLoader("fvmodel", "templates"), autoescape=select_autoescape(["j2", "html"]))
    env.globals.update(fmt=fmt, money=money, num=num, pctf=pctf, count=count, generated=date.today().strftime("%d %b %Y"))
    return env


def summary_row(r) -> dict:
    """What the index needs about one stock, stored next to its page."""
    p2 = r.metrics["price_to_fair_value"]
    return {
        "ticker": r.ticker, "name": r.name, "price": f"{r.price:.2f}", "as_of": r.as_of.isoformat(),
        "fair_value": fmt(r.metrics["fair_value"]), "verdict": p2.verdict or "", "verdict_text": p2.verdict_text,
        "quality_score": fmt(r.metrics["quality_score"]), "pe": fmt(r.metrics["pe_ttm"]), "roic": fmt(r.metrics["roic"]),
        "f_score": fmt(r.metrics["piotroski_f"]), "z_score": fmt(r.metrics["altman_z"]),
    }


def render_site(reports, out: Path, comparison: dict | None = None) -> None:
    """Write stock pages, rebuild the index from every stock analyzed so far, and the validation page."""
    env = _env()
    stocks = out / "stocks"
    stocks.mkdir(parents=True, exist_ok=True)
    for r in reports:
        html = env.get_template("stock.html.j2").render(
            r=r, root="../", nav="stocks", charts_json=Markup(json.dumps(r.charts).replace("</", "<\\/")))
        (stocks / f"{r.ticker}.html").write_text(html)
        (stocks / f"{r.ticker}.json").write_text(json.dumps(summary_row(r)))
    rows = sorted((json.loads(p.read_text()) for p in stocks.glob("*.json")), key=lambda x: x["ticker"])
    (out / "index.html").write_text(env.get_template("index.html.j2").render(rows=rows, root="", nav="stocks"))
    if comparison:
        labels = {}
        for r in reports:
            labels.update({k: m.label for k, m in r.metrics.items()})
        html = env.get_template("validation.html.j2").render(root="", nav="validation", labels=labels, **comparison)
        (out / "validation.html").write_text(html)
