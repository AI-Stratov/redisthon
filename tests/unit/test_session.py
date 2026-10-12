"""
Unit tests for RedisSession.

Behaviour is tested against fakeredis. Failure paths replace RedisClient with
a Mock that raises.
"""

import base64
import logging
import os
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from telethon import utils
from telethon.crypto import AuthKey
from telethon.sessions.memory import MemorySession
from telethon.tl.types import (
    Channel,
    ChatPhotoEmpty,
    InputDocument,
    InputPeerChannel,
    InputPeerUser,
    InputPhoto,
    User,
)
from telethon.tl.types.updates import State

from redisthon import RedisClient, RedisSession, __version__
from redisthon.exceptions import ConnectionError, SessionError

DATE = datetime(2025, 1, 1, tzinfo=UTC)
DATA_KEY = 'redisthon:session:test:data'
ENTITIES_KEY = 'redisthon:session:test:entities'
STATES_KEY = 'redisthon:session:test:update_states'
FILES_KEY = 'redisthon:session:test:sent_files'


def make_state(pts: int = 1) -> State:
    return State(pts=pts, qts=2, date=DATE, seq=3, unread_count=0)


def make_photo() -> InputPhoto:
    return InputPhoto(id=1, access_hash=2, file_reference=b'')


def make_channel(channel_id: int, access_hash: int) -> Channel:
    return Channel(
        id=channel_id,
        title='News',
        photo=ChatPhotoEmpty(),
        date=DATE,
        access_hash=access_hash,
    )


@pytest.fixture
def failing_client() -> Mock:
    """RedisClient that loads an empty session and then fails every call."""
    client = Mock(spec=RedisClient)
    client.get_key.return_value = None
    error = ConnectionError('down', host='localhost', port=6379)
    for name in (
        'set_key',
        'expire_keys',
        'expire_key',
        'delete_keys',
        'scan_keys',
        'hash_get',
        'hash_set_many',
        'hash_scan',
        'hash_len',
        'key_exists',
    ):
        getattr(client, name).side_effect = error
    return client


class TestInit:
    def test_bytes_name(self, client):
        assert RedisSession(b'abc', redis_client=client).session_name == 'abc'

    def test_invalid_name(self):
        with pytest.raises(SessionError, match='string or bytes'):
            RedisSession(123)  # type: ignore[arg-type]

    def test_key_names(self, make_session):
        session = make_session('acc', key_prefix='app')
        assert session.get_health_info()['keys'] == {
            'session': 'app:acc:data',
            'entities': 'app:acc:entities',
            'update_states': 'app:acc:update_states',
            'sent_files': 'app:acc:sent_files',
        }

    def test_builds_own_client_from_settings(self):
        with patch('redisthon.session.RedisClient') as client_cls:
            client_cls.return_value.get_key.return_value = None
            RedisSession('s', host='h', port=1, db=2, is_dragonfly=True)

        kwargs = client_cls.call_args.kwargs
        assert kwargs['host'] == 'h'
        assert kwargs['port'] == 1
        assert kwargs['db'] == 2
        assert kwargs['is_dragonfly'] is True

    def test_fresh_session_is_empty(self, session):
        assert session.dc_id == 0
        assert session.server_address is None
        assert session.auth_key is None
        assert session.takeout_id is None


class TestSaveAndLoad:
    def test_round_trip(self, make_session):
        key = AuthKey(data=os.urandom(256))
        session = make_session()
        session.set_dc(2, '149.154.167.51', 443)
        session.auth_key = key
        session.takeout_id = 7
        session.save()

        loaded = make_session()
        assert loaded.dc_id == 2
        assert loaded.server_address == '149.154.167.51'
        assert loaded.port == 443
        assert loaded.auth_key.key == key.key
        assert loaded.takeout_id == 7

    def test_stored_document(self, session, client):
        key = AuthKey(data=os.urandom(256))
        session.set_dc(2, '1.2.3.4', 443)
        session.auth_key = key
        session.save()

        data = client.get_key(DATA_KEY)
        assert data['session_name'] == 'test'
        assert base64.b64decode(data['auth_key']) == key.key
        assert data['version'] == __version__

    def test_session_without_auth_key(self, make_session):
        make_session().set_dc(2, '1.2.3.4', 443)
        assert make_session().auth_key is None

    def test_save_without_dc_writes_nothing(self, session, fake_redis):
        session.save()
        assert fake_redis.keys() == []

    def test_unreadable_auth_key_is_ignored(self, make_session, client, caplog):
        client.set_key(DATA_KEY, {'dc_id': 2, 'auth_key': 'not base64!'})

        with caplog.at_level(logging.WARNING):
            session = make_session()

        assert session.dc_id == 2
        assert session.auth_key is None
        assert 'unreadable auth key' in caplog.text

    def test_non_map_document_raises(self, make_session, client):
        client.set_key(DATA_KEY, [1, 2])
        with pytest.raises(SessionError, match='expected a map, got list'):
            make_session()

    def test_load_error_raises(self, failing_client):
        failing_client.get_key.side_effect = ConnectionError('down')
        with pytest.raises(SessionError, match='Failed to load') as exc_info:
            RedisSession('s', redis_client=failing_client)
        assert exc_info.value.session_name == 's'

    def test_save_error_raises(self, failing_client):
        session = RedisSession('s', redis_client=failing_client)
        with pytest.raises(SessionError, match='Failed to save'):
            session.set_dc(2, '1.2.3.4', 443)


