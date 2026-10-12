"""
Tests for RedisClient functionality.
"""

from unittest.mock import Mock, patch

import pytest
import redis

from redisthon.client import RedisClient
from redisthon.exceptions import ConnectionError, SerializationError


class TestRedisClientInitialization:
    """Test Redis client initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default parameters."""
        with patch('redis.Redis') as mock_redis:
            client = RedisClient()
            assert client._config['host'] == 'localhost'
            assert client._config['port'] == 6379
            assert client._config['max_connections'] == 50
            assert client._is_dragonfly is False

    def test_init_with_dragonfly(self):
        """Test initialization for Dragonfly."""
        with patch('redis.Redis') as mock_redis:
            client = RedisClient(is_dragonfly=True, port=6380)
            assert client._is_dragonfly is True
            assert client._config['port'] == 6380
            # Dragonfly should not have db parameter
            assert client._config['db'] == 0

    def test_init_with_existing_redis_client(self):
        """Test initialization with existing Redis client."""
        mock_redis_client = Mock(spec=redis.Redis)
        client = RedisClient(redis_client=mock_redis_client)
        assert client._redis_client == mock_redis_client
        assert client._connection_pool is None


class TestSerialization:
    """Test data serialization/deserialization."""

    def test_msgpack_serialization(self):
        """Test msgpack serialization."""
        with patch('redisthon.client.msgpack') as mock_msgpack:
            mock_msgpack.packb.return_value = b'serialized_data'
            mock_msgpack.unpackb.return_value = {'key': 'value'}

            with patch('redis.Redis'):
                client = RedisClient()

            # Test serialization
            result = client.serialize({'test': 'data'})
            assert result == b'serialized_data'
            mock_msgpack.packb.assert_called_with({'test': 'data'}, use_bin_type=True)

            # Test deserialization
            result = client.deserialize(b'serialized_data')
            assert result == {'key': 'value'}
            mock_msgpack.unpackb.assert_called_with(b'serialized_data', raw=False)

    def test_serialization_error_handling(self):
        """Test serialization error handling."""
        with patch('redisthon.client.msgpack') as mock_msgpack:
            mock_msgpack.packb.side_effect = Exception('Serialization failed')

            with patch('redis.Redis'):
                client = RedisClient()

            with pytest.raises(SerializationError, match='Failed to serialize data'):
                client.serialize({'test': 'data'})


