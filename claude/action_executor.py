"""Translates Claude computer_use tool actions into Playwright page calls."""

from __future__ import annotations

import logging

from playwright.async_api import Page

log = logging.getLogger(__name__)

# Map Claude/X11 key names → Playwright W3C key names
_KEY_MAP = {
    "Return": "Enter",
    "KP_Enter": "Enter",
    "space": "Space",
    "ctrl": "Control",
    "Control_L": "Control",
    "Control_R": "Control",
    "alt": "Alt",
    "Alt_L": "Alt",
    "Alt_R": "Alt",
    "super": "Meta",
    "Super_L": "Meta",
    "shift": "Shift",
    "Shift_L": "Shift",
    "Shift_R": "Shift",
    "BackSpace": "Backspace",
    "Delete": "Delete",
    "Escape": "Escape",
    "Tab": "Tab",
    "F1": "F1", "F2": "F2", "F3": "F3", "F4": "F4", "F5": "F5",
    "F6": "F6", "F7": "F7", "F8": "F8", "F9": "F9", "F10": "F10",
    "F11": "F11", "F12": "F12",
}


def _translate_key(key: str) -> str:
    """Translate a Claude/X11 key name to a Playwright W3C key name."""
    # Handle combos like "ctrl+l" or "alt+Left"
    if "+" in key:
        parts = key.split("+")
        return "+".join(_KEY_MAP.get(p, p) for p in parts)
    return _KEY_MAP.get(key, key)


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
            key = _translate_key(action["text"])
            log.info("Translated key '%s' → '%s'", action["text"], key)
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

        elif action_type == "navigate":
            url = action.get("url") or action.get("text", "")
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

        elif action_type == "js_click":
            # Click an element via JS selector — useful when button is off-screen
            selector = action.get("selector", "")
            await page.evaluate(f'document.querySelector("{selector}")?.click()')

        else:
            return f"Unknown action type: {action_type}"

    except Exception as e:
        log.error("Action %s failed: %s", action_type, e)
        return str(e)

    return None