class TestTTL:
    def test_save_refreshes_ttl_on_all_keys(self, make_session, fake_redis):
        session = make_session(ttl_seconds=60)
        session.process_entities([User(id=1, access_hash=2)])
        session.set_update_state(0, make_state())
        session.cache_file(b'm', 1, make_photo())
        for key in fake_redis.scan_iter():
            fake_redis.persist(key)

        session.set_dc(2, '1.2.3.4', 443)

        keys = fake_redis.keys()
        assert len(keys) == 4
        assert all(0 < fake_redis.ttl(key) <= 60 for key in keys)

    def test_cache_writes_set_ttl(self, make_session, fake_redis):
        make_session(ttl_seconds=60).process_entities([User(id=1, access_hash=2)])
        assert 0 < fake_redis.ttl(ENTITIES_KEY) <= 60

    def test_zero_ttl_disables_expiry(self, make_session, fake_redis):
        session = make_session(ttl_seconds=0)
        session.process_entities([User(id=1, access_hash=2)])
        session.set_dc(2, '1.2.3.4', 443)

        assert [fake_redis.ttl(key) for key in fake_redis.scan_iter()] == [-1, -1]


class TestEntities:
    def test_resolve_by_id_username_phone_and_name(self, make_session):
        user = User(
            id=10, access_hash=20, username='Alice', phone='155', first_name='Al'
        )
        make_session().process_entities([user])

        session = make_session()
        expected = InputPeerUser(10, 20)
        assert session.get_input_entity(10) == expected
        assert session.get_input_entity('alice') == expected
        assert session.get_input_entity('+155') == expected
        assert session.get_input_entity('Al') == expected

    def test_resolve_unmarked_channel_id(self, session):
        session.process_entities([make_channel(555, 99)])

        marked_id = utils.get_peer_id(InputPeerChannel(555, 99))
        assert session.get_entity_rows_by_id(555, exact=False) == (marked_id, 99)
        assert session.get_input_entity(555) == InputPeerChannel(555, 99)

    def test_unknown_entity(self, session):
        assert session.get_entity_rows_by_id(1) is None
        assert session.get_entity_rows_by_id(1, exact=False) is None
        assert session.get_entity_rows_by_username('nobody') is None
        with pytest.raises(ValueError, match='Could not find input entity'):
            session.get_input_entity(1)

    def test_save_entities_false(self, make_session, fake_redis):
        make_session(save_entities=False).process_entities([User(id=1, access_hash=2)])
        assert fake_redis.keys() == []

    def test_object_without_entities(self, session, fake_redis):
        session.process_entities(object())
        assert fake_redis.keys() == []

    def test_malformed_entities_are_misses(self, session, client):
        client.hash_set(ENTITIES_KEY, '1', {'id': 1})
        client.hash_set(ENTITIES_KEY, '2', {'username': 'bob', 'id': 'x'})
        client.hash_set(ENTITIES_KEY, '3', 'not a map')

        assert session.get_entity_rows_by_id(1) is None
        assert session.get_entity_rows_by_username('bob') is None


class TestUpdateStates:
    def test_round_trip(self, make_session):
        writer = make_session()
        writer.set_update_state(0, make_state(pts=10))
        writer.set_update_state(-100555, make_state(pts=5))

        session = make_session()
        assert session.get_update_state(0) == make_state(pts=10)
        assert session.get_update_state(1) is None
        # TelegramClient.connect() iterates these as (entity_id, state) pairs
        assert dict(session.get_update_states()) == {
            0: make_state(pts=10),
            -100555: make_state(pts=5),
        }

    def test_state_without_date(self, session):
        state = State(pts=1, qts=0, date=None, seq=0, unread_count=0)
        session.set_update_state(1, state)
        assert session.get_update_state(1) == state

    def test_malformed_states_are_skipped(self, session, client):
        session.set_update_state(1, make_state())
        client.hash_set(STATES_KEY, 'x', {'pts': 1})
        client.hash_set(STATES_KEY, '2', {'pts': 1})

        assert dict(session.get_update_states()) == {1: make_state()}
        assert session.get_update_state(2) is None


