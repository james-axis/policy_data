"""Slack webhook alerting for sync failures."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


def send_alert(webhook_url: str, message: str, details: dict | None = None) -> None:
    """Post a failure alert to a Slack webhook.

    Args:
        webhook_url: Slack incoming webhook URL.
        message: Short summary of the failure.
        details: Optional dict of extra context fields.
    """
    blocks = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":rotating_light: *Policy Sync Alert*\n{message}"},
        }
    ]

    if details:
        fields = [
            {"type": "mrkdwn", "text": f"*{k}:* {v}"}
            for k, v in details.items()
        ]
        blocks.append({"type": "section", "fields": fields})

    payload = {"blocks": blocks}

    try:
        with httpx.Client(timeout=10) as client:
            resp = client.post(webhook_url, json=payload)
            resp.raise_for_status()
        log.info("Alert sent to Slack: %s", message)
    except httpx.HTTPError as e:
        log.error("Failed to send Slack alert: %s", e)
