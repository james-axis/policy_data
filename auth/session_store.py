"""Redis-backed cookie/session store keyed by adviser + portal."""

from __future__ import annotations

import json
import logging

import redis

from config import settings

log = logging.getLogger(__name__)


class SessionStore:
    def __init__(self, redis_url: str | None = None):
        self._r = redis.Redis.from_url(redis_url or settings.redis_url, decode_responses=True)

    @staticmethod
    def _key(adviser_id: str, portal_id: str) -> str:
        return f"session:{adviser_id}:{portal_id}"

    def get(self, adviser_id: str, portal_id: str) -> list[dict] | None:
        """Return stored cookies or None if missing/expired."""
        raw = self._r.get(self._key(adviser_id, portal_id))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Corrupt session data for %s:%s — deleting", adviser_id, portal_id)
            self.delete(adviser_id, portal_id)
            return None

    def set(self, adviser_id: str, portal_id: str, cookies: list[dict], ttl_hours: int = 12) -> None:
        """Persist cookies with a TTL (hours)."""
        self._r.setex(
            self._key(adviser_id, portal_id),
            ttl_hours * 3600,
            json.dumps(cookies),
        )
        log.info("Stored session for %s:%s (ttl=%dh)", adviser_id, portal_id, ttl_hours)

    def delete(self, adviser_id: str, portal_id: str) -> None:
        """Invalidate a session."""
        self._r.delete(self._key(adviser_id, portal_id))
        log.info("Deleted session for %s:%s", adviser_id, portal_id)