class TestSentFiles:
    @pytest.mark.parametrize(
        'instance',
        [
            InputPhoto(id=1, access_hash=2, file_reference=b'\x01'),
            InputDocument(id=3, access_hash=4, file_reference=b''),
        ],
    )
    def test_round_trip(self, make_session, instance):
        make_session().cache_file(b'\xaa' * 16, 10, instance)

        session = make_session()
        assert session.get_file(b'\xaa' * 16, 10, type(instance)) == instance
        assert session.get_file(b'\xaa' * 16, 11, type(instance)) is None

    def test_photo_and_document_with_same_hash_do_not_collide(self, session):
        photo = make_photo()
        document = InputDocument(id=3, access_hash=4, file_reference=b'')
        session.cache_file(b'm', 1, photo)
        session.cache_file(b'm', 1, document)

        assert session.get_file(b'm', 1, InputPhoto) == photo
        assert session.get_file(b'm', 1, InputDocument) == document

    def test_unsupported_type(self, session, fake_redis, caplog):
        with caplog.at_level(logging.WARNING):
            session.cache_file(b'm', 1, User(id=1))

        assert session.get_file(b'm', 1, User) is None
        assert fake_redis.keys() == []
        assert 'Not caching file of type User' in caplog.text

    def test_malformed_entry_is_a_miss(self, session, client):
        client.hash_set(FILES_KEY, f'{b"m".hex()}_1_photo', {'id': 1})
        assert session.get_file(b'm', 1, InputPhoto) is None


class TestLifecycle:
    def test_clone_is_an_empty_memory_session(self, session, fake_redis):
        session.set_dc(2, '1.2.3.4', 443)
        cloned = session.clone()
        # Telethon does this for CDN connections
        cloned.set_dc(5, '5.5.5.5', 443)

        assert type(cloned) is MemorySession
        assert cloned.save_entities is True
        assert fake_redis.keys() == [DATA_KEY.encode()]

    def test_clone_into_instance(self, session):
        target = MemorySession()
        assert session.clone(target) is target

    def test_delete_removes_all_keys(self, session, fake_redis):
        session.set_dc(2, '1.2.3.4', 443)
        session.process_entities([User(id=1, access_hash=2)])

        session.delete()

        assert fake_redis.keys() == []

    def test_delete_failure_is_logged(self, failing_client, caplog):
        session = RedisSession('s', redis_client=failing_client)
        with caplog.at_level(logging.ERROR):
            session.delete()
        assert "Failed to delete session 's'" in caplog.text

    def test_list_sessions(self, make_session):
        for name in ('b', 'a:with:colons'):
            make_session(name).set_dc(2, '1.2.3.4', 443)
        make_session('c', key_prefix='other').set_dc(2, '1.2.3.4', 443)

        assert make_session('unsaved').list_sessions() == ['a:with:colons', 'b']

    def test_list_sessions_failure(self, failing_client):
        session = RedisSession('s', redis_client=failing_client)
        assert session.list_sessions() == ['s']

    def test_close_leaves_injected_client_open(self):
        client = Mock(spec=RedisClient)
        client.get_key.return_value = None

        with RedisSession('s', redis_client=client):
            pass

        client.close.assert_not_called()

    def test_close_closes_own_client(self):
        with patch('redisthon.session.RedisClient') as client_cls:
            client_cls.return_value.get_key.return_value = None
            with RedisSession('s'):
                pass

        client_cls.return_value.close.assert_called_once()


class TestCacheFailures:
    """Cache reads and writes never raise; Telethon falls back to the network."""

    def test_reads_are_misses(self, failing_client, caplog):
        session = RedisSession('s', redis_client=failing_client)

        with caplog.at_level(logging.WARNING):
            assert session.get_entity_rows_by_id(1) is None
            assert session.get_entity_rows_by_username('a') is None
            assert session.get_update_state(0) is None
            assert list(session.get_update_states()) == []
            assert session.get_file(b'm', 1, InputPhoto) is None
        assert 'Failed to read' in caplog.text

    def test_writes_are_logged(self, failing_client, caplog):
        session = RedisSession('s', redis_client=failing_client)

        with caplog.at_level(logging.WARNING):
            session.process_entities([User(id=1, access_hash=2)])
            session.set_update_state(0, make_state())
            session.cache_file(b'm', 1, make_photo())
        assert caplog.text.count('Failed to write') == 3


class TestDiagnostics:
    def test_health_info(self, session):
        health = session.get_health_info()

        assert health['session_name'] == 'test'
        assert health['connection_healthy'] is True
        assert health['client_info']['serializer'] == 'msgpack'
        assert health['settings'] == {'ttl_seconds': 86400 * 30, 'save_entities': True}

    def test_statistics(self, session):
        session.set_dc(2, '1.2.3.4', 443)
        session.auth_key = AuthKey(data=os.urandom(256))
        session.process_entities([User(id=1, access_hash=2), User(id=3, access_hash=4)])

        assert session.get_statistics() == {
            'session_name': 'test',
            'session_exists': True,
            'entities_count': 2,
            'update_states_count': 0,
            'sent_files_count': 0,
            'has_auth_key': True,
            'dc_id': 2,
        }

    def test_statistics_error(self, failing_client):
        stats = RedisSession('s', redis_client=failing_client).get_statistics()
        assert stats == {'session_name': 's', 'error': 'down'}
