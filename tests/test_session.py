"""
Tests for RedisSession core functionality.
"""

from datetime import datetime, timezone

import pytest
from telethon.tl.types import InputPhoto
from telethon.tl.types.updates import State

from redisthon import RedisSession
from redisthon.exceptions import SessionError


class TestRedisSessionInitialization:
    """Test session initialization and configuration."""

    def test_init_with_string_name(self, mock_redis_client):
        """Test initialization with string session name."""
        session = RedisSession('test_session', redis_client=mock_redis_client)
        assert session.session_name == 'test_session'
        assert session.save_entities is True

    def test_init_with_bytes_name(self, mock_redis_client):
        """Test initialization with bytes session name."""
        session = RedisSession(b'test_session', redis_client=mock_redis_client)
        assert session.session_name == 'test_session'

    def test_init_invalid_name_type(self):
        """Test initialization with invalid session name type."""
        with pytest.raises(SessionError, match="Session name must be a string or bytes"):
            RedisSession(123)

    def test_key_generation(self, mock_redis_client):
        """Test Redis key generation."""
        session = RedisSession('test_session', redis_client=mock_redis_client)
        assert session._session_key == 'redisthon:session:test_session:data'
        assert session._entities_key == 'redisthon:session:test_session:entities'
        assert session._update_states_key == 'redisthon:session:test_session:update_states'
        assert session._sent_files_key == 'redisthon:session:test_session:sent_files'


class TestSessionDataManagement:
    """Test session data save/load operations."""

    def test_save_session_without_dc(self, redis_session):
        """Test that save does nothing without DC information."""
        redis_session.save()
        redis_session._client.set_key.assert_not_called()

    def test_save_session_with_dc(self, redis_session):
        """Test saving session with DC information."""
        redis_session.set_dc(2, 'test.telegram.org', 443)

        redis_session._client.set_key.assert_called()
        call_args = redis_session._client.set_key.call_args
        key, data, ttl = call_args[0]

        assert key == redis_session._session_key
        assert data['dc_id'] == 2
        assert data['server_address'] == 'test.telegram.org'
        assert data['port'] == 443

    def test_load_session_data(self, mock_redis_client, session_data):
        """Test loading existing session data."""
        mock_redis_client.get_key.return_value = session_data

        session = RedisSession('test_session', redis_client=mock_redis_client)

        assert session.dc_id == 2
        assert session.server_address == 'test.telegram.org'
        assert session.port == 443

    def test_clone_session(self, redis_session):
        """Test session cloning."""
        redis_session.set_dc(2, 'test.telegram.org', 443)

        cloned = redis_session.clone()

        assert cloned.dc_id == 2
        assert cloned.server_address == 'test.telegram.org'
        assert cloned.port == 443
        assert cloned.session_name == 'test_session_clone'


class TestEntityManagement:
    """Test entity caching and retrieval."""

    def test_get_entity_by_id_found(self, redis_session, entity_data):
        """Test getting entity by ID when found."""
        redis_session._client.hash_get.return_value = entity_data

        result = redis_session.get_entity_rows_by_id(123456789)

        assert len(result) == 1
        assert result[0] == (123456789, 987654321)
        redis_session._client.hash_get.assert_called_with(
            redis_session._entities_key,
            '123456789'
        )

    def test_get_entity_by_id_not_found(self, redis_session):
        """Test getting entity by ID when not found."""
        redis_session._client.hash_get.return_value = None

        result = redis_session.get_entity_rows_by_id(123456789)

        assert result == []

    def test_get_entity_by_username(self, redis_session, entity_data):
        """Test getting entity by username."""
        redis_session._client.hash_scan.return_value = [('123456789', entity_data)]

        result = redis_session.get_entity_rows_by_username('test_user')

        assert len(result) == 1
        assert result[0] == (123456789, 987654321)

    def test_get_entity_by_phone(self, redis_session, entity_data):
        """Test getting entity by phone number."""
        redis_session._client.hash_scan.return_value = [('123456789', entity_data)]

        result = redis_session.get_entity_rows_by_phone('+1234567890')

        assert len(result) == 1
        assert result[0] == (123456789, 987654321)


