"""
Fixtures for integration tests. These need a running server.

Redis is always required: REDIS_HOST and REDIS_PORT (default localhost:6379).
Dragonfly runs only when DRAGONFLY_PORT is set (host from DRAGONFLY_HOST,
default localhost).
"""

import os
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
import redis

BACKENDS = ['redis', 'dragonfly']


def backend_config(name: str) -> dict[str, Any]:
    if name == 'redis':
        return {
            'host': os.getenv('REDIS_HOST', 'localhost'),
            'port': int(os.getenv('REDIS_PORT', '6379')),
        }
    port = os.getenv('DRAGONFLY_PORT')
    if port is None:
        pytest.skip('DRAGONFLY_PORT is not set')
    return {
        'host': os.getenv('DRAGONFLY_HOST', 'localhost'),
        'port': int(port),
        'is_dragonfly': True,
    }


@pytest.fixture(params=BACKENDS)
def server(request: pytest.FixtureRequest) -> dict[str, Any]:
    """Connection settings for RedisSession. Fails if the server is down."""
    config = backend_config(request.param)
    conn = redis.Redis(host=config['host'], port=config['port'])
    try:
        conn.ping()
    except redis.ConnectionError as e:
        pytest.fail(f'{request.param} is not reachable at {config}: {e}')
    finally:
        conn.close()
    return config


@pytest.fixture
def key_prefix(server: dict[str, Any]) -> Iterator[str]:
    """Unique key prefix per test. Deletes its keys afterwards."""
    prefix = f'redisthon-test:{uuid.uuid4().hex}'
    yield prefix
    conn = redis.Redis(host=server['host'], port=server['port'])
    keys = list(conn.scan_iter(match=f'{prefix}:*'))
    if keys:
        conn.delete(*keys)
    conn.close()
