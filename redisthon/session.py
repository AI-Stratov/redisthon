"""
Telethon session stored in Redis or Dragonfly.
"""

import base64
import binascii
import logging
from collections.abc import ItemsView
from datetime import UTC, datetime
from typing import Any

from telethon import utils
from telethon.crypto import AuthKey
from telethon.sessions.memory import MemorySession, _SentFileType
from telethon.tl.types import (
    InputDocument,
    InputPhoto,
    PeerChannel,
    PeerChat,
    PeerUser,
)
from telethon.tl.types.updates import State

from ._version import __version__
from .client import RedisClient
from .exceptions import RedisthonError, SessionError

logger = logging.getLogger(__name__)

EntityRow = tuple[int, int]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _entity_row(data: Any) -> EntityRow | None:
    """(id, access_hash) from a stored entity, or None if it is malformed."""
    try:
        return int(data['id']), int(data['access_hash'])
    except (KeyError, TypeError, ValueError):
        return None


def _state_to_dict(entity_id: int, state: State) -> dict[str, Any]:
    return {
        'entity_id': entity_id,
        'pts': state.pts,
        'qts': state.qts,
        'date': state.date.isoformat() if state.date else None,
        'seq': state.seq,
        'unread_count': state.unread_count,
        'updated_at': _now(),
    }


