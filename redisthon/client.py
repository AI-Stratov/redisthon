"""
Redis/Dragonfly client with connection management.
"""

import base64
import logging
from typing import Any, cast

import msgpack
import redis
from redis.connection import ConnectionPool

from .exceptions import ConfigurationError, ConnectionError, SerializationError

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis/Dragonfly client with optimized connection management.

    :param host: Redis/Dragonfly server host
    :param port: Server port
    :param db: Database number (Redis only, ignored for Dragonfly)
    :param password: Authentication password
    :param username: Authentication username (Redis 6.0+)
    :param max_connections: Maximum connections in pool
    :param socket_keepalive: Enable TCP keepalive
    :param socket_keepalive_options: TCP keepalive settings
    :param health_check_interval: Health check interval in seconds
    :param connection_timeout: Connection timeout in seconds
    :param socket_timeout: Socket timeout in seconds
    :param is_dragonfly: Whether using Dragonfly instead of Redis
    :param redis_client: Existing Redis client to use
    """

    __slots__ = (
        '_config',
        '_connection_pool',
        '_is_dragonfly',
        '_redis_client',
    )

    def __init__(
        self,
        *,
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        username: str | None = None,
        max_connections: int = 50,
        socket_keepalive: bool = True,
        socket_keepalive_options: dict[str, Any] | None = None,
        health_check_interval: int = 30,
        connection_timeout: int = 5,
        socket_timeout: int = 5,
        is_dragonfly: bool = False,
        redis_client: redis.Redis | None = None,
    ) -> None:
        self._is_dragonfly = is_dragonfly

        # Store configuration with proper types
        self._config: dict[str, Any] = {
            'host': host,
            'port': port,
            'db': db if not is_dragonfly else 0,
            'password': password,
            'username': username,
            'max_connections': max_connections,
            'socket_keepalive': socket_keepalive,
            'socket_keepalive_options': socket_keepalive_options or {},
            'health_check_interval': health_check_interval,
            'connection_timeout': connection_timeout,
            'socket_timeout': socket_timeout,
        }

        if redis_client is not None:
            self._redis_client = redis_client
            self._connection_pool: ConnectionPool | None = None
        else:
            self._setup_connection_pool()

    def _setup_connection_pool(self) -> None:
        """Setup connection pool."""
        try:
            pool_kwargs = {
                'host': self._config['host'],
                'port': self._config['port'],
                'password': self._config['password'],
                'socket_keepalive': self._config['socket_keepalive'],
                'socket_keepalive_options': self._config['socket_keepalive_options'],
                'health_check_interval': self._config['health_check_interval'],
                'max_connections': self._config['max_connections'],
                'socket_connect_timeout': self._config['connection_timeout'],
                'socket_timeout': self._config['socket_timeout'],
                'decode_responses': False,
            }

            # Dragonfly doesn't support database selection
            if not self._is_dragonfly:
                pool_kwargs['db'] = self._config['db']

            if self._config['username']:
                pool_kwargs['username'] = self._config['username']

            self._connection_pool = ConnectionPool(**pool_kwargs)
            self._redis_client = redis.Redis(connection_pool=self._connection_pool)

            logger.debug(
                f'Created connection pool for {"Dragonfly" if self._is_dragonfly else "Redis"}'
            )

        except Exception as e:
            raise ConfigurationError(
                f'Failed to setup connection pool: {e}', parameter='connection_pool'
            ) from e

    def serialize(self, data: Any) -> bytes:
        """
        Serialize data using msgpack.

        :param data: Data to serialize
        :returns: Serialized bytes
        :raises SerializationError: If serialization fails
        """
        try:
            return cast(bytes, msgpack.packb(data, use_bin_type=True))
        except Exception as e:
            raise SerializationError(
                f'Failed to serialize data: {e}', serializer='msgpack'
            ) from e

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize data using msgpack.

        :param data: Data to deserialize
        :returns: Deserialized data
        :raises SerializationError: If deserialization fails
        """
        try:
            return msgpack.unpackb(data, raw=False)
        except Exception as e:
            raise SerializationError(
                f'Failed to deserialize data: {e}', serializer='msgpack'
            ) from e

    def ping(self) -> bool:
        """
        Test connection to Redis/Dragonfly.

        :returns: True if connection is healthy
        """
        try:
            result = self._redis_client.ping()
            return bool(result)
        except Exception as e:
            logger.warning(f'Ping failed: {e}')
            return False

    def set_key(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Set a key with optional TTL.

        :param key: Redis key
        :param value: Value to store
        :param ttl: Time to live in seconds (optional)
        :raises ConnectionError: If Redis operation fails
        """
        try:
            serialized_data = self.serialize(value)
            if ttl and ttl > 0:
                self._redis_client.setex(key, ttl, serialized_data)
            else:
                self._redis_client.set(key, serialized_data)
        except Exception as e:
            raise ConnectionError(
                f"Failed to set key '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def get_key(self, key: str) -> Any | None:
        """
        Get a key value.

        :param key: Redis key
        :returns: Deserialized value or None if key doesn't exist
        :raises ConnectionError: If Redis operation fails
        """
        try:
            data = self._redis_client.get(key)
            if data is None:
                return None
            return self.deserialize(cast(bytes, data))
        except Exception as e:
            raise ConnectionError(
                f"Failed to get key '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def hash_set(self, key: str, field: str, value: Any) -> None:
        """
        Set a hash field.

        :param key: Hash key
        :param field: Field name
        :param value: Value to store
        :raises ConnectionError: If Redis operation fails
        """
        try:
            serialized_data = self.serialize(value)
            # Convert bytes to base64 string for hset compatibility
            serialized_str = base64.b64encode(serialized_data).decode('utf-8')
            self._redis_client.hset(key, field, serialized_str)
        except Exception as e:
            raise ConnectionError(
                f"Failed to set hash field '{key}:{field}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def hash_get(self, key: str, field: str) -> Any | None:
        """
        Get a hash field value.

        :param key: Hash key
        :param field: Field name
        :returns: Deserialized value or None if field doesn't exist
        :raises ConnectionError: If Redis operation fails
        """
        try:
            raw_data = self._redis_client.hget(key, field)
            if raw_data is None:
                return None

            # Convert to bytes for deserialization
            data_bytes: bytes
            if isinstance(raw_data, str):
                # Data is base64 encoded string
                data_bytes = base64.b64decode(raw_data.encode('utf-8'))
            elif isinstance(raw_data, bytes):
                # Try to decode as base64 first, if that fails assume it's raw bytes
                try:
                    data_bytes = base64.b64decode(raw_data)
                except Exception:
                    data_bytes = raw_data  # Use raw bytes as is
            else:
                # Fallback for other types
                data_bytes = cast(bytes, raw_data)

            return self.deserialize(data_bytes)
        except Exception as e:
            raise ConnectionError(
                f"Failed to get hash field '{key}:{field}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def hash_scan(self, key: str) -> list[tuple[str, Any]]:
        """
        Scan all hash fields efficiently.

        :param key: Hash key
        :returns: List of (field, value) tuples
        :raises ConnectionError: If Redis operation fails
        """
        try:
            cursor = 0
            results = []
            while True:
                cursor, fields = cast(
                    tuple[int, dict[bytes, bytes]],
                    self._redis_client.hscan(key, cursor),
                )
                for field, value in fields.items():
                    try:
                        deserialized_value = self.deserialize(value)
                        field_str = (
                            field.decode() if isinstance(field, bytes) else str(field)
                        )
                        results.append((field_str, deserialized_value))
                    except Exception:
                        continue  # Skip corrupted data
                if cursor == 0:
                    break
            return results
        except Exception as e:
            raise ConnectionError(
                f"Failed to scan hash '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def hash_len(self, key: str) -> int:
        """
        Get hash length.

        :param key: Hash key
        :returns: Number of fields in hash
        :raises ConnectionError: If Redis operation fails
        """
        try:
            result = self._redis_client.hlen(key)
            return cast(int, result)
        except Exception as e:
            raise ConnectionError(
                f"Failed to get hash length '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def key_exists(self, key: str) -> bool:
        """
        Check if key exists.

        :param key: Redis key
        :returns: True if key exists
        :raises ConnectionError: If Redis operation fails
        """
        try:
            result = self._redis_client.exists(key)
            return bool(result)
        except Exception as e:
            raise ConnectionError(
                f"Failed to check key existence '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def expire_key(self, key: str, ttl: int) -> None:
        """
        Set TTL on a key.

        :param key: Redis key
        :param ttl: Time to live in seconds
        :raises ConnectionError: If Redis operation fails
        """
        try:
            self._redis_client.expire(key, ttl)
        except Exception as e:
            raise ConnectionError(
                f"Failed to set TTL on key '{key}': {e}",
                host=cast(str, self._config['host']),
                port=cast(int, self._config['port']),
            ) from e

    def get_info(self) -> dict[str, Any]:
        """
        Get Redis/Dragonfly server information.

        :returns: Server information dictionary
        """
        try:
            info = cast(dict[str, Any], self._redis_client.info())
            return {
                'redis_version': info.get('redis_version', 'unknown'),
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory', 0),
                'used_memory_human': info.get('used_memory_human', 'unknown'),
                'keyspace_hits': info.get('keyspace_hits', 0),
                'keyspace_misses': info.get('keyspace_misses', 0),
                'is_dragonfly': self._is_dragonfly,
                'serializer': 'msgpack',
            }
        except Exception as e:
            return {'error': str(e), 'serializer': 'msgpack'}

    def get_client_info(self) -> dict[str, Any]:
        """
        Get client configuration information.

        :returns: Client configuration dictionary
        """
        return {
            'host': self._config['host'],
            'port': self._config['port'],
            'db': self._config['db'],
            'max_connections': self._config['max_connections'],
            'is_dragonfly': self._is_dragonfly,
            'serializer': 'msgpack',
            'keepalive': self._config['socket_keepalive'],
        }

    def close(self) -> None:
        """Close connection pool."""
        try:
            if self._connection_pool:
                self._connection_pool.disconnect()
                logger.debug('Connection pool closed')
        except Exception as e:
            logger.warning(f'Failed to close connection pool: {e}')

    def __enter__(self) -> 'RedisClient':
        """Context manager entry."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit."""
        self.close()
