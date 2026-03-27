"""AIA adviser portal extraction module.

Based on the AIA Adviser Portal at adviserretail.aia.com.au.
Policy list page: /au/en/policy.html?inforce=true

Flow: Login → Policies → In-force → Select each adviser code from dropdown → scrape

Table columns on list view:
  - Policy no.
  - Life insured
  - Organisation
  - Updated
  - Status badge (e.g. "Paid to date")
"""

from __future__ import annotations

import logging

from playwright.async_api import BrowserContext, Page

from portals.base import BasePortalExtractor

log = logging.getLogger(__name__)

INFORCE_URL = "https://adviserretail.aia.com.au/au/en/policy.html?inforce=true"
OUT_OF_FORCE_URL = "https://adviserretail.aia.com.au/au/en/policy.html?inforce=false"

# Selectors based on the AIA portal DOM (March 2026)
POLICY_ROW_SELECTOR = "table tbody tr"
NEXT_PAGE_SELECTOR = "button[aria-label='Next page']:not([disabled]), .pagination-next:not(.disabled)"
# The adviser dropdown in the top-right
ADVISER_DROPDOWN_SELECTOR = "[class*='adviser'] select, select[class*='code'], .adviser-dropdown"
ADVISER_DROPDOWN_TRIGGER = "button[class*='adviser'], [class*='adviser'] button, [aria-label*='adviser']"


class AIAExtractor(BasePortalExtractor):
    async def extract(self, context: BrowserContext) -> list[dict]:
        page = context.pages[0] if context.pages else await context.new_page()

        all_policies: list[dict] = []

        # Navigate to in-force policies first
        await page.goto(INFORCE_URL, wait_until="networkidle")

        # Get list of adviser codes from the dropdown
        adviser_codes = await self._get_adviser_codes(page)

        if not adviser_codes:
            # No dropdown found — just extract the current view
            log.info("No adviser dropdown found — extracting current view")
            inforce = await self._extract_table(page, "active")
            all_policies.extend(inforce)
        else:
            # Iterate through each adviser code
            for code_label in adviser_codes:
                log.info("Selecting adviser code: %s", code_label)
                await self._select_adviser_code(page, code_label)

                # Extract in-force for this adviser
                await page.goto(INFORCE_URL, wait_until="networkidle")
                inforce = await self._extract_table(page, "active")
                for p in inforce:
                    p["raw_data"]["adviser_code"] = code_label
                all_policies.extend(inforce)

                # Extract out-of-force for this adviser
                await page.goto(OUT_OF_FORCE_URL, wait_until="networkidle")
                out_of_force = await self._extract_table(page, "lapsed")
                for p in out_of_force:
                    p["raw_data"]["adviser_code"] = code_label
                all_policies.extend(out_of_force)

        log.info("AIA extraction complete — %d total policies", len(all_policies))
        return all_policies

    async def _get_adviser_codes(self, page: Page) -> list[str]:
        """Extract the list of adviser codes from the dropdown."""
        # Try clicking the dropdown trigger to open it
        trigger = await page.query_selector(ADVISER_DROPDOWN_TRIGGER)
        if trigger:
            await trigger.click()
            await page.wait_for_timeout(1000)

        # Look for dropdown options / list items
        # From the screenshot: the dropdown shows items like "AA384 ex-CommInsure", "4C0000217 AIA" etc.
        option_selectors = [
            "[class*='dropdown'] li",
            "[class*='dropdown'] a",
            "[role='option']",
            "[role='listbox'] li",
            "[class*='linked-codes'] li",
            "[class*='menu'] li",
        ]

        codes = []
        for selector in option_selectors:
            items = await page.query_selector_all(selector)
            if items:
                for item in items:
                    text = (await item.inner_text()).strip()
                    # Skip headers/labels like "All linked codes", "Search all linked codes"
                    if text and "search" not in text.lower() and "all linked" not in text.lower():
                        codes.append(text)
                if codes:
                    break

        # Close dropdown if we opened it
        await page.keyboard.press("Escape")
        return codes

    async def _select_adviser_code(self, page: Page, code_label: str) -> None:
        """Select a specific adviser code from the dropdown."""
        trigger = await page.query_selector(ADVISER_DROPDOWN_TRIGGER)
        if trigger:
            await trigger.click()
            await page.wait_for_timeout(500)

        # Click the matching option
        option_selectors = [
            "[class*='dropdown'] li",
            "[class*='dropdown'] a",
            "[role='option']",
            "[role='listbox'] li",
            "[class*='menu'] li",
        ]

        for selector in option_selectors:
            items = await page.query_selector_all(selector)
            for item in items:
                text = (await item.inner_text()).strip()
                if text == code_label:
                    await item.click()
                    await page.wait_for_load_state("networkidle")
                    return

        log.warning("Could not find adviser code option: %s", code_label)

    async def _extract_table(self, page: Page, status_default: str) -> list[dict]:
        """Extract all policies from the current table view, handling pagination."""
        policies: list[dict] = []
        page_num = 0

        while True:
            page_num += 1
            log.info("AIA extraction — page %d", page_num)

            try:
                await page.wait_for_selector(POLICY_ROW_SELECTOR, timeout=15000)
            except Exception:
                log.info("No policy rows found — page may be empty")
                break

            rows = await page.query_selector_all(POLICY_ROW_SELECTOR)

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 3:
                    continue

                texts = [await c.inner_text() for c in cells]

                # Try to find a status badge in the row
                status_el = await row.query_selector(
                    ".badge, .status, [class*='status'], [class*='paid'], [class*='Paid']"
                )
                status_text = ""
                if status_el:
                    status_text = await status_el.inner_text()

                policy = {
                    "policy_number": texts[0].strip() if len(texts) > 0 else "",
                    "client_name": texts[1].strip() if len(texts) > 1 else "",
                    "product_name": texts[2].strip() if len(texts) > 2 else "",
                    "status": self._map_aia_status(status_text, status_default),
                    "premium_amount": "",
                    "premium_frequency": "",
                    "sum_insured": "",
                    "policy_start_date": "",
                    "next_payment_date": texts[3].strip() if len(texts) > 3 else "",
                    "raw_data": {
                        "columns": {f"col_{i}": t.strip() for i, t in enumerate(texts)},
                        "status_badge": status_text.strip(),
                    },
                }
                policies.append(policy)

            # Try pagination
            next_btn = await page.query_selector(NEXT_PAGE_SELECTOR)
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
            else:
                break

        return policies

    @staticmethod
    def _map_aia_status(badge_text: str, default: str) -> str:
        """Map AIA status badges to our enum."""
        lower = badge_text.strip().lower()
        if "paid to date" in lower:
            return "active"
        if "overdue" in lower or "arrears" in lower:
            return "active"
        if "lapsed" in lower:
            return "lapsed"
        if "cancelled" in lower:
            return "cancelled"
        return default
