"""Resolution Life adviser portal extraction module."""

from __future__ import annotations

import logging

from playwright.async_api import BrowserContext

from portals.base import BasePortalExtractor

log = logging.getLogger(__name__)

POLICY_LIST_URL = "https://adviser.resolutionlife.com.au/policies"
POLICY_ROW_SELECTOR = "table.policy-list tbody tr"
NEXT_PAGE_SELECTOR = "[aria-label='Next']:not([disabled])"


class ResolutionExtractor(BasePortalExtractor):
    async def extract(self, context: BrowserContext) -> list[dict]:
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(POLICY_LIST_URL, wait_until="networkidle")

        policies: list[dict] = []

        while True:
            await page.wait_for_selector(POLICY_ROW_SELECTOR, timeout=15000)
            rows = await page.query_selector_all(POLICY_ROW_SELECTOR)

            for row in rows:
                cells = await row.query_selector_all("td")
                if len(cells) < 7:
                    continue
                texts = [await c.inner_text() for c in cells]
                policies.append({
                    "policy_number": texts[0].strip(),
                    "client_name": texts[1].strip(),
                    "product_name": texts[2].strip(),
                    "status": self.normalise_status(texts[3]),
                    "premium_amount": str(self.parse_currency(texts[4])),
                    "premium_frequency": self.normalise_frequency(texts[5]),
                    "sum_insured": str(self.parse_currency(texts[6])),
                    "policy_start_date": texts[7].strip() if len(texts) > 7 else "",
                    "next_payment_date": texts[8].strip() if len(texts) > 8 else "",
                    "raw_data": {f"col_{i}": t.strip() for i, t in enumerate(texts)},
                })

            next_btn = await page.query_selector(NEXT_PAGE_SELECTOR)
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
            else:
                break

        log.info("Resolution Life extraction complete — %d policies", len(policies))
        return policies
