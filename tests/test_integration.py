"""
Integration tests for redisthon requiring real Redis server.

These tests require actual Redis/Dragonfly server running.
Configure via environment variables:
- REDIS_HOST (default: localhost)
- REDIS_PORT (default: 6379)
- REDIS_PASSWORD (optional)
- DRAGONFLY_HOST (default: localhost)
- DRAGONFLY_PORT (default: 6380)
"""

import os
from unittest.mock import patch

import pytest

from redisthon import RedisClient, RedisSession


def get_redis_config():
    """Get Redis configuration from environment variables."""
    return {
        'host': os.getenv('REDIS_HOST', 'localhost'),
        'port': int(os.getenv('REDIS_PORT', '6379')),
        'password': os.getenv('REDIS_PASSWORD'),
        'username': os.getenv('REDIS_USERNAME'),
    }


def get_dragonfly_config():
    """Get Dragonfly configuration from environment variables."""
    return {
        'host': os.getenv('DRAGONFLY_HOST', 'localhost'),
        'port': int(os.getenv('DRAGONFLY_PORT', '6380')),
        'password': os.getenv('DRAGONFLY_PASSWORD'),
        'is_dragonfly': True,
    }


def redis_available():
    """Check if Redis server is available."""
    try:
        config = get_redis_config()
        client = RedisClient(**config)
        result = client.ping()
        client.close()
        return result
    except Exception:
        return False


def dragonfly_available():
    """Check if Dragonfly server is available."""
    try:
        config = get_dragonfly_config()
        client = RedisClient(**config)
        result = client.ping()
        client.close()
        return result
    except Exception:
        return False


@pytest.mark.integration
class TestRedisIntegration:
    """Integration tests with real Redis server."""

    @pytest.fixture(autouse=True)
    def skip_if_no_redis(self):
        """Skip tests if Redis is not available."""
        if not redis_available():
            pytest.skip(
                'Redis server not available. Set REDIS_HOST/REDIS_PORT or start local Redis.'
            )

    def test_real_redis_connection(self):
        """Test connection to real Redis server."""
        config = get_redis_config()

        with RedisSession('integration_test', **config) as session:
            health = session.get_health_info()
            assert health['connection_healthy']

            server_info = health['server_info']
            assert 'redis_version' in server_info
            assert server_info['serializer'] == 'msgpack'

    def test_session_persistence(self):
        """Test session data persistence across instances."""
        config = get_redis_config()
        session_name = 'persistence_test'

        # Create and save session
        with RedisSession(session_name, **config) as session1:
            session1.set_dc(2, 'test.telegram.org', 443)
            stats1 = session1.get_statistics()

        # Load session in new instance
        with RedisSession(session_name, **config) as session2:
            assert session2.dc_id == 2
            assert session2.server_address == 'test.telegram.org'
            assert session2.port == 443

            stats2 = session2.get_statistics()
            assert stats2['session_exists']

    def test_entity_caching_real_redis(self):
        """Test entity caching with real Redis operations."""
        config = get_redis_config()

        with RedisSession('entity_test', **config) as session:
            # Simulate entity data
            entity_data = {
                'id': 123456789,
                'access_hash': 987654321,
                'username': 'test_user',
                'phone': '+1234567890',
                'name': 'Test User',
            }

            # Store entity manually
            session._client.hash_set(
                session._entities_key, str(entity_data['id']), entity_data
            )

            # Retrieve entity
            result = session.get_entity_rows_by_id(123456789)
            assert len(result) == 1
            assert result[0] == (123456789, 987654321)

            # Test username lookup
            result_username = session.get_entity_rows_by_username('test_user')
            assert len(result_username) == 1

    def test_serialization_with_real_redis(self):
        """Test msgpack serialization with real Redis storage."""
        config = get_redis_config()

        with RedisSession('serialization_test', **config) as session:
            # Test complex data structure
            test_data = {
                'string': 'test_value',
                'integer': 42,
                'list': [1, 2, 3, 'four'],
                'dict': {'nested': True, 'value': 3.14},
                'bytes': b'binary_data',
            }

            # Store and retrieve
            session._client.set_key('test_key', test_data)
            retrieved_data = session._client.get_key('test_key')

            assert retrieved_data == test_data
            assert isinstance(retrieved_data['bytes'], bytes)


