"""Session management — checks cookie validity, triggers re-auth if needed."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from auth.session_store import SessionStore

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext

log = logging.getLogger(__name__)

session_store = SessionStore()

DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 800


async def ensure_authenticated_context(
    adviser_id: str,
    portal_id: str,
    portal_login_url: str,
    portal_base_url: str,
    secret_ref: str,
    twilio_number: str | None,
    session_ttl_hours: int,
) -> BrowserContext:
    """Return a Playwright browser context with valid session cookies."""
    from playwright.async_api import async_playwright
    from auth.credential_vault import CredentialVault
    from claude.computer_use import claude_login

    credential_vault = CredentialVault()

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)

    cookies = session_store.get(adviser_id, portal_id)

    if cookies:
        log.info("Found cached session for %s:%s", adviser_id, portal_id)
        context = await browser.new_context(
            viewport={"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT}
        )
        await context.add_cookies(cookies)
        page = await context.new_page()
        await page.goto(portal_base_url, wait_until="networkidle")
        if portal_login_url not in page.url:
            log.info("Cached session still valid for %s:%s", adviser_id, portal_id)
            return context
        log.info("Cached session expired for %s:%s — re-authenticating", adviser_id, portal_id)
        await context.close()

    # Re-authenticate
    credentials = credential_vault.get(secret_ref)
    context = await browser.new_context(
        viewport={"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT}
    )
    page = await context.new_page()

    new_cookies = await claude_login(
        page=page,
        portal_id=portal_id,
        portal_login_url=portal_login_url,
        credentials=credentials,
        twilio_number=twilio_number,
    )

    session_store.set(adviser_id, portal_id, new_cookies, ttl_hours=session_ttl_hours)
    log.info("Re-authenticated %s:%s — session stored", adviser_id, portal_id)
    return context
