"""Browserbase session management — residential browser-as-a-service."""

from __future__ import annotations

import logging

import httpx

from config import settings

log = logging.getLogger(__name__)

BB_API = "https://www.browserbase.com/v1"


async def create_session(proxy: bool = True) -> tuple[str, str]:
    """Create a Browserbase session and return (session_id, cdp_url).

    Args:
        proxy: Whether to enable Browserbase's residential proxy (bypasses portal IP blocks).

    Returns:
        (session_id, cdp_url) — pass cdp_url to playwright.connect_over_cdp().
    """
    payload: dict = {"projectId": settings.browserbase_project_id}
    if proxy:
        payload["proxies"] = True

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BB_API}/sessions",
            headers={
                "x-bb-api-key": settings.browserbase_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    session_id = data["id"]
    cdp_url = (
        f"wss://connect.browserbase.com"
        f"?apiKey={settings.browserbase_api_key}"
        f"&sessionId={session_id}"
    )
    log.info("Browserbase session created: %s", session_id)
    return session_id, cdp_url


async def get_debug_url(session_id: str) -> str:
    """Return the live Browserbase debug viewer URL for a session."""
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(
            f"{BB_API}/sessions/{session_id}/debug",
            headers={"x-bb-api-key": settings.browserbase_api_key},
        )
        resp.raise_for_status()
        return resp.json().get("debuggerFullscreenUrl", "")
