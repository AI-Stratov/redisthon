"""
Integration tests against a real Redis or Dragonfly server.

Run with: pytest tests/integration
"""

import os
from datetime import UTC, datetime

from telethon import TelegramClient
from telethon.crypto import AuthKey
from telethon.tl.types import InputDocument, InputPeerUser, User
from telethon.tl.types.updates import State

from redisthon import RedisSession


def open_session(server, key_prefix, name='s', **kwargs):
    return RedisSession(name, key_prefix=key_prefix, **server, **kwargs)


def test_auth_key_and_dc_persist(server, key_prefix):
    key = AuthKey(data=os.urandom(256))

    with open_session(server, key_prefix) as session:
        # The sequence TelegramClient runs on connect
        session.set_dc(2, '149.154.167.51', 443)
        session.auth_key = key
        session.save()

    with open_session(server, key_prefix) as session:
        assert session.dc_id == 2
        assert session.server_address == '149.154.167.51'
        assert session.port == 443
        assert session.auth_key.key == key.key


def test_telegram_client_sets_default_dc(server, key_prefix):
    """TelegramClient() picks a default DC and saves the session."""
    session = open_session(server, key_prefix)
    TelegramClient(session, api_id=1, api_hash='0' * 32)

    with open_session(server, key_prefix) as reloaded:
        assert reloaded.dc_id == session.dc_id
        assert reloaded.server_address == session.server_address
    session.close()


def test_sessions_are_isolated_by_name(server, key_prefix):
    with open_session(server, key_prefix, name='a') as a:
        a.set_dc(1, '1.1.1.1', 443)
    with open_session(server, key_prefix, name='b') as b:
        assert b.dc_id != 1


def test_entities_resolve_by_id_username_phone_and_name(server, key_prefix):
    user = User(
        id=1001, access_hash=2002, username='Alice', phone='15550001', first_name='Al'
    )
    with open_session(server, key_prefix) as session:
        session.process_entities([user])

    with open_session(server, key_prefix) as session:
        expected = InputPeerUser(1001, 2002)
        assert session.get_input_entity(1001) == expected
        assert session.get_input_entity('alice') == expected
        assert session.get_input_entity('+15550001') == expected
        assert session.get_entity_rows_by_name('Al') == (1001, 2002)


def test_save_entities_false_stores_nothing(server, key_prefix):
    with open_session(server, key_prefix, save_entities=False) as session:
        session.process_entities([User(id=1001, access_hash=2002)])
        assert session.get_statistics()['entities_count'] == 0


def test_update_states_persist(server, key_prefix):
    date = datetime(2025, 1, 1, tzinfo=UTC)
    with open_session(server, key_prefix) as session:
        session.set_update_state(
            0, State(pts=10, qts=2, date=date, seq=3, unread_count=0)
        )
        session.set_update_state(
            777, State(pts=5, qts=0, date=date, seq=0, unread_count=0)
        )

    with open_session(server, key_prefix) as session:
        assert session.get_update_state(0).pts == 10
        states = dict(session.get_update_states())
        assert set(states) == {0, 777}
        assert states[777].pts == 5
        assert states[0].date == date


def test_sent_files_persist(server, key_prefix):
    doc = InputDocument(id=1, access_hash=2, file_reference=b'\x01\x02')
    with open_session(server, key_prefix) as session:
        session.cache_file(b'\xaa' * 16, 1234, doc)

    with open_session(server, key_prefix) as session:
        assert session.get_file(b'\xaa' * 16, 1234, InputDocument) == doc
        assert session.get_file(b'\xaa' * 16, 9999, InputDocument) is None


def test_ttl_is_applied(server, key_prefix):
    with open_session(server, key_prefix, ttl_seconds=120) as session:
        session.set_dc(2, '149.154.167.51', 443)
        session.process_entities([User(id=1, access_hash=2)])
        conn = session._client._redis_client
        assert 0 < conn.ttl(session._session_key) <= 120
        assert 0 < conn.ttl(session._entities_key) <= 120


def test_zero_ttl_means_no_expiry(server, key_prefix):
    with open_session(server, key_prefix, ttl_seconds=0) as session:
        session.set_dc(2, '149.154.167.51', 443)
        assert session._client._redis_client.ttl(session._session_key) == -1


def test_health_info_and_statistics(server, key_prefix):
    with open_session(server, key_prefix) as session:
        session.set_dc(2, '149.154.167.51', 443)
        session.process_entities([User(id=1, access_hash=2)])

        health = session.get_health_info()
        assert health['connection_healthy'] is True
        assert health['server_info']['redis_version'] != 'unknown'

        stats = session.get_statistics()
        assert stats['session_exists'] is True
        assert stats['entities_count'] == 1
        assert stats['dc_id'] == 2
