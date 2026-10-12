"""
Unit tests for RedisClient.

Behaviour is tested against fakeredis. Failure paths use a Mock in place of
redis.Redis, since fakeredis does not fail on demand.
"""

import base64
import logging
from unittest.mock import Mock, patch

import fakeredis
import msgpack
import pytest
import redis

from redisthon import RedisClient
from redisthon.exceptions import (
    ConfigurationError,
    ConnectionError,
    SerializationError,
)


@pytest.fixture
def broken_redis() -> Mock:
    """A redis.Redis stand-in whose every command fails."""
    mock = Mock(spec=redis.Redis)
    error = redis.ConnectionError('down')
    for name in (
        'set',
        'get',
        'exists',
        'expire',
        'delete',
        'scan_iter',
        'hset',
        'hget',
        'hscan_iter',
        'hlen',
        'ping',
        'info',
    ):
        getattr(mock, name).side_effect = error
    mock.pipeline.return_value.execute.side_effect = error
    return mock


class TestInitialization:
    def test_builds_pool_from_settings(self):
        with patch('redisthon.client.redis.ConnectionPool') as pool:
            client = RedisClient(
                host='h', port=1, db=2, username='u', password='p', max_connections=7
            )

        kwargs = pool.call_args.kwargs
        assert kwargs['host'] == 'h'
        assert kwargs['port'] == 1
        assert kwargs['db'] == 2
        assert kwargs['username'] == 'u'
        assert kwargs['password'] == 'p'
        assert kwargs['max_connections'] == 7
        assert kwargs['decode_responses'] is False
        assert client.get_client_info() == {
            'host': 'h',
            'port': 1,
            'db': 2,
            'max_connections': 7,
            'is_dragonfly': False,
            'serializer': 'msgpack',
            'keepalive': True,
        }

    def test_no_username_by_default(self):
        with patch('redisthon.client.redis.ConnectionPool') as pool:
            RedisClient()

        assert 'username' not in pool.call_args.kwargs

    def test_dragonfly_skips_db(self):
        with patch('redisthon.client.redis.ConnectionPool') as pool:
            client = RedisClient(is_dragonfly=True, db=3)

        assert 'db' not in pool.call_args.kwargs
        assert client.get_client_info()['db'] == 0
        assert client.get_client_info()['is_dragonfly'] is True

    def test_invalid_pool_settings(self):
        with (
            patch(
                'redisthon.client.redis.ConnectionPool',
                side_effect=ValueError('bad'),
            ),
            pytest.raises(ConfigurationError, match='bad'),
        ):
            RedisClient()

    def test_existing_client_is_used_as_is(self, fake_redis):
        with patch('redisthon.client.redis.ConnectionPool') as pool:
            client = RedisClient(redis_client=fake_redis)

        pool.assert_not_called()
        client.set_key('k', 1)
        assert fake_redis.exists('k')


class TestSerialization:
    def test_round_trip(self, client):
        data = {'text': 'x', 'number': 1, 'raw': b'\x00\xff', 'list': [1, 2]}
        assert client.deserialize(client.serialize(data)) == data

    def test_unserializable_value(self, client):
        with pytest.raises(SerializationError, match='Failed to serialize'):
            client.serialize(object())

    def test_invalid_msgpack(self, client):
        with pytest.raises(SerializationError, match='Failed to deserialize'):
            client.deserialize(b'\xc1')