class TestRedisOperations:
    """Test Redis operations."""

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock Redis client."""
        with patch('redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_class.return_value = mock_redis_instance

            client = RedisClient()
            client._redis_client = mock_redis_instance
            return client, mock_redis_instance

    def test_ping_success(self, mock_redis_client):
        """Test successful ping operation."""
        client, mock_redis = mock_redis_client
        mock_redis.ping.return_value = True

        result = client.ping()
        assert result is True
        mock_redis.ping.assert_called_once()

    def test_ping_failure(self, mock_redis_client):
        """Test ping failure handling."""
        client, mock_redis = mock_redis_client
        mock_redis.ping.side_effect = Exception('Connection failed')

        result = client.ping()
        assert result is False

    def test_set_key_without_ttl(self, mock_redis_client):
        """Test setting key without TTL."""
        client, mock_redis = mock_redis_client

        with patch.object(client, 'serialize', return_value=b'serialized_data'):
            client.set_key('test_key', {'data': 'value'})

        mock_redis.set.assert_called_once_with('test_key', b'serialized_data')

    def test_set_key_with_ttl(self, mock_redis_client):
        """Test setting key with TTL."""
        client, mock_redis = mock_redis_client

        with patch.object(client, 'serialize', return_value=b'serialized_data'):
            client.set_key('test_key', {'data': 'value'}, ttl=300)

        mock_redis.setex.assert_called_once_with('test_key', 300, b'serialized_data')

    def test_get_key_exists(self, mock_redis_client):
        """Test getting existing key."""
        client, mock_redis = mock_redis_client
        mock_redis.get.return_value = b'serialized_data'

        with patch.object(client, 'deserialize', return_value={'data': 'value'}):
            result = client.get_key('test_key')

        assert result == {'data': 'value'}
        mock_redis.get.assert_called_once_with('test_key')

    def test_get_key_not_exists(self, mock_redis_client):
        """Test getting non-existent key."""
        client, mock_redis = mock_redis_client
        mock_redis.get.return_value = None

        result = client.get_key('test_key')
        assert result is None

    def test_hash_operations(self, mock_redis_client):
        """Test hash set/get operations."""
        client, mock_redis = mock_redis_client

        # Test hash set
        with patch.object(client, 'serialize', return_value=b'serialized_data'):
            client.hash_set('hash_key', 'field1', {'data': 'value'})

        mock_redis.hset.assert_called_once_with(
            'hash_key', 'field1', b'serialized_data'
        )

        # Test hash get
        mock_redis.hget.return_value = b'serialized_data'
        with patch.object(client, 'deserialize', return_value={'data': 'value'}):
            result = client.hash_get('hash_key', 'field1')

        assert result == {'data': 'value'}
        mock_redis.hget.assert_called_with('hash_key', 'field1')

    def test_hash_scan(self, mock_redis_client):
        """Test hash scanning operation."""
        client, mock_redis = mock_redis_client

        # Mock hscan to return data in two iterations
        mock_redis.hscan.side_effect = [
            (1, {b'field1': b'data1', b'field2': b'data2'}),
            (0, {b'field3': b'data3'}),  # cursor 0 indicates end
        ]

        with patch.object(
            client, 'deserialize', side_effect=lambda x: f'deserialized_{x.decode()}'
        ):
            result = client.hash_scan('hash_key')

        expected = [
            ('field1', 'deserialized_data1'),
            ('field2', 'deserialized_data2'),
            ('field3', 'deserialized_data3'),
        ]
        assert result == expected


class TestErrorHandling:
    """Test error handling in Redis operations."""

    @pytest.fixture
    def failing_redis_client(self):
        """Create Redis client that fails operations."""
        with patch('redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_class.return_value = mock_redis_instance

            # Make all operations fail
            mock_redis_instance.set.side_effect = redis.ConnectionError(
                'Connection failed'
            )
            mock_redis_instance.get.side_effect = redis.ConnectionError(
                'Connection failed'
            )
            mock_redis_instance.hset.side_effect = redis.ConnectionError(
                'Connection failed'
            )
            mock_redis_instance.hget.side_effect = redis.ConnectionError(
                'Connection failed'
            )

            client = RedisClient(host='localhost', port=6379)
            client._redis_client = mock_redis_instance
            return client, mock_redis_instance

    def test_set_key_connection_error(self, failing_redis_client):
        """Test set_key with connection error."""
        client, _ = failing_redis_client

        with patch.object(client, 'serialize', return_value=b'data'):
            with pytest.raises(ConnectionError, match="Failed to set key 'test_key'"):
                client.set_key('test_key', {'data': 'value'})

    def test_get_key_connection_error(self, failing_redis_client):
        """Test get_key with connection error."""
        client, _ = failing_redis_client

        with pytest.raises(ConnectionError, match="Failed to get key 'test_key'"):
            client.get_key('test_key')

    def test_hash_operations_connection_error(self, failing_redis_client):
        """Test hash operations with connection errors."""
        client, _ = failing_redis_client

        # Test hash set error
        with patch.object(client, 'serialize', return_value=b'data'):
            with pytest.raises(ConnectionError, match='Failed to set hash field'):
                client.hash_set('hash_key', 'field1', {'data': 'value'})

        # Test hash get error
        with pytest.raises(ConnectionError, match='Failed to get hash field'):
            client.hash_get('hash_key', 'field1')


class TestClientInfo:
    """Test client information methods."""

    def test_get_client_info(self):
        """Test getting client configuration info."""
        with patch('redis.Redis'):
            client = RedisClient(
                host='test.host', port=6380, max_connections=100, is_dragonfly=True
            )

        info = client.get_client_info()

        assert info['host'] == 'test.host'
        assert info['port'] == 6380
        assert info['max_connections'] == 100
        assert info['is_dragonfly'] is True
        assert info['serializer'] == 'msgpack'

    def test_get_info_success(self):
        """Test getting server info successfully."""
        with patch('redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_instance.info.return_value = {
                'redis_version': '7.0.0',
                'connected_clients': 5,
                'used_memory': 1000000,
                'used_memory_human': '1M',
                'keyspace_hits': 100,
                'keyspace_misses': 10,
            }
            mock_redis_class.return_value = mock_redis_instance

            client = RedisClient()

        info = client.get_info()

        assert info['redis_version'] == '7.0.0'
        assert info['connected_clients'] == 5
        assert info['used_memory'] == 1000000
        assert info['used_memory_human'] == '1M'
        assert info['is_dragonfly'] is False
        assert info['serializer'] == 'msgpack'

    def test_get_info_error(self):
        """Test getting server info with error."""
        with patch('redis.Redis') as mock_redis_class:
            mock_redis_instance = Mock()
            mock_redis_instance.info.side_effect = Exception('Info failed')
            mock_redis_class.return_value = mock_redis_instance

            client = RedisClient()

        info = client.get_info()

        assert 'error' in info
        assert info['error'] == 'Info failed'
        assert info['serializer'] == 'msgpack'


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager_success(self):
        """Test successful context manager usage."""
        with patch('redis.Redis') as mock_redis_class:
            mock_pool = Mock()
            mock_redis_class.return_value = Mock()

            with patch('redis.ConnectionPool', return_value=mock_pool):
                with RedisClient() as client:
                    assert client is not None

                mock_pool.disconnect.assert_called_once()

    def test_context_manager_with_exception(self):
        """Test context manager with exception during operation."""
        with patch('redis.Redis') as mock_redis_class:
            mock_pool = Mock()
            mock_redis_class.return_value = Mock()

            with patch('redis.ConnectionPool', return_value=mock_pool):
                try:
                    with RedisClient() as client:
                        raise ValueError('Test exception')
                except ValueError:
                    pass

                mock_pool.disconnect.assert_called_once()
