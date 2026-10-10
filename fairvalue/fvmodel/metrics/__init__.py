"""Metric computation: `analyze(ticker)` returns a Report."""

from datetime import date

from ..fundamentals import Fundamentals
from ..market import load_market, splits
from ..sec import is_financial, load_facts, sic_code
from ..xbrl import FactBook
from .compute import Report, compute


def analyze(ticker: str, as_of: date | None = None) -> Report:
    """Analyze `ticker` today, or as it looked on `as_of` (filings and prices known by then)."""
    name, docs = load_facts(ticker)
    book = FactBook(docs, splits(ticker), filed_by=as_of)
    return compute(ticker, name, Fundamentals(book), load_market(ticker, as_of), today=as_of,
                   financial=is_financial(sic_code(ticker)))
