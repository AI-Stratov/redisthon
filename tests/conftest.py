"""
Test configuration and fixtures
"""

from unittest.mock import Mock

import pytest

from redisthon import RedisClient, RedisSession


@pytest.fixture
def mock_redis_client():
    """Mock Redis client for testing without real Redis server."""
    client = Mock(spec=RedisClient)
    client.ping.return_value = True
    client.serialize.side_effect = lambda x: str(x).encode()
    client.deserialize.side_effect = lambda x: x.decode() if isinstance(x, bytes) else x
    client.get_key.return_value = None
    client.set_key.return_value = None
    client.hash_get.return_value = None
    client.hash_set.return_value = None
    client.hash_scan.return_value = []
    client.hash_len.return_value = 0
    client.key_exists.return_value = False
    client.expire_key.return_value = None
    client.get_info.return_value = {
        'redis_version': '7.0.0',
        'connected_clients': 1,
        'used_memory': 1000000,
        'used_memory_human': '1M',
        'serializer': 'msgpack',
        'is_dragonfly': False,
    }
    client.get_client_info.return_value = {
        'host': 'localhost',
        'port': 6379,
        'serializer': 'msgpack',
    }
    return client


@pytest.fixture
def redis_session(mock_redis_client):
    """Redis session with mocked client."""
    return RedisSession(
        'test_session',
        redis_client=mock_redis_client,
        save_entities=True,
    )


@pytest.fixture
def session_data():
    """Sample session data for testing."""
    return {
        'session_name': 'test_session',
        'dc_id': 2,
        'server_address': 'test.telegram.org',
        'port': 443,
        'auth_key': 'dGVzdF9hdXRoX2tleQ==',  # base64 encoded 'test_auth_key'
        'takeout_id': None,
        'saved_at': '2025-08-23T19:00:00+00:00',
        'version': '0.1.0',
    }


@pytest.fixture
def entity_data():
    """Sample entity data for testing."""
    return {
        'id': 123456789,
        'access_hash': 987654321,
        'username': 'test_user',
        'phone': '+1234567890',
        'name': 'Test User',
        'cached_at': '2025-08-23T19:00:00+00:00',
    }
