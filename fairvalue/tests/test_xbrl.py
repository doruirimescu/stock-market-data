from datetime import date

import pytest

from fvmodel.fundamentals import Fundamentals
from fvmodel.xbrl import FactBook


def fact(start, end, val, filed, form="10-Q"):
    f = {"end": end, "val": val, "filed": filed, "form": form}
    if start:
        f["start"] = start
    return f


def doc(tag_facts: dict, unit="USD"):
    return {"facts": {"us-gaap": {tag: {"units": {unit: facts}} for tag, facts in tag_facts.items()}}}


# Fiscal year = calendar year. FY2024 = 100, 9M 2024 = 70, 9M 2025 = 80.
REVENUE = [
    fact("2024-01-01", "2024-12-31", 100, "2025-02-01", "10-K"),
    fact("2024-01-01", "2024-09-30", 70, "2024-11-01"),
    fact("2025-01-01", "2025-09-30", 80, "2025-11-01"),
    fact("2025-07-01", "2025-09-30", 30, "2025-11-01"),
    fact("2025-01-01", "2025-06-30", 50, "2025-08-01"),
]


def test_ttm_from_year_to_date():
    book = FactBook([doc({"Revenues": REVENUE})])
    assert book.ttm("Revenues", date(2025, 9, 30)) == pytest.approx(100 + 80 - 70)


def test_ttm_uses_annual_fact_at_year_end():
    book = FactBook([doc({"Revenues": REVENUE})])
    assert book.ttm("Revenues", date(2024, 12, 31)) == 100


def test_latest_filing_wins_for_restatements():
    restated = REVENUE + [fact("2024-01-01", "2024-12-31", 110, "2026-02-01", "10-K")]
    book = FactBook([doc({"Revenues": restated})])
    assert book.annual("Revenues")[date(2024, 12, 31)] == 110


def test_point_in_time_ignores_later_filings():
    book = FactBook([doc({"Revenues": REVENUE})], filed_by=date(2025, 10, 1))
    assert book.ttm("Revenues", date(2025, 9, 30)) is None
    assert book.ttm("Revenues", date(2024, 12, 31)) == 100


def test_quarter_derivation():
    facts = REVENUE + [fact("2025-01-01", "2025-12-31", 112, "2026-02-01", "10-K")]
    book = FactBook([doc({"Revenues": facts})])
    assert book.quarter("Revenues", date(2025, 9, 30)) == 30  # discrete fact
    assert book.quarter("Revenues", date(2025, 12, 31)) == 112 - 80  # Q4 = FY - 9M


def test_split_adjusts_only_pre_split_filings():
    eps = [
        fact("2019-01-01", "2019-12-31", 8.0, "2020-02-01", "10-K"),  # pre-split basis
        fact("2021-01-01", "2021-12-31", 3.0, "2022-02-01", "10-K"),
    ]
    book = FactBook([doc({"EarningsPerShareDiluted": eps}, unit="USD/shares")], splits=[(date(2020, 8, 31), 4.0)])
    annual = book.annual("EarningsPerShareDiluted")
    assert annual[date(2019, 12, 31)] == 2.0
    assert annual[date(2021, 12, 31)] == 3.0


def test_fundamentals_fallbacks_and_derived_items():
    facts = {
        "RevenueFromContractWithCustomerExcludingAssessedTax": [fact("2024-01-01", "2024-12-31", 100, "2025-02-01", "10-K")],
        "CostOfGoodsAndServicesSold": [fact("2024-01-01", "2024-12-31", 60, "2025-02-01", "10-K")],
        "NetIncomeLoss": [fact("2024-01-01", "2024-12-31", 10, "2025-02-01", "10-K")],
        "EarningsPerShareDiluted": [],
        "NetCashProvidedByUsedInOperatingActivities": [fact("2024-01-01", "2024-12-31", 20, "2025-02-01", "10-K")],
        "PaymentsToAcquirePropertyPlantAndEquipment": [fact("2024-01-01", "2024-12-31", 5, "2025-02-01", "10-K")],
        "LongTermDebtNoncurrent": [fact(None, "2024-12-31", 30, "2025-02-01", "10-K")],
        "LongTermDebtCurrent": [fact(None, "2024-12-31", 4, "2025-02-01", "10-K")],
        "CommercialPaper": [fact(None, "2024-12-31", 1, "2025-02-01", "10-K")],
    }
    f = Fundamentals(FactBook([doc(facts)]))
    assert f.as_of == date(2024, 12, 31)
    assert f.ttm("revenue") == 100
    assert f.ttm("gross_profit") == 40  # revenue - cogs when GrossProfit is not tagged
    assert f.ttm("fcf") == 15
    assert f.mrq("total_debt") == 35  # 4 + 1 current + 30 long-term
