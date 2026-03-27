"""Agentic loop: Claude Computer Use drives Playwright to authenticate on insurer portals."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import anthropic
from playwright.async_api import Page

from auth.twilio_otp import OTPStore
from claude import action_executor
from config import settings

log = logging.getLogger(__name__)

DISPLAY_WIDTH = 1280
DISPLAY_HEIGHT = 800
TOOL_VERSION = "computer_20251124"
BETA_FLAG = "computer-use-2025-11-24"
MODEL = "claude-sonnet-4-20250514"


class AuthenticationError(Exception):
    pass


def _load_prompt(portal_id: str) -> str:
    path = Path(__file__).parent / "prompts" / f"{portal_id}.txt"
    if not path.exists():
        raise FileNotFoundError(f"No prompt file for portal: {portal_id}")
    return path.read_text()


async def _take_screenshot(page: Page) -> str:
    """Capture a JPEG screenshot and return base64-encoded string."""
    buf = await page.screenshot(
        type="jpeg",
        quality=70,
        clip={"x": 0, "y": 0, "width": DISPLAY_WIDTH, "height": DISPLAY_HEIGHT},
    )
    return base64.b64encode(buf).decode()


async def claude_login(
    page: Page,
    portal_id: str,
    portal_login_url: str,
    credentials: dict,
    twilio_number: str | None = None,
) -> list[dict]:
    """Drive Claude through the portal login flow and return session cookies.

    Args:
        page: Playwright page (already created with correct viewport).
        portal_id: Used to load the correct system prompt.
        portal_login_url: URL to navigate to before starting.
        credentials: dict with 'username' and 'password'.
        twilio_number: E.164 number for OTP capture (None if no 2FA).

    Returns:
        List of cookie dicts from the authenticated browser context.

    Raises:
        AuthenticationError: If login fails after max turns.
    """
    max_turns = settings.claude_max_turns
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    otp_store = OTPStore() if twilio_number else None

    # Load portal-specific system prompt and inject credentials
    system_prompt = _load_prompt(portal_id)
    system_prompt = system_prompt.replace("{username}", credentials["username"])
    system_prompt = system_prompt.replace("{password}", credentials["password"])

    await page.goto(portal_login_url, wait_until="domcontentloaded", timeout=30000)

    tools = [
        {
            "type": TOOL_VERSION,
            "name": "computer",
            "display_width_px": DISPLAY_WIDTH,
            "display_height_px": DISPLAY_HEIGHT,
        },
    ]

    # Initial screenshot to give Claude context
    screenshot_b64 = await _take_screenshot(page)
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": screenshot_b64,
                    },
                },
                {
                    "type": "text",
                    "text": "Log into this portal now. The page is loaded and ready.",
                },
            ],
        }
    ]

    for turn in range(max_turns):
        log.info("Claude login turn %d/%d for portal %s", turn + 1, max_turns, portal_id)

        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
            tools=tools,
            betas=[BETA_FLAG],
        )

        # Append assistant response to conversation
        messages.append({"role": "assistant", "content": response.content})

        # Process tool use blocks
        tool_results = []
        for block in response.content:
            if block.type == "text":
                text = block.text.lower()
                # Check if Claude signals login complete
                if "login successful" in text or "authenticated" in text or "dashboard" in text:
                    log.info("Claude signals login complete for portal %s", portal_id)
                    return await page.context.cookies()

                # Check if Claude signals OTP needed
                if "otp" in text or "verification code" in text or "2fa" in text:
                    if otp_store and twilio_number:
                        log.info("Waiting for OTP on %s", twilio_number)
                        try:
                            otp_code = await otp_store.wait_for_code(twilio_number, timeout=30)
                            # Type the OTP into the page
                            await page.keyboard.type(otp_code, delay=50)
                        except TimeoutError:
                            log.warning("OTP timeout — retrying once")
                            try:
                                otp_code = await otp_store.wait_for_code(twilio_number, timeout=30)
                                await page.keyboard.type(otp_code, delay=50)
                            except TimeoutError:
                                raise AuthenticationError(
                                    f"OTP not received for {twilio_number} after 2 attempts"
                                )

            elif block.type == "tool_use":
                action = block.input

                if action.get("action") == "screenshot":
                    # Return a fresh screenshot
                    screenshot_b64 = await _take_screenshot(page)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": screenshot_b64,
                                },
                            }
                        ],
                    })
                else:
                    # Execute the action on the page
                    error = await action_executor.execute(page, action)
                    if error:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {error}",
                            "is_error": True,
                        })
                    else:
                        # After each non-screenshot action, return a screenshot
                        import asyncio
                        await asyncio.sleep(0.5)  # let page settle
                        screenshot_b64 = await _take_screenshot(page)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/jpeg",
                                        "data": screenshot_b64,
                                    },
                                }
                            ],
                        })

        # If no tool calls, check stop reason
        if response.stop_reason == "end_turn" and not tool_results:
            # Claude finished without tool use — check if login succeeded
            # by looking for dashboard indicators in the page
            log.info("Claude ended turn without tools — checking page state")
            return await page.context.cookies()

        if tool_results:
            messages.append({"role": "user", "content": tool_results})

    raise AuthenticationError(
        f"Login to {portal_id} failed after {max_turns} turns"
    )
