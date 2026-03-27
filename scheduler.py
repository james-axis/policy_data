"""Daily job scheduler — generates staggered sync jobs for all active adviser+portal configs.

Run at 2am AEST daily via Celery Beat or external cron.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from workers.sync_worker import run_sync_job

log = logging.getLogger(__name__)

AEST = timezone(timedelta(hours=10))
STAGGER_MINUTES = 5


def generate_daily_jobs(configs: list[dict]) -> int:
    """Queue sync jobs for all active configs, staggered by portal.

    Args:
        configs: List of dicts with keys:
            adviser_id, portal_id, portal_login_url, portal_base_url,
            secret_ref, twilio_number, session_ttl_hours

    Returns:
        Number of jobs queued.
    """
    # Group configs by portal_id
    by_portal: dict[str, list[dict]] = {}
    for cfg in configs:
        by_portal.setdefault(cfg["portal_id"], []).append(cfg)

    now = datetime.now(timezone.utc)
    total = 0

    for portal_id, adviser_configs in by_portal.items():
        for i, cfg in enumerate(adviser_configs):
            eta = now + timedelta(minutes=i * STAGGER_MINUTES)

            run_sync_job.apply_async(
                kwargs={
                    "adviser_id": cfg["adviser_id"],
                    "portal_id": cfg["portal_id"],
                    "portal_login_url": cfg["portal_login_url"],
                    "portal_base_url": cfg["portal_base_url"],
                    "secret_ref": cfg["secret_ref"],
                    "twilio_number": cfg.get("twilio_number"),
                    "session_ttl_hours": cfg.get("session_ttl_hours", 12),
                },
                eta=eta,
                queue=f"portal_{portal_id}",
            )
            total += 1
            log.info(
                "Queued sync for %s:%s at %s",
                cfg["adviser_id"], portal_id, eta.isoformat(),
            )

    log.info("Scheduled %d sync jobs across %d portals", total, len(by_portal))
    return total
