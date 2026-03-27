"""Abstract base class for portal extraction modules."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from decimal import Decimal

from playwright.async_api import BrowserContext, Page


class BasePortalExtractor(ABC):
    """Each portal implements extract() which returns a list of raw policy dicts."""

    @abstractmethod
    async def extract(self, context: BrowserContext) -> list[dict]:
        """Navigate the authenticated portal and return raw policy data.

        Each dict should map to the PolicySyncRecord fields:
            policy_number, client_name, product_name, status,
            premium_amount, premium_frequency, sum_insured,
            policy_start_date, next_payment_date, raw_data
        """

    # ── Helpers available to all extractors ───────────────────────────

    @staticmethod
    async def safe_text(page: Page, selector: str, default: str = "") -> str:
        """Get inner text of a selector, returning default if not found."""
        el = await page.query_selector(selector)
        if el is None:
            return default
        return (await el.inner_text()).strip()

    @staticmethod
    def parse_currency(text: str) -> Decimal:
        """Parse '$1,234.56' → Decimal('1234.56')."""
        cleaned = re.sub(r"[^\d.]", "", text)
        return Decimal(cleaned) if cleaned else Decimal("0")

    @staticmethod
    def normalise_status(raw: str) -> str:
        """Map portal-specific status strings to our enum values."""
        raw_lower = raw.strip().lower()
        mapping = {
            "active": "active",
            "in force": "active",
            "inforce": "active",
            "lapsed": "lapsed",
            "cancelled": "cancelled",
            "pending": "pending",
            "applied": "pending",
        }
        return mapping.get(raw_lower, "active")

    @staticmethod
    def normalise_frequency(raw: str) -> str:
        """Map frequency strings to our enum values."""
        raw_lower = raw.strip().lower()
        if "month" in raw_lower:
            return "monthly"
        if "annual" in raw_lower or "year" in raw_lower:
            return "annual"
        return "monthly"