@pytest.mark.integration
class TestDragonflyIntegration:
    """Integration tests with real Dragonfly server."""

    @pytest.fixture(autouse=True)
    def skip_if_no_dragonfly(self):
        """Skip tests if Dragonfly is not available."""
        if not dragonfly_available():
            pytest.skip(
                'Dragonfly server not available. Set DRAGONFLY_HOST/DRAGONFLY_PORT or start local Dragonfly.'
            )

    def test_dragonfly_connection(self):
        """Test connection to Dragonfly server."""
        config = get_dragonfly_config()

        with RedisSession('dragonfly_test', **config) as session:
            health = session.get_health_info()
            assert health['connection_healthy']

            client_info = health['client_info']
            assert client_info['is_dragonfly']

    def test_dragonfly_performance(self):
        """Test operations with Dragonfly."""
        config = get_dragonfly_config()

        with RedisSession('dragonfly_perf', **config) as session:
            # Test batch operations
            import time

            start_time = time.perf_counter()
            for i in range(100):
                session._client.hash_set('perf_test', f'field_{i}', {'data': i})

            for i in range(100):
                result = session._client.hash_get('perf_test', f'field_{i}')
                assert result['data'] == i

            duration = time.perf_counter() - start_time

            # Should be reasonably fast
            assert duration < 5.0, f'Operations took too long: {duration:.3f}s'


@pytest.mark.integration
class TestEnvironmentConfiguration:
    """Test environment-based configuration."""

    def test_redis_config_from_env(self):
        """Test Redis configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                'REDIS_HOST': 'test.host',
                'REDIS_PORT': '1234',
                'REDIS_PASSWORD': 'test_password',
                'REDIS_USERNAME': 'test_user',
            },
        ):
            config = get_redis_config()

            assert config['host'] == 'test.host'
            assert config['port'] == 1234
            assert config['password'] == 'test_password'
            assert config['username'] == 'test_user'

    def test_dragonfly_config_from_env(self):
        """Test Dragonfly configuration from environment variables."""
        with patch.dict(
            os.environ,
            {
                'DRAGONFLY_HOST': 'dragon.host',
                'DRAGONFLY_PORT': '5678',
                'DRAGONFLY_PASSWORD': 'dragon_password',
            },
        ):
            config = get_dragonfly_config()

            assert config['host'] == 'dragon.host'
            assert config['port'] == 5678
            assert config['password'] == 'dragon_password'
            assert config['is_dragonfly']

    def test_default_config_values(self):
        """Test default configuration values."""
        # Clear environment variables
        with patch.dict(os.environ, {}, clear=True):
            redis_config = get_redis_config()
            dragonfly_config = get_dragonfly_config()

            assert redis_config['host'] == 'localhost'
            assert redis_config['port'] == 6379
            assert redis_config['password'] is None

            assert dragonfly_config['host'] == 'localhost'
            assert dragonfly_config['port'] == 6380
            assert dragonfly_config['is_dragonfly']


if __name__ == '__main__':
    """
    Run integration tests manually.
    
    Usage:
        python -m pytest tests/test_integration.py -v
        
    Or with specific Redis:
        REDIS_HOST=myredis.com REDIS_PORT=6380 python -m pytest tests/test_integration.py
    """

    print('=== Redis Integration Test Setup ===')
    print(f'Redis config: {get_redis_config()}')
    print(f'Redis available: {redis_available()}')

    print('\n=== Dragonfly Integration Test Setup ===')
    print(f'Dragonfly config: {get_dragonfly_config()}')
    print(f'Dragonfly available: {dragonfly_available()}')

    # Run specific tests
    pytest.main([__file__, '-v', '--tb=short'])
