"""Twilio OTP capture — stores inbound SMS codes in Redis, waits for them during auth."""

from __future__ import annotations

import asyncio
import logging
import re

import redis

from config import settings

log = logging.getLogger(__name__)

OTP_TTL_SECONDS = 90
OTP_POLL_INTERVAL = 2


class OTPStore:
    def __init__(self, redis_url: str | None = None):
        self._r = redis.Redis.from_url(redis_url or settings.redis_url, decode_responses=True)

    @staticmethod
    def _key(twilio_number: str) -> str:
        return f"otp:{twilio_number}"

    def store(self, twilio_number: str, code: str) -> None:
        """Store an OTP code with a short TTL."""
        self._r.setex(self._key(twilio_number), OTP_TTL_SECONDS, code)
        log.info("Stored OTP for %s (ttl=%ds)", twilio_number, OTP_TTL_SECONDS)

    async def wait_for_code(self, twilio_number: str, timeout: int = 30) -> str:
        """Poll Redis until an OTP appears or timeout is reached."""
        elapsed = 0
        while elapsed < timeout:
            code = self._r.get(self._key(twilio_number))
            if code:
                self._r.delete(self._key(twilio_number))
                log.info("Retrieved OTP for %s", twilio_number)
                return code
            await asyncio.sleep(OTP_POLL_INTERVAL)
            elapsed += OTP_POLL_INTERVAL
        raise TimeoutError(f"No OTP received for {twilio_number} within {timeout}s")

    @staticmethod
    def extract_otp(body: str) -> str | None:
        """Pull the first 4-8 digit number from an SMS body."""
        match = re.search(r"\b(\d{4,8})\b", body)
        return match.group(1) if match else None
