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
    # Store under both the phone number and "manual" so either key works
    otp_store.store(phone, otp.code)
    otp_store.store("manual", otp.code)
    return {"status": "stored", "phone": phone, "code_received": otp.code}


@router.get("/screenshots")
async def list_screenshots():
    """List saved debug screenshots from the last login attempt."""
    from pathlib import Path
    debug_dir = Path("/tmp/login_aia")
    if not debug_dir.exists():
        return {"files": []}
    files = sorted(debug_dir.glob("*.jpg"))
    return {"files": [f.name for f in files], "count": len(files)}


@router.get("/screenshot/{filename}")
async def get_screenshot(filename: str):
    """Serve a saved debug screenshot."""
    from pathlib import Path
    from fastapi.responses import FileResponse
    path = Path("/tmp/login_aia") / filename
    if not path.exists() or not path.suffix == ".jpg":
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Screenshot not found")
    return FileResponse(path, media_type="image/jpeg")


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
    session_store = SessionStore()
    username = os.getenv("AIA_USERNAME", "")
    password = os.getenv("AIA_PASSWORD", "")
    phone = os.getenv("AIA_PHONE")

    pw = None
    browser = None

    try:
        # Step 1: Create Browserbase session (different IP than Railway)
        _test_state["message"] = "Creating Browserbase session..."
        from browser.browserbase import create_session, get_debug_url
        bb_session_id, cdp_url = await create_session(proxy=False)

        try:
            debug_url = await get_debug_url(bb_session_id)
            _test_state["debug_url"] = debug_url
            log.info("Browserbase debug viewer: %s", debug_url)
        except Exception:
            pass

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
                "Logging in to AIA... (submit OTP at /test/otp when prompted)"
            )
            from portals.aia_login import aia_login
            from auth.twilio_otp import OTPStore

            otp_store = OTPStore()

            async def otp_callback():
                """Wait for OTP submitted via /test/otp endpoint."""
                _test_state["message"] = "Waiting for OTP — check your phone and POST to /test/otp"
                log.info("Waiting for OTP...")
                try:
                    code = await otp_store.wait_for_code(phone or "manual", timeout=120)
                    return code
                except Exception:
                    # also try "manual" key
                    return await otp_store.wait_for_code("manual", timeout=30)

            await aia_login(page, username, password, otp_callback)
            new_cookies = await page.context.cookies()
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