def _state_from_dict(data: Any) -> State | None:
    """State from a stored dict, or None if it is malformed."""
    try:
        date = data.get('date')
        return State(
            pts=data['pts'],
            qts=data['qts'],
            date=datetime.fromisoformat(date) if date else None,
            seq=data['seq'],
            unread_count=data['unread_count'],
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


class RedisSession(MemorySession):  # type: ignore[misc]
    """
    Redis/Dragonfly session storage for Telethon.

    Connection state (DC, auth key, takeout ID) lives in one key; entities,
    update states and sent files live in one hash each. Reads and writes of
    those caches never raise: a Redis failure is logged and treated as a miss,
    so Telethon falls back to asking Telegram.

    :param session_name: Unique session identifier
    :param host: Redis/Dragonfly server host
    :param port: Server port
    :param db: Database number (ignored for Dragonfly)
    :param password: Authentication password
    :param username: Authentication username
    :param is_dragonfly: Whether using Dragonfly instead of Redis
    :param redis_client: Existing RedisClient to use. The caller owns it:
        close() leaves it open so other sessions can keep using it.
    :param max_connections: Maximum connections in pool
    :param socket_keepalive: Enable TCP keepalive
    :param socket_keepalive_options: TCP keepalive settings
    :param connection_timeout: Connection timeout in seconds
    :param key_prefix: Prefix for all Redis keys
    :param ttl_seconds: TTL for all keys, refreshed on save (0 = no expiry)
    :param save_entities: Whether to cache entities
    :raises SessionError: If the stored session cannot be loaded
    """

    def __init__(
        self,
        session_name: str | bytes,
        *,
        # Redis connection settings
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0,
        password: str | None = None,
        username: str | None = None,
        is_dragonfly: bool = False,
        redis_client: RedisClient | None = None,
        # Connection settings
        max_connections: int = 50,
        socket_keepalive: bool = True,
        socket_keepalive_options: dict[str, Any] | None = None,
        connection_timeout: int = 5,
        # Session settings
        key_prefix: str = 'redisthon:session',
        ttl_seconds: int = 86400 * 30,
        save_entities: bool = True,
    ) -> None:
        if not isinstance(session_name, str | bytes):
            raise SessionError('Session name must be a string or bytes')

        super().__init__()

        self.session_name = (
            session_name if isinstance(session_name, str) else session_name.decode()
        )
        self.save_entities = save_entities
        self._ttl_seconds = ttl_seconds
        self._base_key_prefix = key_prefix

        self._owns_client = redis_client is None
        if redis_client is None:
            redis_client = RedisClient(
                host=host,
                port=port,
                db=db,
                password=password,
                username=username,
                max_connections=max_connections,
                socket_keepalive=socket_keepalive,
                socket_keepalive_options=socket_keepalive_options,
                connection_timeout=connection_timeout,
                is_dragonfly=is_dragonfly,
            )
        self._client = redis_client

        self._key_prefix = f'{key_prefix}:{self.session_name}'
        self._session_key = f'{self._key_prefix}:data'
        self._entities_key = f'{self._key_prefix}:entities'
        self._update_states_key = f'{self._key_prefix}:update_states'
        self._sent_files_key = f'{self._key_prefix}:sent_files'

        self._load_session_data()

    @property
    def _all_keys(self) -> tuple[str, str, str, str]:
        return (
            self._session_key,
            self._entities_key,
            self._update_states_key,
            self._sent_files_key,
        )

    @property
    def _cache_keys(self) -> tuple[str, str, str]:
        return self._entities_key, self._update_states_key, self._sent_files_key

    def _load_session_data(self) -> None:
        try:
            data = self._client.get_key(self._session_key)
        except RedisthonError as e:
            raise SessionError(
                f'Failed to load session data: {e}', session_name=self.session_name
            ) from e

        if data is None:
            logger.debug("No stored session for '%s'", self.session_name)
            return
        if not isinstance(data, dict):
            raise SessionError(
                f'Failed to load session data: expected a map, got {type(data).__name__}',
                session_name=self.session_name,
            )

        self._dc_id = data.get('dc_id') or 0
        self._server_address = data.get('server_address')
        self._port = data.get('port')
        self._takeout_id = data.get('takeout_id')
        self._auth_key = self._decode_auth_key(data.get('auth_key'))
        logger.debug("Loaded session '%s'", self.session_name)

    def _decode_auth_key(self, encoded: Any) -> AuthKey | None:
        if not encoded:
            return None
        try:
            return AuthKey(data=base64.b64decode(encoded, validate=True))
        except (binascii.Error, TypeError, ValueError) as e:
            logger.warning(
                "Ignoring unreadable auth key of session '%s': %s", self.session_name, e
            )
            return None

    # Cache helpers: failures are logged and treated as a miss

    def _read_field(self, key: str, field: str) -> Any | None:
        try:
            return self._client.hash_get(key, field)
        except RedisthonError as e:
            logger.warning("Failed to read '%s:%s': %s", key, field, e)
            return None

    def _read_all(self, key: str) -> list[tuple[str, Any]]:
        try:
            return self._client.hash_scan(key)
        except RedisthonError as e:
            logger.warning("Failed to read '%s': %s", key, e)
            return []

    def _write_fields(self, key: str, values: dict[str, Any]) -> None:
        try:
            self._client.hash_set_many(key, values)
            if self._ttl_seconds > 0:
                self._client.expire_key(key, self._ttl_seconds)
        except RedisthonError as e:
            logger.warning("Failed to write '%s': %s", key, e)

    # Session lifecycle

    def clone(self, to_instance: MemorySession | None = None) -> MemorySession:
        """
        Return a fresh in-memory session, as SQLiteSession.clone() does.

        Telethon clones the session for CDN connections and then calls
        set_dc() on the clone. A memory session keeps that out of Redis.
        """
        cloned = to_instance or MemorySession()
        cloned.save_entities = self.save_entities
        return cloned

    def save(self) -> None:
        """
        Store DC, auth key and takeout ID, and refresh the TTL of all keys.

        :raises SessionError: If Redis cannot be written
        """
        if not self._dc_id:
            return

        data = {
            'session_name': self.session_name,
            'dc_id': self._dc_id,
            'server_address': self._server_address,
            'port': self._port,
            'auth_key': (
                base64.b64encode(self._auth_key.key).decode() if self._auth_key else ''
            ),
            'takeout_id': self._takeout_id,
            'saved_at': _now(),
            'version': __version__,
        }
        ttl = self._ttl_seconds if self._ttl_seconds > 0 else None
        try:
            self._client.set_key(self._session_key, data, ttl)
            if ttl:
                self._client.expire_keys(self._cache_keys, ttl)
        except RedisthonError as e:
            raise SessionError(
                f'Failed to save session: {e}', session_name=self.session_name
            ) from e
        logger.debug("Saved session '%s'", self.session_name)

    def close(self) -> None:
        """Close the connection pool, unless it was passed in by the caller."""
        if self._owns_client:
            self._client.close()

    def delete(self) -> None:
        """Delete all keys of this session. Telethon calls this on log_out()."""
        try:
            self._client.delete_keys(*self._all_keys)
        except RedisthonError as e:
            logger.error("Failed to delete session '%s': %s", self.session_name, e)
        self.close()

    def list_sessions(self) -> list[str]:
        """Return the names of all sessions stored under this key prefix."""
        prefix = f'{self._base_key_prefix}:'
        suffix = ':data'
        try:
            keys = self._client.scan_keys(f'{prefix}*{suffix}')
        except RedisthonError as e:
            logger.warning('Failed to list sessions: %s', e)
            return [self.session_name]
        return sorted(key[len(prefix) : -len(suffix)] for key in keys)

    def set_dc(self, dc_id: int, server_address: str, port: int) -> None:
        """Set the data center and save."""
        super().set_dc(dc_id, server_address, port)
        self.save()

    # Entities

    def process_entities(self, tlo: Any) -> None:
        """Cache the users and chats contained in a Telethon object."""
        if not self.save_entities:
            return

        rows = self._entities_to_rows(tlo)
        if not rows:
            return

        cached_at = _now()
        self._write_fields(
            self._entities_key,
            {
                str(entity_id): {
                    'id': entity_id,
                    'access_hash': access_hash,
                    'username': username or '',
                    'phone': phone or '',
                    'name': name or '',
                    'cached_at': cached_at,
                }
                for entity_id, access_hash, username, phone, name in rows
            },
        )

    def _find_entity(self, field: str, value: str) -> EntityRow | None:
        for _, data in self._read_all(self._entities_key):
            if isinstance(data, dict) and data.get(field) == value:
                return _entity_row(data)
        return None

    def get_entity_rows_by_id(
        self, entity_id: int, exact: bool = True
    ) -> EntityRow | None:
        """
        Return (marked_id, access_hash) for a cached entity, or None.

        With exact=False, entity_id is an unmarked ID that may belong to a
        user, chat or channel, as in MemorySession.
        """
        if exact:
            candidates = [entity_id]
        else:
            candidates = [
                utils.get_peer_id(PeerUser(entity_id)),
                utils.get_peer_id(PeerChat(entity_id)),
                utils.get_peer_id(PeerChannel(entity_id)),
            ]
        for candidate in candidates:
            data = self._read_field(self._entities_key, str(candidate))
            if data is not None:
                return _entity_row(data)
        return None

    def get_entity_rows_by_username(self, username: str) -> EntityRow | None:
        """Return (marked_id, access_hash) for a cached username, or None."""
        return self._find_entity('username', username)

    def get_entity_rows_by_phone(self, phone: str) -> EntityRow | None:
        """Return (marked_id, access_hash) for a cached phone, or None."""
        return self._find_entity('phone', phone)

    def get_entity_rows_by_name(self, name: str) -> EntityRow | None:
        """Return (marked_id, access_hash) for a cached display name, or None."""
        return self._find_entity('name', name)

    # Update states

    def get_update_state(self, entity_id: int) -> State | None:
        """Return the stored update state of an entity (0 = the account)."""
        data = self._read_field(self._update_states_key, str(entity_id))
        return None if data is None else _state_from_dict(data)

    def get_update_states(self) -> ItemsView[int, State]:
        """Return (entity_id, State) pairs, as MemorySession does."""
        states: dict[int, State] = {}
        for field, data in self._read_all(self._update_states_key):
            try:
                entity_id = int(field)
            except ValueError:
                continue
            state = _state_from_dict(data)
            if state is not None:
                states[entity_id] = state
        return states.items()

    def set_update_state(self, entity_id: int, state: State) -> None:
        """Store the update state of an entity."""
        self._write_fields(
            self._update_states_key, {str(entity_id): _state_to_dict(entity_id, state)}
        )

    # Sent files

    @staticmethod
    def _file_field(md5_digest: bytes, file_size: int, kind: _SentFileType) -> str:
        return f'{md5_digest.hex()}_{file_size}_{kind.name.lower()}'

    def get_file(
        self, md5_digest: bytes, file_size: int, cls: type[Any]
    ) -> InputPhoto | InputDocument | None:
        """Return a cached InputPhoto or InputDocument, or None."""
        try:
            kind = _SentFileType.from_type(cls)
        except ValueError:
            return None
        data = self._read_field(
            self._sent_files_key, self._file_field(md5_digest, file_size, kind)
        )
        if data is None:
            return None
        try:
            return cls(
                id=data['id'],
                access_hash=data['access_hash'],
                file_reference=bytes.fromhex(data['file_reference']),
            )
        except (KeyError, TypeError, ValueError):
            return None

    def cache_file(
        self, md5_digest: bytes, file_size: int, instance: InputPhoto | InputDocument
    ) -> None:
        """Cache an uploaded photo or document."""
        try:
            kind = _SentFileType.from_type(type(instance))
        except ValueError:
            logger.warning('Not caching file of type %s', type(instance).__name__)
            return
        self._write_fields(
            self._sent_files_key,
            {
                self._file_field(md5_digest, file_size, kind): {
                    'md5_digest': md5_digest.hex(),
                    'file_size': file_size,
                    'id': instance.id,
                    'access_hash': instance.access_hash,
                    'file_reference': (instance.file_reference or b'').hex(),
                    'type': kind.name.lower(),
                    'cached_at': _now(),
                }
            },
        )

    # Diagnostics

    def get_health_info(self) -> dict[str, Any]:
        """Return ping result, server and client info, key names and settings."""
        return {
            'session_name': self.session_name,
            'connection_healthy': self._client.ping(),
            'server_info': self._client.get_info(),
            'client_info': self._client.get_client_info(),
            'keys': {
                'session': self._session_key,
                'entities': self._entities_key,
                'update_states': self._update_states_key,
                'sent_files': self._sent_files_key,
            },
            'settings': {
                'ttl_seconds': self._ttl_seconds,
                'save_entities': self.save_entities,
            },
        }

    def get_statistics(self) -> dict[str, Any]:
        """Return key existence and cache sizes, or {'error': ...} on failure."""
        try:
            return {
                'session_name': self.session_name,
                'session_exists': self._client.key_exists(self._session_key),
                'entities_count': self._client.hash_len(self._entities_key),
                'update_states_count': self._client.hash_len(self._update_states_key),
                'sent_files_count': self._client.hash_len(self._sent_files_key),
                'has_auth_key': self._auth_key is not None,
                'dc_id': self._dc_id,
            }
        except RedisthonError as e:
            return {'session_name': self.session_name, 'error': str(e)}

    def __enter__(self) -> 'RedisSession':
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