class TestUpdateStateManagement:
    """Test update state operations."""

    def test_set_update_state(self, redis_session):
        """Test setting update state."""
        state = State(
            pts=100,
            qts=50,
            date=datetime.now(timezone.utc),
            seq=25,
            unread_count=3
        )

        redis_session.set_update_state(123456789, state)

        redis_session._client.hash_set.assert_called()
        call_args = redis_session._client.hash_set.call_args
        key, field, data = call_args[0]

        assert key == redis_session._update_states_key
        assert field == '123456789'
        assert data['pts'] == 100
        assert data['qts'] == 50
        assert data['seq'] == 25
        assert data['unread_count'] == 3

    def test_get_update_state_found(self, redis_session):
        """Test getting update state when found."""
        state_data = {
            'entity_id': 123456789,
            'pts': 100,
            'qts': 50,
            'date': '2025-08-23T19:00:00+00:00',
            'seq': 25,
            'unread_count': 3,
        }
        redis_session._client.hash_get.return_value = state_data

        result = redis_session.get_update_state(123456789)

        assert result is not None
        assert result.pts == 100
        assert result.qts == 50
        assert result.seq == 25
        assert result.unread_count == 3

    def test_get_update_state_not_found(self, redis_session):
        """Test getting update state when not found."""
        redis_session._client.hash_get.return_value = None

        result = redis_session.get_update_state(123456789)

        assert result is None


class TestFileCaching:
    """Test file caching operations."""

    def test_cache_photo_file(self, redis_session):
        """Test caching photo file."""
        md5_digest = b'test_md5_hash_here'
        file_size = 1024
        photo = InputPhoto(id=123, access_hash=456, file_reference=b'test_ref')

        redis_session.cache_file(md5_digest, file_size, photo)

        redis_session._client.hash_set.assert_called()
        call_args = redis_session._client.hash_set.call_args
        key, field, data = call_args[0]

        assert key == redis_session._sent_files_key
        assert field == f'{md5_digest.hex()}_{file_size}'
        assert data['type'] == 'photo'
        assert data['id'] == 123
        assert data['access_hash'] == 456

    def test_get_cached_photo(self, redis_session):
        """Test getting cached photo file."""
        file_data = {
            'id': 123,
            'access_hash': 456,
            'file_reference': 'test_ref'.encode().hex(),
            'type': 'photo',
        }
        redis_session._client.hash_get.return_value = file_data

        md5_digest = b'test_md5_hash_here'
        file_size = 1024

        result = redis_session.get_file(md5_digest, file_size, InputPhoto)

        assert result is not None
        assert isinstance(result, InputPhoto)
        assert result.id == 123
        assert result.access_hash == 456


class TestSessionProperties:
    """Test session properties and attributes."""

    def test_session_properties(self, redis_session):
        """Test session property accessors."""
        redis_session.set_dc(2, 'test.telegram.org', 443)

        assert redis_session.dc_id == 2
        assert redis_session.server_address == 'test.telegram.org'
        assert redis_session.port == 443
        assert redis_session.takeout_id is None

    def test_context_manager(self, mock_redis_client):
        """Test context manager functionality."""
        with RedisSession('test_session', redis_client=mock_redis_client) as session:
            assert session.session_name == 'test_session'

        mock_redis_client.close.assert_called_once()


class TestHealthAndStatistics:
    """Test health monitoring and statistics."""

    def test_get_health_info(self, redis_session):
        """Test health information retrieval."""
        health = redis_session.get_health_info()

        assert health['session_name'] == 'test_session'
        assert health['connection_healthy'] is True
        assert 'server_info' in health
        assert 'client_info' in health
        assert 'keys' in health
        assert 'settings' in health

    def test_get_statistics(self, redis_session):
        """Test statistics retrieval."""
        redis_session._client.key_exists.return_value = True
        redis_session._client.hash_len.return_value = 5
        redis_session.set_dc(2, 'test.telegram.org', 443)

        stats = redis_session.get_statistics()

        assert stats['session_name'] == 'test_session'
        assert stats['session_exists'] is True
        assert stats['entities_count'] == 5
        assert stats['dc_id'] == 2


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_load_session_with_invalid_auth_key(self, mock_redis_client):
        """Test loading session with invalid auth key."""
        session_data = {
            'dc_id': 2,
            'server_address': 'test.telegram.org',
            'port': 443,
            'auth_key': 'invalid_base64!',  # Invalid base64
        }
        mock_redis_client.get_key.return_value = session_data

        # Should not raise exception, just log warning
        session = RedisSession('test_session', redis_client=mock_redis_client)
        assert session.auth_key is None

    def test_entity_operations_with_client_errors(self, redis_session):
        """Test entity operations when Redis client raises exceptions."""
        redis_session._client.hash_get.side_effect = Exception("Redis error")

        # Should not raise, just return empty results
        result = redis_session.get_entity_rows_by_id(123456789)
        assert result == []

    def test_save_session_handles_errors_gracefully(self, redis_session):
        """Test that save handles Redis errors gracefully."""
        redis_session._client.set_key.side_effect = Exception("Redis error")
        redis_session.set_dc(2, 'test.telegram.org', 443)

        # Should raise SessionError with proper context
        with pytest.raises(SessionError):
            redis_session.save()