class TestKeys:
    def test_set_and_get(self, client, fake_redis):
        client.set_key('k', {'a': 1})

        assert client.get_key('k') == {'a': 1}
        assert fake_redis.ttl('k') == -1

    def test_set_with_ttl(self, client, fake_redis):
        client.set_key('k', 1, ttl=300)
        assert 0 < fake_redis.ttl('k') <= 300

    @pytest.mark.parametrize('ttl', [0, -1])
    def test_non_positive_ttl_means_no_expiry(self, client, fake_redis, ttl):
        client.set_key('k', 1, ttl=ttl)
        assert fake_redis.ttl('k') == -1

    def test_get_missing_key(self, client):
        assert client.get_key('missing') is None

    def test_get_text_response_is_rejected(self):
        client = RedisClient(redis_client=fakeredis.FakeRedis(decode_responses=True))
        client._redis_client.set('k', 'text')

        with pytest.raises(SerializationError, match='decode_responses=False'):
            client.get_key('k')

    def test_get_corrupt_value(self, client, fake_redis):
        fake_redis.set('k', b'\xc1')
        with pytest.raises(SerializationError):
            client.get_key('k')

    def test_key_exists(self, client):
        assert client.key_exists('k') is False
        client.set_key('k', 1)
        assert client.key_exists('k') is True

    def test_expire_key(self, client, fake_redis):
        client.set_key('k', 1)
        client.expire_key('k', 60)
        assert 0 < fake_redis.ttl('k') <= 60

    def test_expire_keys(self, client, fake_redis):
        client.set_key('a', 1)
        client.hash_set('b', 'f', 1)
        client.expire_keys(['a', 'b', 'missing'], 60)

        assert 0 < fake_redis.ttl('a') <= 60
        assert 0 < fake_redis.ttl('b') <= 60

    def test_delete_keys(self, client):
        client.set_key('a', 1)
        client.set_key('b', 1)

        assert client.delete_keys('a', 'b', 'missing') == 2
        assert client.key_exists('a') is False

    def test_delete_no_keys(self, client):
        assert client.delete_keys() == 0

    def test_scan_keys(self, client):
        for key in ('p:a:data', 'p:b:data', 'p:a:entities', 'q:c:data'):
            client.set_key(key, 1)

        assert sorted(client.scan_keys('p:*:data')) == ['p:a:data', 'p:b:data']


class TestHashes:
    def test_set_and_get(self, client):
        client.hash_set('h', 'f', {'a': 1})
        assert client.hash_get('h', 'f') == {'a': 1}

    def test_values_are_base64_msgpack(self, client, fake_redis):
        client.hash_set('h', 'f', {'a': 1})

        raw = fake_redis.hget('h', 'f')
        assert msgpack.unpackb(base64.b64decode(raw)) == {'a': 1}

    def test_set_many(self, client):
        client.hash_set_many('h', {'a': 1, 'b': [2]})

        assert client.hash_get('h', 'a') == 1
        assert client.hash_get('h', 'b') == [2]
        assert client.hash_len('h') == 2

    def test_set_many_empty_is_noop(self, client, fake_redis):
        client.hash_set_many('h', {})
        assert not fake_redis.exists('h')

    def test_get_missing_field(self, client):
        assert client.hash_get('h', 'missing') is None

    def test_get_value_that_is_not_base64(self, client, fake_redis):
        fake_redis.hset('h', 'f', b'\x00not base64')
        with pytest.raises(SerializationError, match='not base64'):
            client.hash_get('h', 'f')

    def test_scan(self, client):
        client.hash_set_many('h', {'a': 1, 'b': 2})
        assert sorted(client.hash_scan('h')) == [('a', 1), ('b', 2)]

    def test_scan_missing_hash(self, client):
        assert client.hash_scan('missing') == []

    def test_scan_skips_corrupt_values(self, client, fake_redis, caplog):
        client.hash_set('h', 'good', 1)
        fake_redis.hset('h', 'bad', b'!!')

        with caplog.at_level(logging.WARNING):
            assert client.hash_scan('h') == [('good', 1)]
        assert "corrupt field 'h:bad'" in caplog.text

    def test_scan_with_text_responses(self):
        client = RedisClient(redis_client=fakeredis.FakeRedis(decode_responses=True))
        client.hash_set('h', 'f', 1)

        assert client.hash_get('h', 'f') == 1
        assert client.hash_scan('h') == [('f', 1)]

    def test_len(self, client):
        assert client.hash_len('h') == 0
        client.hash_set('h', 'f', 1)
        assert client.hash_len('h') == 1


