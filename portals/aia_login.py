"""Direct Playwright login for AIA adviser portal (no Claude computer use).

ForgeRock SSO flow:
  1. AIA welcome page → click Login button
  2. ForgeRock page — may be one-step (user+pass) or two-step (user → Next → pass)
  3. MFA screen → mobile radio already selected → click Next to send SMS
  4. OTP entry → type code → click Submit
  5. Redirected back to AIA dashboard
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

log = logging.getLogger(__name__)

LOGIN_URL = "https://adviserretail.aia.com.au/au/en/welcome.html"


async def _click_submit(page: Page) -> None:
    """Click the primary submit/next button on a ForgeRock page."""
    for selector in [
        "input[type='submit']",
        "button[type='submit']",
        "button.btn-primary",
        "button:has-text('Next')",
        "button:has-text('Sign In')",
        "button:has-text('Login')",
        "button:has-text('Continue')",
    ]:
        try:
            el = page.locator(selector).first
            await el.click(timeout=3000)
            return
        except Exception:
            continue
    # Last resort: press Enter
    await page.keyboard.press("Enter")


async def aia_login(
    page: Page,
    username: str,
    password: str,
    otp_callback,  # async callable that returns the OTP code string
) -> None:
    """Log into AIA portal. Calls otp_callback() when OTP input is needed."""

    # Navigate directly to the policy page — AIA will redirect to ForgeRock if not logged in
    log.info("Navigating to AIA policy page (will redirect to ForgeRock login)")
    await page.goto(
        "https://adviserretail.aia.com.au/au/en/policy.html?inforce=true",
        wait_until="domcontentloaded",
        timeout=30000,
    )
    await asyncio.sleep(3)
    log.info("After navigate, URL: %s", page.url)

    # If already on AIA (not ForgeRock), we're already logged in
    if "forgerock" not in page.url.lower() and "openam" not in page.url.lower():
        log.info("Already authenticated — skipping login")
        return

    log.info("On ForgeRock login page")

    # Step 2: ForgeRock — wait for form to load then fill credentials
    log.info("Waiting for ForgeRock form...")
    # Wait for the username field to appear
    username_field = page.locator("input[placeholder='Username'], input[name='IDToken1'], input[name='username']").first
    await username_field.wait_for(state="visible", timeout=15000)
    log.info("ForgeRock form visible, URL: %s", page.url)

    # Clear and fill username
    await username_field.triple_click()
    await username_field.fill(username)
    log.info("Username entered: %s", username)
    await asyncio.sleep(0.5)

    # Step 3: Enter password — use type() to handle special chars reliably
    log.info("Entering password")
    pw_field = page.locator("input[placeholder='Password'], input[name='IDToken2'], input[type='password']").first
    await pw_field.wait_for(state="visible", timeout=5000)
    await pw_field.triple_click()
    await pw_field.fill(password)
    log.info("Password entered (length: %d)", len(password))
    await asyncio.sleep(0.5)

    # Step 4: Click Next button
    log.info("Clicking Next")
    await _click_submit(page)
    await asyncio.sleep(4)
    log.info("After Next, URL: %s", page.url)

    # Check for login error
    try:
        err = page.locator(".alert-danger, [class*='error'], [class*='alert']").first
        err_text = await err.inner_text(timeout=2000)
        if err_text and len(err_text.strip()) > 5:
            raise RuntimeError(f"AIA login error: {err_text.strip()}")
    except RuntimeError:
        raise
    except Exception:
        pass

    # Step 5: MFA selection screen — select mobile and click Next to send SMS
    if "forgerock" in page.url.lower():
        log.info("Still on ForgeRock — checking for MFA selection screen")
        page_text = await page.inner_text("body")
        log.info("Page text preview: %s", page_text[:300])

        if "how would you like" in page_text.lower() or "verify" in page_text.lower() or "mobile" in page_text.lower():
            log.info("MFA selection screen detected — selecting mobile and clicking Next")
            try:
                # Select the first radio (mobile phone)
                radio = page.locator("input[type='radio']").first
                await radio.check(timeout=5000)
            except Exception:
                pass
            await asyncio.sleep(0.5)
            await _click_submit(page)
            await asyncio.sleep(4)
            log.info("After MFA Next, URL: %s", page.url)

    # Step 6: OTP entry screen
    if "forgerock" in page.url.lower():
        page_text = await page.inner_text("body")
        log.info("ForgeRock page text: %s", page_text[:300])

        if any(kw in page_text.lower() for kw in ["one-time", "verification code", "otp", "passcode", "enter the code"]):
            log.info("OTP entry screen — waiting for code")
            otp_code = await otp_callback()
            log.info("Got OTP code, entering")
            otp_field = page.locator("input[name='IDToken1'], input[type='text'], input[autocomplete='one-time-code']").first
            await otp_field.fill(otp_code, timeout=10000)
            await asyncio.sleep(0.5)
            await _click_submit(page)
            await asyncio.sleep(5)
            log.info("After OTP submit, URL: %s", page.url)

    log.info("Login complete, final URL: %s", page.url)
    if "forgerock" in page.url.lower() or "welcome" in page.url:
        page_text = await page.inner_text("body")
        raise RuntimeError(f"Login incomplete at: {page.url} | {page_text[:200]}")
