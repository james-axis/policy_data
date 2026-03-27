"""Test endpoint — runs AIA sync directly without Celery. For development only."""

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel

from auth.twilio_otp import OTPStore
from workers.crm_writer import upsert_policies

log = logging.getLogger(__name__)
router = APIRouter()

# In-memory state for the test run
_test_state = {
    "status": "idle",
    "message": "",
    "policies_count": 0,
    "output_file": "",
    "error": "",
    "debug_url": "",
}


class OTPInput(BaseModel):
    code: str


@router.get("/status")
async def test_status():
    """Check the status of the current test sync."""
    return _test_state


@router.post("/otp")
async def submit_otp(otp: OTPInput):
    """Manually submit an OTP code for the test sync."""
    otp_store = OTPStore()
    phone = os.getenv("AIA_PHONE", "+61433337000")
    otp_store.store(phone, otp.code)
    return {"status": "stored", "phone": phone}


@router.get("/debug-url")
async def test_debug_url():
    """Return the Browserbase live debug viewer URL for the current session."""
    return {"debug_url": _test_state.get("debug_url", "")}


@router.post("/run-aia")
async def run_aia_test(background_tasks: BackgroundTasks):
    """Kick off an AIA sync in the background. Check /test/status for progress."""
    if _test_state["status"] == "running":
        return {"error": "A test sync is already running"}

    _test_state.update(
        status="running",
        message="Starting AIA sync...",
        error="",
        output_file="",
        debug_url="",
    )
    background_tasks.add_task(_run_aia_sync)
    return {
        "status": "started",
        "next": "Check /test/status for progress. Submit OTP at /test/otp if needed.",
    }


async def _run_aia_sync():
    """The actual sync logic — runs as a background task."""
    from playwright.async_api import async_playwright
    from claude.computer_use import claude_login, DISPLAY_WIDTH, DISPLAY_HEIGHT
    from portals.aia import AIAExtractor
    from auth.session_store import SessionStore
    from browser.browserbase import create_session, get_debug_url

    session_store = SessionStore()
    username = os.getenv("AIA_USERNAME", "")
    password = os.getenv("AIA_PASSWORD", "")
    phone = os.getenv("AIA_PHONE")

    pw = None
    browser = None

    try:
        # Step 1: Create Browserbase session (residential IP, avoids portal blocks)
        _test_state["message"] = "Creating Browserbase session..."
        bb_session_id, cdp_url = await create_session(proxy=True)

        try:
            debug_url = await get_debug_url(bb_session_id)
            _test_state["debug_url"] = debug_url
            log.info("Browserbase debug viewer: %s", debug_url)
        except Exception:
            pass  # debug URL is non-critical

        # Step 2: Connect Playwright to Browserbase
        _test_state["message"] = "Connecting to browser..."
        pw = await async_playwright().start()
        browser = await pw.chromium.connect_over_cdp(cdp_url)

        context = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
            ignore_https_errors=True,
        )
        page = await context.new_page()

        # Step 3: Check for cached session
        cookies = session_store.get("test_adviser", "aia")
        if cookies:
            _test_state["message"] = "Found cached session — testing validity..."
            await context.add_cookies(cookies)
            await page.goto(
                "https://adviserretail.aia.com.au/au/en/policy.html?inforce=true",
                wait_until="domcontentloaded",
                timeout=30000,
            )

            if "welcome" not in page.url and "forgerock" not in page.url:
                _test_state["message"] = "Cached session valid — skipping login"
            else:
                _test_state["message"] = "Cached session expired — re-authenticating..."
                cookies = None

        # Step 4: Login if needed
        if not cookies:
            _test_state["message"] = (
                "Starting Claude login... (submit OTP at /test/otp when prompted)"
            )
            new_cookies = await claude_login(
                page=page,
                portal_id="aia",
                portal_login_url="https://adviserretail.aia.com.au/au/en/welcome.html",
                credentials={"username": username, "password": password},
                twilio_number=phone,
            )
            session_store.set("test_adviser", "aia", new_cookies, ttl_hours=12)
            _test_state["message"] = "Login successful — extracting policies..."

        # Step 5: Extract policies
        _test_state["message"] = "Extracting policies from AIA portal..."
        extractor = AIAExtractor()
        policies = await extractor.extract(context)

        # Step 6: Write to Excel
        _test_state["message"] = "Writing Excel file..."
        output_path = upsert_policies("test_adviser", "aia", policies)

        _test_state.update(
            status="complete",
            message=f"Done! {len(policies)} policies extracted.",
            policies_count=len(policies),
            output_file=output_path,
        )

    except Exception as e:
        log.exception("Test AIA sync failed")
        _test_state.update(
            status="failed",
            message=str(e),
            error=str(e),
        )
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        if pw:
            try:
                await pw.stop()
            except Exception:
                pass
