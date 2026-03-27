"""Tests for the Redis session store."""

import json

import pytest
import fakeredis

from auth.session_store import SessionStore


@pytest.fixture
def store():
    """SessionStore backed by fakeredis."""
    s = SessionStore.__new__(SessionStore)
    s._r = fakeredis.FakeRedis(decode_responses=True)
    return s


def test_set_and_get(store):
    cookies = [{"name": "sid", "value": "abc123", "domain": ".example.com"}]
    store.set("adv1", "tal", cookies, ttl_hours=1)
    result = store.get("adv1", "tal")
    assert result == cookies


def test_get_missing(store):
    assert store.get("adv1", "nope") is None


def test_delete(store):
    store.set("adv1", "tal", [{"name": "x", "value": "y"}])
    store.delete("adv1", "tal")
    assert store.get("adv1", "tal") is None


def test_corrupt_data(store):
    store._r.set("session:adv1:tal", "not-json")
    assert store.get("adv1", "tal") is None
    # Should have been cleaned up
    assert store._r.get("session:adv1:tal") is None
