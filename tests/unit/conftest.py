"""
Fixtures for unit tests. Redis is replaced by fakeredis or by mocks; nothing
here talks to a real server.
"""

from collections.abc import Callable
from typing import Any

import fakeredis
import pytest

from redisthon import RedisClient, RedisSession


@pytest.fixture
def fake_redis() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


@pytest.fixture
def client(fake_redis: fakeredis.FakeRedis) -> RedisClient:
    return RedisClient(redis_client=fake_redis)


@pytest.fixture
def make_session(client: RedisClient) -> Callable[..., RedisSession]:
    """Create sessions that share one fake server."""

    def make(name: str = 'test', **kwargs: Any) -> RedisSession:
        return RedisSession(name, redis_client=client, **kwargs)

    return make


@pytest.fixture
def session(make_session: Callable[..., RedisSession]) -> RedisSession:
    return make_session()
