"""Direct Playwright login for AIA adviser portal (no Claude computer use).

ForgeRock SSO flow:
  1. AIA welcome page → click Login button
  2. ForgeRock page → enter username + password → click Sign In
  3. MFA screen → mobile already selected → click Next to trigger SMS
  4. OTP entry screen → type code → click Submit
  5. Redirected back to AIA dashboard
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

log = logging.getLogger(__name__)

LOGIN_URL = "https://adviserretail.aia.com.au/au/en/welcome.html"
DASHBOARD_URL = "https://adviserretail.aia.com.au/au/en/dashboard.html"


async def aia_login(
    page: Page,
    username: str,
    password: str,
    otp_callback,  # async callable that returns the OTP code string
) -> None:
    """Log into AIA portal. Calls otp_callback() when OTP input is needed."""

    log.info("Navigating to AIA welcome page")
    await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(2)

    # Step 1: Click the Login button on the welcome page
    log.info("Clicking Login button, page title: %s url: %s", await page.title(), page.url)
    # Try multiple strategies to find the Login button
    clicked = False
    for selector in [
        "a.btn-login", "button.btn-login", ".btn-login",
        "a[class*='login']", "button[class*='login']",
        "a[href*='login']", "a[href*='Login']",
        ".login-button", "#loginButton",
    ]:
        try:
            el = page.locator(selector).first
            await el.click(timeout=3000)
            clicked = True
            log.info("Clicked login button via selector: %s", selector)
            break
        except Exception:
            continue

    if not clicked:
        # JS fallback: click the first element whose text contains "Login"
        log.info("Using JS fallback to find Login button")
        await page.evaluate("""
            const els = Array.from(document.querySelectorAll('a, button'));
            const btn = els.find(e => e.textContent.trim().toLowerCase() === 'login' || e.textContent.trim().toLowerCase() === 'log in');
            if (btn) btn.click();
            else throw new Error('Login button not found in DOM');
        """)
    await asyncio.sleep(3)

    log.info("On ForgeRock page: %s", page.url)

    # Step 2: Enter username
    log.info("Entering username")
    username_field = page.locator("input[name='IDToken1'], input[type='text'], input[type='email']").first
    await username_field.fill(username, timeout=10000)
    await asyncio.sleep(0.5)

    # Step 3: Enter password
    log.info("Entering password")
    password_field = page.locator("input[name='IDToken2'], input[type='password']").first
    await password_field.fill(password, timeout=10000)
    await asyncio.sleep(0.5)

    # Step 4: Click Sign In button
    log.info("Clicking Sign In")
    try:
        sign_in = page.locator("input[type='submit'], button[type='submit']").first
        await sign_in.click(timeout=10000)
    except Exception:
        await page.keyboard.press("Enter")
    await asyncio.sleep(3)

    log.info("After sign in, URL: %s", page.url)

    # Check for login error
    error = page.locator(".alert-danger, .error-message, [class*='error']").first
    try:
        err_text = await error.inner_text(timeout=2000)
        if err_text:
            raise RuntimeError(f"AIA login error: {err_text.strip()}")
    except Exception as e:
        if "RuntimeError" in str(type(e)):
            raise
        pass  # No error element, that's fine

    # Step 5: MFA selection screen — click Next to send SMS
    if "forgerock" in page.url:
        log.info("On MFA selection screen")
        # Make sure mobile is selected
        try:
            mobile_radio = page.locator("input[type='radio']").first
            await mobile_radio.check(timeout=5000)
        except Exception:
            pass

        # Click Next/Submit to trigger SMS
        try:
            next_btn = page.locator("input[type='submit'], button[type='submit'], button:has-text('Next'), button:has-text('Submit')").first
            await next_btn.click(timeout=10000)
        except Exception:
            await page.keyboard.press("Enter")
        await asyncio.sleep(3)
        log.info("Clicked Next on MFA screen, URL: %s", page.url)

    # Step 6: OTP entry screen
    if "forgerock" in page.url:
        log.info("Waiting for OTP code via callback")
        otp_code = await otp_callback()
        log.info("Got OTP, entering it")

        otp_field = page.locator("input[name='IDToken1'], input[type='text'], input[autocomplete='one-time-code']").first
        await otp_field.fill(otp_code, timeout=10000)
        await asyncio.sleep(0.5)

        try:
            submit = page.locator("input[type='submit'], button[type='submit']").first
            await submit.click(timeout=10000)
        except Exception:
            await page.keyboard.press("Enter")
        await asyncio.sleep(5)

    log.info("Login complete, final URL: %s", page.url)

    if "forgerock" in page.url or "welcome" in page.url:
        raise RuntimeError(f"Login did not complete, still on: {page.url}")
