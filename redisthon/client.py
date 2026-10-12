"""
Redis/Dragonfly client used by RedisSession.
"""

import base64
import binascii
import logging
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any

import msgpack
import redis
from redis.typing import EncodableT, FieldT

from .exceptions import ConfigurationError, ConnectionError, SerializationError

logger = logging.getLogger(__name__)


class RedisClient:
    """
    Redis/Dragonfly client with a connection pool and msgpack serialization.

    Plain keys hold msgpack bytes. Hash fields hold base64 text of msgpack
    bytes.

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
    :param redis_client: Existing Redis client to use. The caller keeps
        ownership: close() does not disconnect it.
    """

    __slots__ = (
        '_connection_pool',
        '_db',
        '_host',
        '_is_dragonfly',
        '_max_connections',
        '_port',
        '_redis_client',
        '_socket_keepalive',
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
        self._host = host
        self._port = port
        self._db = 0 if is_dragonfly else db
        self._max_connections = max_connections
        self._socket_keepalive = socket_keepalive
        self._is_dragonfly = is_dragonfly
        self._connection_pool: redis.ConnectionPool | None = None

        if redis_client is not None:
            self._redis_client = redis_client
            return

        pool_kwargs: dict[str, Any] = {
            'host': host,
            'port': port,
            'password': password,
            'socket_keepalive': socket_keepalive,
            'socket_keepalive_options': socket_keepalive_options or {},
            'health_check_interval': health_check_interval,
            'max_connections': max_connections,
            'socket_connect_timeout': connection_timeout,
            'socket_timeout': socket_timeout,
            'decode_responses': False,
        }
        # Dragonfly is always used with the default database
        if not is_dragonfly:
            pool_kwargs['db'] = db
        if username:
            pool_kwargs['username'] = username

        try:
            self._connection_pool = redis.ConnectionPool(**pool_kwargs)
        except (TypeError, ValueError) as e:
            raise ConfigurationError(
                f'Failed to setup connection pool: {e}', parameter='connection_pool'
            ) from e
        self._redis_client = redis.Redis(connection_pool=self._connection_pool)

    @contextmanager
    def _wrap_errors(self, action: str) -> Iterator[None]:
        """Re-raise redis-py errors as ConnectionError naming the operation."""
        try:
            yield
        except redis.RedisError as e:
            raise ConnectionError(
                f'Failed to {action}: {e}', host=self._host, port=self._port
            ) from e

    # Serialization

    def serialize(self, data: Any) -> bytes:
        """
        Serialize data using msgpack.

        :raises SerializationError: If the value cannot be packed
        """
        try:
            packed: bytes = msgpack.packb(data, use_bin_type=True)
        except (TypeError, ValueError, OverflowError) as e:
            raise SerializationError(
                f'Failed to serialize data: {e}', serializer='msgpack'
            ) from e
        return packed

    def deserialize(self, data: bytes) -> Any:
        """
        Deserialize msgpack bytes.

        :raises SerializationError: If the bytes are not valid msgpack
        """
        try:
            return msgpack.unpackb(data, raw=False)
        except (ValueError, TypeError, msgpack.UnpackException) as e:
            raise SerializationError(
                f'Failed to deserialize data: {e}', serializer='msgpack'
            ) from e

    def _encode_field(self, value: Any) -> str:
        return base64.b64encode(self.serialize(value)).decode('ascii')

    def _decode_field(self, raw: bytes | str) -> Any:
        try:
            packed = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as e:
            raise SerializationError(
                f'Hash value is not base64: {e}', serializer='msgpack'
            ) from e
        return self.deserialize(packed)

    # Plain keys

    def ping(self) -> bool:
        """Return True if the server answers PING."""
        try:
            return bool(self._redis_client.ping())
        except redis.RedisError as e:
            logger.warning('Ping failed: %s', e)
            return False

    def set_key(self, key: str, value: Any, ttl: int | None = None) -> None:
        """
        Store a value, with a TTL in seconds if ttl is positive.

        :raises SerializationError: If the value cannot be packed
        :raises ConnectionError: If the Redis command fails
        """
        payload = self.serialize(value)
        with self._wrap_errors(f"set key '{key}'"):
            self._redis_client.set(key, payload, ex=ttl if ttl and ttl > 0 else None)

    def get_key(self, key: str) -> Any | None:
        """
        Return the stored value, or None if the key does not exist.

        :raises SerializationError: If the stored bytes are not msgpack
        :raises ConnectionError: If the Redis command fails
        """
        with self._wrap_errors(f"get key '{key}'"):
            data = self._redis_client.get(key)
        if data is None:
            return None
        if not isinstance(data, bytes):
            raise SerializationError(
                f"Key '{key}' was read as text. Create the redis.Redis client "
                'with decode_responses=False.',
                serializer='msgpack',
            )
        return self.deserialize(data)

    def key_exists(self, key: str) -> bool:
        """:raises ConnectionError: If the Redis command fails"""
        with self._wrap_errors(f"check key existence '{key}'"):
            return bool(self._redis_client.exists(key))

    def expire_key(self, key: str, ttl: int) -> None:
        """:raises ConnectionError: If the Redis command fails"""
        with self._wrap_errors(f"set TTL on key '{key}'"):
            self._redis_client.expire(key, ttl)

    def expire_keys(self, keys: Iterable[str], ttl: int) -> None:
        """
        Set the same TTL on several keys in one round trip.

        :raises ConnectionError: If the Redis command fails
        """
        keys = list(keys)
        with self._wrap_errors(f'set TTL on keys {keys}'):
            pipe = self._redis_client.pipeline(transaction=False)
            for key in keys:
                pipe.expire(key, ttl)
            pipe.execute()

    def delete_keys(self, *keys: str) -> int:
        """
        Delete keys and return how many existed.

        :raises ConnectionError: If the Redis command fails
        """
        if not keys:
            return 0
        with self._wrap_errors(f'delete keys {list(keys)}'):
            return int(self._redis_client.delete(*keys))

    def scan_keys(self, match: str) -> list[str]:
        """
        Return all keys matching a glob pattern, using SCAN.

        :raises ConnectionError: If the Redis command fails
        """
        with self._wrap_errors(f"scan keys '{match}'"):
            return [
                key.decode() if isinstance(key, bytes) else key
                for key in self._redis_client.scan_iter(match=match)
            ]

    # Hashes

    def hash_set(self, key: str, field: str, value: Any) -> None:
        """
        Store one hash field.

        :raises SerializationError: If the value cannot be packed
        :raises ConnectionError: If the Redis command fails
        """
        encoded = self._encode_field(value)
        with self._wrap_errors(f"set hash field '{key}:{field}'"):
            self._redis_client.hset(key, field, encoded)

    def hash_set_many(self, key: str, values: Mapping[str, Any]) -> None:
        """
        Store several hash fields with one HSET.

        :raises SerializationError: If a value cannot be packed
        :raises ConnectionError: If the Redis command fails
        """
        if not values:
            return
        encoded: dict[FieldT, EncodableT] = {
            field: self._encode_field(value) for field, value in values.items()
        }
        with self._wrap_errors(f"set hash fields in '{key}'"):
            self._redis_client.hset(key, mapping=encoded)

    def hash_get(self, key: str, field: str) -> Any | None:
        """
        Return one hash field, or None if it does not exist.

        :raises SerializationError: If the stored value is corrupt
        :raises ConnectionError: If the Redis command fails
        """
        with self._wrap_errors(f"get hash field '{key}:{field}'"):
            raw = self._redis_client.hget(key, field)
        return None if raw is None else self._decode_field(raw)

    def hash_scan(self, key: str) -> list[tuple[str, Any]]:
        """
        Return all (field, value) pairs of a hash, using HSCAN.

        Corrupt values are logged and skipped.

        :raises ConnectionError: If the Redis command fails
        """
        results: list[tuple[str, Any]] = []
        with self._wrap_errors(f"scan hash '{key}'"):
            items = list(self._redis_client.hscan_iter(key))
        for raw_field, raw_value in items:
            field = raw_field.decode() if isinstance(raw_field, bytes) else raw_field
            try:
                results.append((field, self._decode_field(raw_value)))
            except SerializationError as e:
                logger.warning("Skipping corrupt field '%s:%s': %s", key, field, e)
        return results

    def hash_len(self, key: str) -> int:
        """:raises ConnectionError: If the Redis command fails"""
        with self._wrap_errors(f"get hash length '{key}'"):
            return int(self._redis_client.hlen(key))

    # Diagnostics

    def get_info(self) -> dict[str, Any]:
        """Return selected INFO fields, or {'error': ...} if INFO fails."""
        try:
            info = self._redis_client.info()
        except redis.RedisError as e:
            return {'error': str(e), 'serializer': 'msgpack'}
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

    def get_client_info(self) -> dict[str, Any]:
        """Return the client configuration."""
        return {
            'host': self._host,
            'port': self._port,
            'db': self._db,
            'max_connections': self._max_connections,
            'is_dragonfly': self._is_dragonfly,
            'serializer': 'msgpack',
            'keepalive': self._socket_keepalive,
        }

    def close(self) -> None:
        """Disconnect the pool this client created. A passed-in client is left open."""
        if self._connection_pool is None:
            return
        try:
            self._connection_pool.disconnect()
        except (redis.RedisError, OSError) as e:
            logger.warning('Failed to close connection pool: %s', e)
        else:
            logger.debug('Connection pool closed')

    def __enter__(self) -> 'RedisClient':
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