class TestRedisErrors:
    @pytest.mark.parametrize(
        ('call', 'message'),
        [
            (lambda c: c.set_key('k', 1), "Failed to set key 'k'"),
            (lambda c: c.set_key('k', 1, ttl=5), "Failed to set key 'k'"),
            (lambda c: c.get_key('k'), "Failed to get key 'k'"),
            (lambda c: c.key_exists('k'), "Failed to check key existence 'k'"),
            (lambda c: c.expire_key('k', 1), "Failed to set TTL on key 'k'"),
            (lambda c: c.expire_keys(['k'], 1), 'Failed to set TTL on keys'),
            (lambda c: c.delete_keys('k'), 'Failed to delete keys'),
            (lambda c: c.scan_keys('*'), "Failed to scan keys '\\*'"),
            (lambda c: c.hash_set('h', 'f', 1), "Failed to set hash field 'h:f'"),
            (lambda c: c.hash_set_many('h', {'f': 1}), 'Failed to set hash fields'),
            (lambda c: c.hash_get('h', 'f'), "Failed to get hash field 'h:f'"),
            (lambda c: c.hash_scan('h'), "Failed to scan hash 'h'"),
            (lambda c: c.hash_len('h'), "Failed to get hash length 'h'"),
        ],
    )
    def test_wrapped_as_connection_error(self, broken_redis, call, message):
        client = RedisClient(redis_client=broken_redis)

        with pytest.raises(ConnectionError, match=message) as exc_info:
            call(client)

        assert exc_info.value.host == 'localhost'
        assert exc_info.value.port == 6379
        assert isinstance(exc_info.value.__cause__, redis.RedisError)

    def test_serialization_error_is_not_masked(self, broken_redis):
        client = RedisClient(redis_client=broken_redis)
        with pytest.raises(SerializationError):
            client.set_key('k', object())

    def test_ping(self, client):
        assert client.ping() is True

    def test_ping_failure_returns_false(self, broken_redis, caplog):
        client = RedisClient(redis_client=broken_redis)

        with caplog.at_level(logging.WARNING):
            assert client.ping() is False
        assert 'Ping failed' in caplog.text


class TestInfo:
    def test_get_info(self):
        mock = Mock(spec=redis.Redis)
        mock.info.return_value = {
            'redis_version': '7.2.0',
            'connected_clients': 5,
            'used_memory_human': '1M',
        }
        info = RedisClient(redis_client=mock).get_info()

        assert info['redis_version'] == '7.2.0'
        assert info['connected_clients'] == 5
        assert info['used_memory_human'] == '1M'
        assert info['keyspace_hits'] == 0
        assert info['is_dragonfly'] is False

    def test_get_info_error(self, broken_redis):
        info = RedisClient(redis_client=broken_redis).get_info()
        assert info == {'error': 'down', 'serializer': 'msgpack'}


class TestClose:
    def test_context_manager_disconnects_own_pool(self):
        with patch('redisthon.client.redis.ConnectionPool') as pool, RedisClient():
            pass

        pool.return_value.disconnect.assert_called_once()

    def test_disconnects_on_error_inside_block(self):
        with (
            patch('redisthon.client.redis.ConnectionPool') as pool,
            pytest.raises(RuntimeError, match='boom'),
            RedisClient(),
        ):
            raise RuntimeError('boom')

        pool.return_value.disconnect.assert_called_once()

    def test_disconnect_failure_is_logged(self, caplog):
        with patch('redisthon.client.redis.ConnectionPool') as pool:
            pool.return_value.disconnect.side_effect = OSError('gone')
            client = RedisClient()

        with caplog.at_level(logging.WARNING):
            client.close()
        assert 'Failed to close connection pool' in caplog.text

    def test_external_client_is_left_open(self):
        external = Mock()
        RedisClient(redis_client=external).close()

        assert external.mock_calls == []
