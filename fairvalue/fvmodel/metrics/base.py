"""Metric record and small numeric helpers shared by the metric modules."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Metric:
    key: str
    label: str
    value: float | None
    unit: str = ""  # "%", "x", "$", "" (plain number), "/10", "/9", "/100"
    better: str | None = None  # "high" | "low" | None
    note: str = ""
    hist: dict | None = None  # range_stats() of the metric's own 10-year history
    verdict: str | None = None  # "under" | "over" | None: teal/orange label
    verdict_text: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.value is not None and not (isinstance(self.value, float) and math.isnan(self.value))


def div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def pct(a, b):
    v = div(a, b)
    return None if v is None else v * 100


def avg(*vals):
    vals = [v for v in vals if v is not None]
    return sum(vals) / len(vals) if vals else None


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def cagr(series: list[float | None], years: int) -> float | None:
    """Compound growth (%) from series[-1-years] to series[-1]; needs positive endpoints."""
    if len(series) <= years:
        return None
    start, end = series[-1 - years], series[-1]
    if start is None or end is None or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100
