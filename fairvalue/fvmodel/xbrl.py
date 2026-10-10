"""Turn SEC companyfacts JSON into clean period series.

Each XBRL fact is either a duration (income/cash-flow item with start and end)
or an instant (balance-sheet item with only an end date). The same period is
usually reported several times (the original filing, then as a comparative in
later filings); we keep the most recently filed value, which carries any
restatement.

Trailing twelve months (TTM) for a duration item ending at E is:
  * the annual fact ending at E, if there is one; otherwise
  * prior fiscal year + year-to-date at E - same year-to-date one year earlier.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

UNIT_PREFERENCE = ("USD", "USD/shares", "shares", "pure")
ANNUAL_DAYS = (350, 380)


@dataclass(frozen=True)
class Fact:
    start: date | None
    end: date
    val: float
    filed: date
    form: str
    unit: str = "USD"

    @property
    def days(self) -> int:
        return (self.end - self.start).days if self.start else 0


def _d(s: str) -> date:
    return date.fromisoformat(s)


def _near(a: date, b: date, tol: int) -> bool:
    return abs((a - b).days) <= tol


def _split_adjust(f: Fact, splits: list[tuple[date, float]]) -> Fact:
    if f.unit not in ("shares", "USD/shares"):
        return f
    factor = 1.0
    for when, ratio in splits:
        if f.filed < when:  # reported on the pre-split share basis
            factor *= ratio
    if factor == 1.0:
        return f
    val = f.val * factor if f.unit == "shares" else f.val / factor
    return Fact(f.start, f.end, val, f.filed, f.form, f.unit)


class FactBook:
    """Deduplicated facts for one company, possibly merged across CIKs."""

    def __init__(self, docs: list[dict], splits: list[tuple[date, float]] | None = None,
                 filed_by: date | None = None):
        """`splits`: (effective date, ratio) pairs, e.g. (2020-08-31, 4.0).

        Per-share values and share counts in filings made before a split are
        restated to today's share basis, since old periods are never re-filed.
        `filed_by`: ignore facts filed after this date (point-in-time view).
        """
        self._facts: dict[str, dict[tuple, Fact]] = {}
        for doc in docs:
            for taxonomy, concepts in doc.get("facts", {}).items():
                for tag, body in concepts.items():
                    unit = next((u for u in UNIT_PREFERENCE if u in body["units"]), None)
                    if unit is None:
                        continue
                    key = tag if taxonomy == "us-gaap" else f"{taxonomy}:{tag}"
                    bucket = self._facts.setdefault(key, {})
                    for raw in body["units"][unit]:
                        f = Fact(
                            _d(raw["start"]) if "start" in raw else None,
                            _d(raw["end"]),
                            float(raw["val"]),
                            _d(raw["filed"]),
                            raw.get("form", ""),
                            unit,
                        )
                        if filed_by and f.filed > filed_by:
                            continue
                        f = _split_adjust(f, splits or [])
                        k = (f.start, f.end)
                        if k not in bucket or f.filed > bucket[k].filed:
                            bucket[k] = f

    def has(self, tag: str) -> bool:
        return tag in self._facts

    def facts(self, tag: str) -> list[Fact]:
        return list(self._facts.get(tag, {}).values())

    # ---- durations -------------------------------------------------------

    def annual(self, tag: str) -> dict[date, float]:
        """Fiscal-year values keyed by period end."""
        lo, hi = ANNUAL_DAYS
        return {f.end: f.val for f in self.facts(tag) if f.start and lo <= f.days <= hi}

    def ttm(self, tag: str, end: date) -> float | None:
        durs = [f for f in self.facts(tag) if f.start]
        lo, hi = ANNUAL_DAYS
        for f in durs:
            if f.end == end and lo <= f.days <= hi:
                return f.val
        ytds = sorted((f for f in durs if f.end == end and f.days < lo), key=lambda f: -f.days)
        for ytd in ytds:
            prior_fy = next(
                (f for f in durs if lo <= f.days <= hi and _near(f.end, ytd.start - timedelta(days=1), 7)),
                None,
            )
            prior_ytd = next(
                (
                    f
                    for f in durs
                    if _near(f.end, end - timedelta(days=365), 10) and abs(f.days - ytd.days) <= 10
                ),
                None,
            )
            if prior_fy and prior_ytd:
                return prior_fy.val + ytd.val - prior_ytd.val
        return None

    def quarter(self, tag: str, end: date) -> float | None:
        """Discrete three-month value ending at `end`; Q4 is derived as FY - 9M YTD."""
        durs = [f for f in self.facts(tag) if f.start]
        for f in durs:
            if f.end == end and 80 <= f.days <= 100:
                return f.val
        lo, hi = ANNUAL_DAYS
        for fy in (f for f in durs if f.end == end and lo <= f.days <= hi):
            for ytd in durs:
                if ytd.start == fy.start and 250 <= ytd.days <= 290:
                    return fy.val - ytd.val
        # Q2/Q3 from consecutive year-to-date facts with the same start
        for ytd in (f for f in durs if f.end == end and 150 <= f.days <= 290):
            for prior in durs:
                if prior.start == ytd.start and 60 <= ytd.days - prior.days <= 110:
                    return ytd.val - prior.val
        return None

    def latest_quarter(self, tag: str, end: date) -> float | None:
        """Single-quarter value ending at `end` (e.g. weighted shares of the quarter)."""
        for f in self.facts(tag):
            if f.start and f.end == end and 80 <= f.days <= 100:
                return f.val
        return None

    # ---- instants --------------------------------------------------------

    def instants(self, tag: str) -> dict[date, float]:
        return {f.end: f.val for f in self.facts(tag) if f.start is None}

    def instant(self, tag: str, end: date, tol: int = 7) -> float | None:
        best = None
        for d, v in self.instants(tag).items():
            if _near(d, end, tol) and (best is None or abs((d - end).days) < abs((best[0] - end).days)):
                best = (d, v)
        return best[1] if best else None

    def latest_instant(self, tag: str) -> tuple[date, float] | None:
        series = self.instants(tag)
        if not series:
            return None
        d = max(series)
        return d, series[d]

    # ---- calendar --------------------------------------------------------

    def period_ends(self, tags: tuple[str, ...]) -> list[date]:
        """All report period ends (10-K and 10-Q) seen on the given anchor tags."""
        ends = set()
        for tag in tags:
            ends.update(f.end for f in self.facts(tag) if f.start and f.form.startswith(("10-K", "10-Q", "20-F")))
        return sorted(ends)

    def fiscal_year_ends(self, tags: tuple[str, ...]) -> list[date]:
        ends = set()
        for tag in tags:
            ends.update(self.annual(tag))
        return sorted(ends)
