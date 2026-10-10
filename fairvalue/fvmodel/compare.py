"""Compare our metrics with values the reference provider published (reference/benchmark_reference.json).

Every the reference provider value carries an as-of date. We re-run the analysis point-in-time
for that date (only filings made and prices known by then), so a newer quarter
or a later price move does not show up as a methodology difference.
A month-only date ("2026-06") names the fiscal period behind a quarterly
figure; we evaluate it 75 days after month end, once that quarter is filed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import pandas as pd

from .metrics.compute import Report

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "benchmark_reference.json"

ABS_TOL = {  # (match, close) absolute tolerances for scores
    "quality_score": (5, 10),
    "piotroski_f": (1, 2),
    "beneish_m": (0.25, 0.5),
    "altman_z": (0.5, 1.5),
}
RANK_TOL = (1, 2)
REL_TOL = (0.05, 0.15)
FILING_LAG_DAYS = 75


@dataclass
class Row:
    ticker: str
    metric: str
    label: str
    ours: float | None
    theirs: float
    as_of: str
    source: str
    diff: float | None  # relative (fraction) or absolute for scores
    diff_kind: str  # "rel" | "abs"
    status: str  # "match" | "close" | "differs" | "missing"
    note: str = ""


def load_reference(path: Path = REFERENCE) -> dict:
    return json.loads(path.read_text())["stocks"] if path.exists() else {}


def evaluation_date(as_of: str, today: date | None = None) -> date:
    today = today or date.today()
    if len(as_of) == 7:  # YYYY-MM: fiscal period of a quarterly figure
        month_end = (pd.Timestamp(as_of) + pd.offsets.MonthEnd(0)).date()
        return min(today, month_end + timedelta(days=FILING_LAG_DAYS))
    return min(today, date.fromisoformat(as_of[:10]))


def compare_ticker(ticker: str, ref: dict, analyze_at: Callable[[str, date], Report]) -> list[Row]:
    rows = []
    for key, ent in ref.get("metrics", {}).items():
        theirs = float(ent["value"])
        as_of = ent.get("as_of", "")
        when = evaluation_date(as_of)
        r = analyze_at(ticker, when)
        ours_key = f"{key}_quarterly" if ent.get("basis") == "annualized quarter" else key
        ours = r.m(ours_key)
        label = r.metrics[key].label if key in r.metrics else key
        note = f"ours as of {when}, fundamentals to {r.as_of}"
        if ours_key != key:
            note += "; both annualized from the latest quarter"
        if ours is None:
            rows.append(Row(ticker, key, label, None, theirs, as_of, ent.get("source", ""), None, "rel", "missing", note))
            continue
        if key.startswith("rank_") or key in ABS_TOL:
            tol = RANK_TOL if key.startswith("rank_") else ABS_TOL[key]
            d, kind = ours - theirs, "abs"
            status = "match" if abs(d) <= tol[0] else "close" if abs(d) <= tol[1] else "differs"
        else:
            d, kind = (ours - theirs) / abs(theirs) if theirs else None, "rel"
            status = ("missing" if d is None else "match" if abs(d) <= REL_TOL[0]
                      else "close" if abs(d) <= REL_TOL[1] else "differs")
        rows.append(Row(ticker, key, label, ours, theirs, as_of, ent.get("source", ""), d, kind, status, note))
    return rows


def summarize(rows: list[Row]) -> dict:
    by_status = {s: sum(r.status == s for r in rows) for s in ("match", "close", "differs", "missing")}
    by_metric = {}
    for r in rows:
        b = by_metric.setdefault(r.metric, {"n": 0, "match": 0, "close": 0, "differs": 0, "missing": 0, "abs_rel": []})
        b["n"] += 1
        b[r.status] += 1
        if r.diff is not None and r.diff_kind == "rel":
            b["abs_rel"].append(abs(r.diff))
    for b in by_metric.values():
        vals = sorted(b.pop("abs_rel"))
        b["median_abs_rel_diff"] = vals[len(vals) // 2] if vals else None
    return {"total": len(rows), "by_status": by_status, "by_metric": by_metric}
