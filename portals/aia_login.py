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
    page_debug: dict | None = None,
) -> None:
    """Log into AIA portal. Calls otp_callback() when OTP input is needed."""

    # Step 1: Load welcome page and extract the login link URL
    log.info("Loading AIA welcome page to find login link")
    await page.goto(LOGIN_URL, wait_until="networkidle", timeout=45000)
    await asyncio.sleep(2)
    log.info("Welcome page URL: %s | title: %s", page.url, await page.title())

    # If already on AIA dashboard, skip login
    if "forgerock" not in page.url.lower() and "openam" not in page.url.lower() and "welcome" not in page.url.lower():
        log.info("Already authenticated — skipping login")
        return

    # Click the Login button — use multiple strategies
    login_href = None
    log.info("Clicking Login button on welcome page")
    clicked = False

    # Strategy 1: Playwright text selector
    for locator in [
        page.get_by_role("link", name="Login"),
        page.get_by_role("button", name="Login"),
        page.locator("text=Login").first,
        page.locator("a:has-text('Login')").first,
        page.locator("button:has-text('Login')").first,
    ]:
        try:
            await locator.click(timeout=5000)
            clicked = True
            log.info("Clicked Login via locator")
            break
        except Exception:
            continue

    if not clicked:
        # JS fallback: dispatch click on element with Login text
        log.info("Using JS click fallback")
        await page.evaluate("""
            const els = [...document.querySelectorAll('a,button,span,div')];
            const btn = els.find(e => e.textContent.trim() === 'Login');
            if (btn) btn.click();
            else throw new Error('Login not found. Elements: ' + els.map(e=>e.textContent.trim()).filter(Boolean).slice(0,30).join('|'));
        """)

    # Wait for ForgeRock redirect
    await page.wait_for_url("**/openam**", timeout=20000)
    await asyncio.sleep(2)
    log.info("After login click, URL: %s", page.url)

    # Step 2: ForgeRock — wait for JS-rendered form to appear
    log.info("Waiting for ForgeRock form to render (JS app)...")
    await asyncio.sleep(5)  # Extra wait for Angular/JS rendering
    log.info("Current URL after wait: %s", page.url)

    # Log page content to diagnose what's actually showing
    try:
        body_text = await page.inner_text("body")
        page_html = await page.content()
        log.info("Page URL: %s", page.url)
        log.info("Page body text (first 500): %s", body_text[:500])
        log.info("Page HTML (1000-2000): %s", page_html[1000:2000])
        if page_debug is not None:
            page_debug["url"] = page.url
            page_debug["body_text"] = body_text[:2000]
            page_debug["html_snippet"] = page_html[500:3000]
            page_debug["login_href"] = login_href or ""
    except Exception as e:
        log.warning("Could not get page text: %s", e)

    # Try broad selector — ForgeRock renders inputs dynamically
    username_field = page.locator(
        "input[placeholder='Username'], input[name='IDToken1'], "
        "input[name='username'], input[type='text']:visible, "
        "input[autocomplete='username']"
    ).first
    await username_field.wait_for(state="visible", timeout=20000)
    log.info("ForgeRock form visible, URL: %s", page.url)

    # Click username field and type using keyboard (same method Claude used successfully)
    await username_field.click()
    await page.keyboard.type(username, delay=50)
    log.info("Username typed via keyboard: %s", username)
    await asyncio.sleep(0.5)

    # Tab to password field and type
    await page.keyboard.press("Tab")
    await asyncio.sleep(0.3)
    log.info("Entering password via keyboard")
    pw_field = page.locator("input[placeholder='Password'], input[name='IDToken2'], input[type='password']").first
    await pw_field.wait_for(state="visible", timeout=5000)
    await pw_field.click()
    await page.keyboard.type(password, delay=50)
    log.info("Password typed via keyboard (length: %d)", len(password))
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
