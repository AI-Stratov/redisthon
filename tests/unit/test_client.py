"""
Unit tests for RedisClient. The redis-py client is replaced with mocks.
"""

import base64
from unittest.mock import Mock, patch

import msgpack
import pytest
import redis

from redisthon.client import RedisClient
from redisthon.exceptions import ConnectionError, SerializationError


def packed(value):
    return msgpack.packb(value, use_bin_type=True)


@pytest.fixture
def fake_redis():
    return Mock()


@pytest.fixture
def client(fake_redis):
    return RedisClient(redis_client=fake_redis)


class TestInitialization:
    def test_defaults(self):
        with patch('redisthon.client.ConnectionPool') as pool:
            client = RedisClient()

        kwargs = pool.call_args.kwargs
        assert kwargs['host'] == 'localhost'
        assert kwargs['port'] == 6379
        assert kwargs['db'] == 0
        assert kwargs['max_connections'] == 50
        assert kwargs['decode_responses'] is False
        assert 'username' not in kwargs
        assert client.get_client_info()['is_dragonfly'] is False

    def test_username_is_passed(self):
        with patch('redisthon.client.ConnectionPool') as pool:
            RedisClient(username='user', password='secret')

        assert pool.call_args.kwargs['username'] == 'user'
        assert pool.call_args.kwargs['password'] == 'secret'

    def test_dragonfly_skips_db(self):
        with patch('redisthon.client.ConnectionPool') as pool:
            client = RedisClient(is_dragonfly=True, port=6380, db=3)

        assert 'db' not in pool.call_args.kwargs
        assert client.get_client_info()['db'] == 0

    def test_existing_redis_client(self):
        existing = Mock(spec=redis.Redis)
        with patch('redisthon.client.ConnectionPool') as pool:
            client = RedisClient(redis_client=existing)

        pool.assert_not_called()
        assert client._redis_client is existing


class TestSerialization:
    def test_round_trip(self, client):
        data = {'text': 'x', 'number': 1, 'raw': b'\x00\xff', 'list': [1, 2]}
        assert client.deserialize(client.serialize(data)) == data

    def test_serialize_error(self, client):
        with pytest.raises(SerializationError, match='Failed to serialize'):
            client.serialize(object())

    def test_deserialize_error(self, client):
        with pytest.raises(SerializationError, match='Failed to deserialize'):
            client.deserialize(b'\xc1')


class TestKeys:
    def test_ping(self, client, fake_redis):
        fake_redis.ping.return_value = True
        assert client.ping() is True

    def test_ping_failure_returns_false(self, client, fake_redis):
        fake_redis.ping.side_effect = redis.ConnectionError('down')
        assert client.ping() is False

    def test_set_key_without_ttl(self, client, fake_redis):
        client.set_key('k', {'a': 1})
        fake_redis.set.assert_called_once_with('k', packed({'a': 1}))

    def test_set_key_with_ttl(self, client, fake_redis):
        client.set_key('k', {'a': 1}, ttl=300)
        fake_redis.setex.assert_called_once_with('k', 300, packed({'a': 1}))

    def test_get_key(self, client, fake_redis):
        fake_redis.get.return_value = packed({'a': 1})
        assert client.get_key('k') == {'a': 1}

    def test_get_missing_key(self, client, fake_redis):
        fake_redis.get.return_value = None
        assert client.get_key('k') is None

    def test_key_exists(self, client, fake_redis):
        fake_redis.exists.return_value = 1
        assert client.key_exists('k') is True

    def test_expire_key(self, client, fake_redis):
        client.expire_key('k', 60)
        fake_redis.expire.assert_called_once_with('k', 60)


class TestHashes:
    def test_hash_set_stores_base64(self, client, fake_redis):
        client.hash_set('h', 'f', {'a': 1})
        expected = base64.b64encode(packed({'a': 1})).decode()
        fake_redis.hset.assert_called_once_with('h', 'f', expected)

    def test_hash_get_missing_field(self, client, fake_redis):
        fake_redis.hget.return_value = None
        assert client.hash_get('h', 'f') is None

    def test_hash_scan_follows_cursor(self, client, fake_redis):
        def encoded(value):
            return base64.b64encode(packed(value))

        fake_redis.hscan.side_effect = [
            (7, {b'a': encoded(1), b'b': encoded(2)}),
            (0, {b'c': encoded(3)}),
        ]
        assert client.hash_scan('h') == [('a', 1), ('b', 2), ('c', 3)]
        assert fake_redis.hscan.call_count == 2

    def test_hash_scan_skips_corrupt_values(self, client, fake_redis):
        fake_redis.hscan.return_value = (
            0,
            {b'good': base64.b64encode(packed(1)), b'bad': b'not msgpack'},
        )
        assert client.hash_scan('h') == [('good', 1)]

    def test_hash_len(self, client, fake_redis):
        fake_redis.hlen.return_value = 4
        assert client.hash_len('h') == 4


