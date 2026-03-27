"""Write-back normalised policy data to the Axis CRM REST API."""

from __future__ import annotations

import logging
import time

import httpx

from config import settings

log = logging.getLogger(__name__)

MAX_RETRIES = 3
BACKOFF_BASE = 2  # seconds


def upsert_policies(adviser_id: str, portal_id: str, policies: list[dict]) -> None:
    """POST policies to the Axis CRM upsert endpoint with retry."""
    url = f"{settings.axis_crm_api_url}/policy-sync/upsert"
    headers = {
        "Authorization": f"Bearer {settings.axis_crm_api_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "adviser_id": adviser_id,
        "portal_id": portal_id,
        "synced_at": _now_iso(),
        "policies": policies,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
            log.info(
                "CRM upsert success: %d policies for %s:%s",
                len(policies), adviser_id, portal_id,
            )
            return
        except httpx.HTTPError as e:
            last_error = e
            wait = BACKOFF_BASE ** attempt
            log.warning(
                "CRM upsert attempt %d/%d failed: %s — retrying in %ds",
                attempt, MAX_RETRIES, e, wait,
            )
            time.sleep(wait)

    raise RuntimeError(
        f"CRM upsert failed after {MAX_RETRIES} attempts: {last_error}"
    )


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
