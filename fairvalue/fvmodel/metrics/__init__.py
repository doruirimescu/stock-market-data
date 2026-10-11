"""Metric computation: `analyze(ticker)` returns a Report."""

from collections.abc import Iterable, Iterator
from datetime import date

from ..fundamentals import Fundamentals
from ..market import load_market, market_history, splits
from ..sec import is_financial, load_facts, sic_code
from ..xbrl import FactBook
from .compute import Report, compute


def analyze(ticker: str, as_of: date | None = None) -> Report:
    """Analyze `ticker` today, or as it looked on `as_of` (filings and prices known by then)."""
    name, docs = load_facts(ticker)
    book = FactBook(docs, splits(ticker), filed_by=as_of)
    return compute(ticker, name, Fundamentals(book), load_market(ticker, as_of), today=as_of,
                   financial=is_financial(sic_code(ticker)))


def analyze_history(ticker: str, dates: Iterable[date]) -> Iterator[tuple[date, Report | Exception]]:
    """analyze(ticker, d) for every date, loading filings and prices once (for the backtest)."""
    name, docs = load_facts(ticker)
    sp, hist, financial = splits(ticker), market_history(ticker), is_financial(sic_code(ticker))
    for d in dates:
        try:
            book = FactBook(docs, sp, filed_by=d)
            yield d, compute(ticker, name, Fundamentals(book), hist.at(d), today=d, financial=financial)
        except Exception as e:  # no filings or prices yet, too little history...
            yield d, e