class TestHashRoundTrip:
    """Values written by hash_set must be readable by hash_get and hash_scan."""

    @pytest.fixture
    def client(self):
        store: dict[bytes, bytes] = {}

        def hset(key, field, value):
            store[field.encode()] = value.encode() if isinstance(value, str) else value

        fake = Mock()
        fake.hset.side_effect = hset
        fake.hget.side_effect = lambda key, field: store.get(field.encode())
        fake.hscan.side_effect = lambda key, cursor: (0, dict(store))
        return RedisClient(redis_client=fake)

    def test_hash_get_reads_hash_set(self, client):
        client.hash_set('h', 'a', {'username': 'alice', 'id': 1})
        assert client.hash_get('h', 'a') == {'username': 'alice', 'id': 1}

    def test_hash_scan_reads_hash_set(self, client):
        client.hash_set('h', 'a', {'id': 1})
        client.hash_set('h', 'b', {'id': 2})
        assert sorted(client.hash_scan('h')) == [('a', {'id': 1}), ('b', {'id': 2})]


class TestErrors:
    @pytest.mark.parametrize(
        ('method', 'args', 'redis_method', 'message'),
        [
            ('set_key', ('k', 1), 'set', "Failed to set key 'k'"),
            ('get_key', ('k',), 'get', "Failed to get key 'k'"),
            ('hash_set', ('h', 'f', 1), 'hset', 'Failed to set hash field'),
            ('hash_get', ('h', 'f'), 'hget', 'Failed to get hash field'),
            ('hash_scan', ('h',), 'hscan', "Failed to scan hash 'h'"),
            ('hash_len', ('h',), 'hlen', 'Failed to get hash length'),
            ('key_exists', ('k',), 'exists', 'Failed to check key existence'),
            ('expire_key', ('k', 1), 'expire', 'Failed to set TTL'),
        ],
    )
    def test_redis_errors_are_wrapped(
        self, client, fake_redis, method, args, redis_method, message
    ):
        getattr(fake_redis, redis_method).side_effect = redis.ConnectionError('down')

        with pytest.raises(ConnectionError, match=message) as exc_info:
            getattr(client, method)(*args)

        assert exc_info.value.host == 'localhost'
        assert exc_info.value.port == 6379


class TestInfo:
    def test_get_info(self, client, fake_redis):
        fake_redis.info.return_value = {
            'redis_version': '7.2.0',
            'connected_clients': 5,
            'used_memory_human': '1M',
        }
        info = client.get_info()

        assert info['redis_version'] == '7.2.0'
        assert info['connected_clients'] == 5
        assert info['used_memory_human'] == '1M'
        assert info['is_dragonfly'] is False

    def test_get_info_error(self, client, fake_redis):
        fake_redis.info.side_effect = redis.ConnectionError('down')
        assert client.get_info() == {'error': 'down', 'serializer': 'msgpack'}

    def test_get_client_info(self):
        with patch('redisthon.client.ConnectionPool'):
            client = RedisClient(host='h', port=6380, max_connections=7)

        info = client.get_client_info()
        assert info['host'] == 'h'
        assert info['port'] == 6380
        assert info['max_connections'] == 7


class TestClose:
    def test_context_manager_disconnects_pool(self):
        with patch('redisthon.client.ConnectionPool') as pool:
            with RedisClient():
                pass

        pool.return_value.disconnect.assert_called_once()

    def test_context_manager_disconnects_on_error(self):
        with patch('redisthon.client.ConnectionPool') as pool:
            with pytest.raises(ValueError), RedisClient():
                raise ValueError

        pool.return_value.disconnect.assert_called_once()

    def test_close_leaves_external_client_alone(self, client, fake_redis):
        client.close()
        fake_redis.close.assert_not_called()
