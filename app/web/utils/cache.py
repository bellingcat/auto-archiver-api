import functools
import inspect
from typing import Callable

from cachetools import TTLCache


def cached_endpoint(cache: TTLCache, key: Callable[..., object]):
    """
    Cache a FastAPI endpoint's return value in a time-bounded ``TTLCache``.

    ``key`` receives the same arguments FastAPI injects into the endpoint (its
    resolved dependencies) and must return a hashable cache key. For per-user
    endpoints the key MUST include a stable user identifier so one user can
    never be served another user's cached response.

    Only successful return values are cached: if the endpoint raises (e.g. an
    ``HTTPException``) the error propagates and nothing is stored, so the next
    request re-evaluates the endpoint.

    ``functools.wraps`` keeps the original signature visible to FastAPI so
    dependency injection, response models and auth all keep working; the wrapper
    matches the sync/async nature of the wrapped endpoint so its execution model
    (threadpool vs event loop) is preserved.
    """

    def decorator(func):
        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                cache_key = key(*args, **kwargs)
                if cache_key in cache:
                    return cache[cache_key]
                result = await func(*args, **kwargs)
                cache[cache_key] = result
                return result

            return async_wrapper

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            cache_key = key(*args, **kwargs)
            if cache_key in cache:
                return cache[cache_key]
            result = func(*args, **kwargs)
            cache[cache_key] = result
            return result

        return sync_wrapper

    return decorator
