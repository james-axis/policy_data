"""Tests for base portal extractor helpers."""

from decimal import Decimal

from portals.base import BasePortalExtractor


def test_parse_currency():
    assert BasePortalExtractor.parse_currency("$1,234.56") == Decimal("1234.56")
    assert BasePortalExtractor.parse_currency("$0.00") == Decimal("0.00")
    assert BasePortalExtractor.parse_currency("") == Decimal("0")
    assert BasePortalExtractor.parse_currency("$500,000") == Decimal("500000")


def test_normalise_status():
    assert BasePortalExtractor.normalise_status("Active") == "active"
    assert BasePortalExtractor.normalise_status("In Force") == "active"
    assert BasePortalExtractor.normalise_status("Lapsed") == "lapsed"
    assert BasePortalExtractor.normalise_status("Cancelled") == "cancelled"
    assert BasePortalExtractor.normalise_status("Pending") == "pending"
    assert BasePortalExtractor.normalise_status("Unknown") == "active"  # default


def test_normalise_frequency():
    assert BasePortalExtractor.normalise_frequency("Monthly") == "monthly"
    assert BasePortalExtractor.normalise_frequency("Annual") == "annual"
    assert BasePortalExtractor.normalise_frequency("Yearly") == "annual"
    assert BasePortalExtractor.normalise_frequency("Other") == "monthly"  # default
