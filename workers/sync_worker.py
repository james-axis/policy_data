"""Main Celery task — orchestrates the full sync flow for one adviser+portal."""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from datetime import datetime, timezone

import redis as redis_lib

from celery_app import celery
from config import settings
from workers.crm_writer import upsert_policies
from workers.session_manager import ensure_authenticated_context

log = logging.getLogger(__name__)

# Portal registry: portal_id → extraction module path
PORTAL_MODULES = {
    "tal": "portals.tal.TALExtractor",
    "zurich": "portals.zurich.ZurichExtractor",
    "aia": "portals.aia.AIAExtractor",
    "mlc": "portals.mlc.MLCExtractor",
    "metlife": "portals.metlife.MetLifeExtractor",
    "clearview": "portals.clearview.ClearviewExtractor",
    "resolution": "portals.resolution.ResolutionExtractor",
}


def _load_extractor(portal_id: str):
    """Dynamically import and instantiate the portal extractor."""
    module_path = PORTAL_MODULES.get(portal_id)
    if not module_path:
        raise ValueError(f"Unknown portal: {portal_id}")
    module_name, class_name = module_path.rsplit(".", 1)
    mod = importlib.import_module(module_name)
    return getattr(mod, class_name)()


def _acquire_lock(portal_id: str, timeout: int = 1800) -> bool:
    """Redis distributed lock — max 1 concurrent job per portal."""
    r = redis_lib.Redis.from_url(settings.redis_url)
    return bool(r.set(f"lock:portal:{portal_id}", "1", nx=True, ex=timeout))


def _release_lock(portal_id: str) -> None:
    r = redis_lib.Redis.from_url(settings.redis_url)
    r.delete(f"lock:portal:{portal_id}")


@celery.task(bind=True, max_retries=2, default_retry_delay=60)
def run_sync_job(
    self,
    adviser_id: str,
    portal_id: str,
    portal_login_url: str,
    portal_base_url: str,
    secret_ref: str,
    twilio_number: str | None = None,
    session_ttl_hours: int = 12,
):
    """Full sync: authenticate → extract → write back to CRM."""
    job_id = str(uuid.uuid4())
    log.info("Starting sync job %s for %s:%s", job_id, adviser_id, portal_id)

    if not _acquire_lock(portal_id):
        log.warning("Portal %s is locked — another job is running. Retrying.", portal_id)
        raise self.retry(countdown=120)

    try:
        policies = asyncio.get_event_loop().run_until_complete(
            _async_sync(
                adviser_id=adviser_id,
                portal_id=portal_id,
                portal_login_url=portal_login_url,
                portal_base_url=portal_base_url,
                secret_ref=secret_ref,
                twilio_number=twilio_number,
                session_ttl_hours=session_ttl_hours,
            )
        )

        upsert_policies(adviser_id, portal_id, policies)
        log.info(
            "Sync job %s complete: %d policies synced for %s:%s",
            job_id, len(policies), adviser_id, portal_id,
        )
        return {
            "job_id": job_id,
            "status": "complete",
            "policies_count": len(policies),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        log.error("Sync job %s failed for %s:%s: %s", job_id, adviser_id, portal_id, e)
        raise self.retry(exc=e)

    finally:
        _release_lock(portal_id)


async def _async_sync(
    adviser_id: str,
    portal_id: str,
    portal_login_url: str,
    portal_base_url: str,
    secret_ref: str,
    twilio_number: str | None,
    session_ttl_hours: int,
) -> list[dict]:
    """Async portion: browser auth + extraction."""
    context = await ensure_authenticated_context(
        adviser_id=adviser_id,
        portal_id=portal_id,
        portal_login_url=portal_login_url,
        portal_base_url=portal_base_url,
        secret_ref=secret_ref,
        twilio_number=twilio_number,
        session_ttl_hours=session_ttl_hours,
    )

    try:
        extractor = _load_extractor(portal_id)
        return await extractor.extract(context)
    finally:
        await context.close()
