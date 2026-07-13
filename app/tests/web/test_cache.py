from http import HTTPStatus
from unittest.mock import MagicMock

import pytest
from cachetools import TTLCache
from fastapi.testclient import TestClient

from app.shared.schemas import Usage, UsageResponse
from app.web.routers import default
from app.web.security import get_user_state
from app.web.utils.cache import cached_endpoint


# --- unit tests for the decorator ------------------------------------------


def test_cached_endpoint_sync_caches_by_key():
    cache = TTLCache(maxsize=8, ttl=60)
    calls = []

    @cached_endpoint(cache, key=lambda user: user)
    def endpoint(user):
        calls.append(user)
        return f"result-{user}"

    assert endpoint(user="a") == "result-a"
    assert endpoint(user="a") == "result-a"  # served from cache
    assert calls == ["a"]  # body ran only once

    assert endpoint(user="b") == "result-b"  # different key, recomputed
    assert calls == ["a", "b"]


@pytest.mark.asyncio
async def test_cached_endpoint_async_caches():
    cache = TTLCache(maxsize=8, ttl=60)
    calls = []

    @cached_endpoint(cache, key=lambda: "const")
    async def endpoint():
        calls.append(1)
        return "value"

    assert await endpoint() == "value"
    assert await endpoint() == "value"
    assert len(calls) == 1


def test_cached_endpoint_does_not_cache_exceptions():
    cache = TTLCache(maxsize=8, ttl=60)
    calls = []

    @cached_endpoint(cache, key=lambda: "k")
    def endpoint():
        calls.append(1)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        endpoint()
    with pytest.raises(ValueError):
        endpoint()
    assert len(calls) == 2  # re-evaluated, error never cached


def test_cached_endpoint_sync_is_thread_safe():
    """Concurrent threads must never observe a partially-written cache entry
    and must never corrupt TTLCache's internal state."""
    import threading as _threading

    cache = TTLCache(maxsize=128, ttl=60)
    lock = _threading.Lock()
    calls = []

    @cached_endpoint(cache, key=lambda user: user, lock=lock)
    def endpoint(user):
        calls.append(user)
        return f"result-{user}"

    errors = []

    def hit(user):
        try:
            result = endpoint(user=user)
            assert result == f"result-{user}"
        except Exception as exc:
            errors.append(exc)

    threads = [
        _threading.Thread(target=hit, args=(f"user-{i % 4}",))
        for i in range(64)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    # Each of the 4 distinct users should have been computed at least once but
    # at most once per user (the lock prevents duplicate computation).
    assert len(calls) == 4


# --- endpoint-level behaviour ----------------------------------------------


def _usage(monthly_urls: int) -> UsageResponse:
    return UsageResponse(
        monthly_urls=monthly_urls,
        monthly_mbs=0,
        total_sheets=0,
        groups={"g": Usage(monthly_urls=monthly_urls)},
    )


def test_user_usage_is_cached(app):
    user = MagicMock()
    user.active = True
    user.email = "alice@example.com"
    user.usage.return_value = _usage(1)

    app.dependency_overrides[get_user_state] = lambda: user
    client = TestClient(app)

    r1 = client.get("/user/usage")
    r2 = client.get("/user/usage")
    assert r1.status_code == r2.status_code == HTTPStatus.OK
    assert r1.json() == r2.json()
    # second request was served from cache, so usage() ran only once
    assert user.usage.call_count == 1


def test_user_usage_is_isolated_per_user(app):
    alice = MagicMock()
    alice.active = True
    alice.email = "alice@example.com"
    alice.usage.return_value = _usage(11)

    bob = MagicMock()
    bob.active = True
    bob.email = "bob@example.com"
    bob.usage.return_value = _usage(22)

    client = TestClient(app)

    app.dependency_overrides[get_user_state] = lambda: alice
    r_alice = client.get("/user/usage")

    app.dependency_overrides[get_user_state] = lambda: bob
    r_bob = client.get("/user/usage")

    assert r_alice.json()["monthly_urls"] == 11
    assert r_bob.json()["monthly_urls"] == 22  # not alice's cached value

    # a fresh object for alice must hit her cached entry, not recompute
    alice_again = MagicMock()
    alice_again.active = True
    alice_again.email = "alice@example.com"
    alice_again.usage.return_value = _usage(999)
    app.dependency_overrides[get_user_state] = lambda: alice_again
    r_alice_again = client.get("/user/usage")
    assert r_alice_again.json()["monthly_urls"] == 11  # cached, not 999
    assert alice_again.usage.call_count == 0


def test_user_usage_inactive_error_is_not_cached(app):
    user = MagicMock()
    user.email = "carol@example.com"
    user.active = False
    user.usage.return_value = _usage(5)

    app.dependency_overrides[get_user_state] = lambda: user
    client = TestClient(app)

    r_forbidden = client.get("/user/usage")
    assert r_forbidden.status_code == HTTPStatus.FORBIDDEN

    # once active, the previously-raised 403 must not have been cached
    user.active = True
    r_ok = client.get("/user/usage")
    assert r_ok.status_code == HTTPStatus.OK
    assert r_ok.json()["monthly_urls"] == 5


def test_user_permissions_is_cached(app):
    from app.shared.user_groups import GroupInfo

    user = MagicMock()
    user.email = "dave@example.com"
    perms = {"all": GroupInfo(read=True)}
    type(user).permissions = property(lambda self: perms)

    app.dependency_overrides[get_user_state] = lambda: user
    client = TestClient(app)

    r1 = client.get("/user/permissions")
    r2 = client.get("/user/permissions")
    assert r1.status_code == r2.status_code == HTTPStatus.OK
    assert r1.json() == r2.json()
    assert default.USER_PERMISSIONS_CACHE["dave@example.com"] is perms


def test_home_endpoint_is_cached(client_with_auth):
    r1 = client_with_auth.get("/")
    r2 = client_with_auth.get("/")
    assert r1.status_code == r2.status_code == HTTPStatus.OK
    assert r1.json() == r2.json()
    assert "home" in default.HOME_CACHE
