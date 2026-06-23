"""
Tests for Redis-backed session store.
"""

import types

from utils.session_store import REDIS_KEY_PREFIX, SessionStore


class FakeRedisClient:
    def __init__(self):
        self.data = {}
        self.ttl = {}
        self.expire_calls = []

    def ping(self):
        return True

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value, ex=None):
        self.data[key] = value
        if ex is not None:
            self.ttl[key] = ex

    def expire(self, key, ttl):
        self.expire_calls.append((key, ttl))
        if key in self.data:
            self.ttl[key] = ttl


def test_session_store_isolates_sessions_with_redis(monkeypatch):
    client = FakeRedisClient()
    fake_redis_module = types.SimpleNamespace(from_url=lambda *args, **kwargs: client)
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    store = SessionStore(redis_url="redis://fake:6379", session_ttl_seconds=3600)

    store.set("current_image_prompt", "prompt-a", session_id="session-a")
    store.set("current_image_prompt", "prompt-b", session_id="session-b")

    assert store.get("current_image_prompt", session_id="session-a") == "prompt-a"
    assert store.get("current_image_prompt", session_id="session-b") == "prompt-b"


def test_session_store_sets_and_refreshes_ttl(monkeypatch):
    client = FakeRedisClient()
    fake_redis_module = types.SimpleNamespace(from_url=lambda *args, **kwargs: client)
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    ttl_seconds = 86400
    store = SessionStore(redis_url="redis://fake:6379", session_ttl_seconds=ttl_seconds)
    session_id = "abc"

    store.set("current_image_prompt", "hello", session_id=session_id)
    redis_key = f"{REDIS_KEY_PREFIX}:{session_id}"

    assert client.ttl[redis_key] == ttl_seconds

    store.get("current_image_prompt", session_id=session_id)
    assert (redis_key, ttl_seconds) in client.expire_calls


def test_session_store_reset_affects_only_target_session(monkeypatch):
    client = FakeRedisClient()
    fake_redis_module = types.SimpleNamespace(from_url=lambda *args, **kwargs: client)
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    store = SessionStore(redis_url="redis://fake:6379", session_ttl_seconds=3600)

    store.set("current_image_prompt", "keep", session_id="s1")
    store.set("current_image_prompt", "drop", session_id="s2")
    store.reset(session_id="s2")

    assert store.get("current_image_prompt", session_id="s1") == "keep"
    assert store.get("current_image_prompt", session_id="s2") == ""


def test_session_store_fallback_without_redis_is_per_session(monkeypatch):
    def _raise_from_url(*args, **kwargs):
        raise RuntimeError("redis unavailable")

    fake_redis_module = types.SimpleNamespace(from_url=_raise_from_url)
    monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)

    store = SessionStore(redis_url="redis://fake:6379", session_ttl_seconds=3600)

    assert store.using_redis is False

    store.set("current_image_prompt", "p1", session_id="tab-1")
    store.set("current_image_prompt", "p2", session_id="tab-2")

    assert store.get("current_image_prompt", session_id="tab-1") == "p1"
    assert store.get("current_image_prompt", session_id="tab-2") == "p2"
