"""Inbound webhooks — Twilio SMS for OTP capture."""

from __future__ import annotations

import hashlib
import hmac
import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Form, Header, HTTPException, Request

from auth.twilio_otp import OTPStore
from config import settings

log = logging.getLogger(__name__)
router = APIRouter()
otp_store = OTPStore()


def _validate_twilio_signature(url: str, params: dict, signature: str) -> bool:
    """Verify the X-Twilio-Signature header."""
    if not settings.twilio_auth_token:
        log.warning("TWILIO_AUTH_TOKEN not set — skipping signature check")
        return True
    data = url + urlencode(sorted(params.items()))
    expected = hmac.new(
        settings.twilio_auth_token.encode(),
        data.encode(),
        hashlib.sha1,
    ).digest()
    import base64
    expected_b64 = base64.b64encode(expected).decode()
    return hmac.compare_digest(expected_b64, signature)


@router.post("/twilio/inbound")
async def twilio_inbound(
    request: Request,
    From: str = Form(...),
    Body: str = Form(...),
    x_twilio_signature: str = Header("", alias="X-Twilio-Signature"),
):
    """Receive inbound SMS from Twilio, extract OTP, store in Redis."""
    form_data = await request.form()
    params = {k: v for k, v in form_data.items()}

    if not _validate_twilio_signature(str(request.url), params, x_twilio_signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    code = OTPStore.extract_otp(Body)
    if not code:
        log.info("No OTP found in SMS from %s: %r", From, Body)
        return {"status": "ignored"}

    otp_store.store(From, code)
    return {"status": "stored", "from": From}
