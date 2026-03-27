"""Translates Claude computer_use tool actions into Playwright page calls."""

from __future__ import annotations

import logging

from playwright.async_api import Page

log = logging.getLogger(__name__)


async def execute(page: Page, action: dict) -> str | None:
    """Execute a single Claude computer_use action on a Playwright page.

    Returns an error string if something went wrong, or None on success.
    """
    action_type = action.get("action")
    log.info("Executing action: %s", action_type)

    try:
        if action_type == "screenshot":
            # Handled by the caller — no-op here
            return None

        elif action_type == "left_click":
            x, y = action["coordinate"]
            await page.mouse.click(x, y)

        elif action_type == "right_click":
            x, y = action["coordinate"]
            await page.mouse.click(x, y, button="right")

        elif action_type == "double_click":
            x, y = action["coordinate"]
            await page.mouse.dblclick(x, y)

        elif action_type == "triple_click":
            x, y = action["coordinate"]
            await page.mouse.click(x, y, click_count=3)

        elif action_type == "middle_click":
            x, y = action["coordinate"]
            await page.mouse.click(x, y, button="middle")

        elif action_type == "mouse_move":
            x, y = action["coordinate"]
            await page.mouse.move(x, y)

        elif action_type == "type":
            text = action["text"]
            await page.keyboard.type(text, delay=50)

        elif action_type == "key":
            key = action["text"]
            await page.keyboard.press(key)

        elif action_type == "scroll":
            x, y = action["coordinate"]
            direction = action.get("scroll_direction", "down")
            amount = action.get("scroll_amount", 3)
            delta = amount * 100  # pixels per scroll tick
            if direction == "down":
                await page.mouse.wheel(0, delta)
            elif direction == "up":
                await page.mouse.wheel(0, -delta)
            elif direction == "right":
                await page.mouse.wheel(delta, 0)
            elif direction == "left":
                await page.mouse.wheel(-delta, 0)

        elif action_type == "left_click_drag":
            sx, sy = action["start_coordinate"]
            ex, ey = action["coordinate"]
            await page.mouse.move(sx, sy)
            await page.mouse.down()
            await page.mouse.move(ex, ey)
            await page.mouse.up()

        elif action_type == "wait":
            import asyncio
            await asyncio.sleep(action.get("duration", 1))

        else:
            return f"Unknown action type: {action_type}"

    except Exception as e:
        log.error("Action %s failed: %s", action_type, e)
        return str(e)

    return None
