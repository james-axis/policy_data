"""Tests for OTP extraction and storage."""

import pytest
import fakeredis

from auth.twilio_otp import OTPStore


@pytest.fixture
def otp_store():
    s = OTPStore.__new__(OTPStore)
    s._r = fakeredis.FakeRedis(decode_responses=True)
    return s


def test_extract_otp_6_digits():
    assert OTPStore.extract_otp("Your code is 123456") == "123456"


def test_extract_otp_4_digits():
    assert OTPStore.extract_otp("Code: 4321") == "4321"


def test_extract_otp_no_match():
    assert OTPStore.extract_otp("Hello there") is None


def test_extract_otp_8_digits():
    assert OTPStore.extract_otp("Use 12345678 to verify") == "12345678"


def test_store_and_retrieve(otp_store):
    otp_store.store("+61400000000", "987654")
    code = otp_store._r.get("otp:+61400000000")
    assert code == "987654"
