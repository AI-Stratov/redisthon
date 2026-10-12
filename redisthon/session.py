"""
Redis/Dragonfly session implementation for Telethon.

Implements all required Telethon session methods with Redis/Dragonfly backend.
"""

import base64
import logging
from collections.abc import ItemsView
from datetime import UTC, datetime
from typing import Any

from telethon.crypto import AuthKey
from telethon.sessions.memory import MemorySession, _SentFileType
from telethon.tl.types import InputDocument, InputPhoto
from telethon.tl.types.updates import State

from .client import RedisClient
from .exceptions import SessionError

logger = logging.getLogger(__name__)


class RedisSession(MemorySession):  # type: ignore[misc]
    """
    Redis/Dragonfly session storage for Telethon.

    :param session_name: Unique session identifier
    :param host: Redis/Dragonfly server host
    :param port: Server port
    :param db: Database number (ignored for Dragonfly)
    :param password: Authentication password
    :param username: Authentication username
    :param is_dragonfly: Whether using Dragonfly instead of Redis
    :param redis_client: Existing RedisClient to use
    :param max_connections: Maximum connections in pool
    :param socket_keepalive: Enable TCP keepalive
    :param socket_keepalive_options: TCP keepalive settings
    :param connection_timeout: Connection timeout in seconds
    :param key_prefix: Prefix for all Redis keys
    :param ttl_seconds: TTL for cached data (0 = no expiration)
    :param save_entities: Whether to cache entities
    """

    __slots__ = (
        '_auth_key',
        '_client',
        # Telethon session attributes
        '_dc_id',
        '_entities_key',
        '_key_prefix',
        '_port',
        '_sent_files_key',
        '_server_address',
        '_session_key',
        '_takeout_id',
        '_ttl_seconds',
        '_update_states_key',
        'save_entities',
        'session_name',
    )

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
        ttl_seconds: int = 86400 * 30,  # 30 days default
        save_entities: bool = True,
    ) -> None:
        if not isinstance(session_name, (str, bytes)):
            raise SessionError('Session name must be a string or bytes')

        super().__init__()

        self.session_name = (
            session_name if isinstance(session_name, str) else session_name.decode()
        )
        self._ttl_seconds = ttl_seconds
        self.save_entities = save_entities

        # Setup Redis client
        if redis_client is not None:
            self._client = redis_client
        else:
            self._client = RedisClient(
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

        # Setup Redis keys
        self._key_prefix = f'{key_prefix}:{self.session_name}'
        self._session_key = f'{self._key_prefix}:data'
        self._entities_key = f'{self._key_prefix}:entities'
        self._update_states_key = f'{self._key_prefix}:update_states'
        self._sent_files_key = f'{self._key_prefix}:sent_files'

        # Load existing session
        self._load_session_data()

    def _load_session_data(self) -> None:
        """Load existing session data from Redis."""
        try:
            session_data = self._client.get_key(self._session_key)
            if session_data:
                self._dc_id = session_data.get('dc_id')
                self._server_address = session_data.get('server_address')
                self._port = session_data.get('port')
                self._takeout_id = session_data.get('takeout_id')

                if auth_key_b64 := session_data.get('auth_key'):
                    try:
                        auth_key_bytes = base64.standard_b64decode(auth_key_b64)
                        self._auth_key = AuthKey(data=auth_key_bytes)
                    except Exception as e:
                        logger.warning(f'Failed to decode auth key: {e}')
                        self._auth_key = None

                logger.debug(f"Loaded session data for '{self.session_name}'")
            else:
                logger.debug(f"No existing session data for '{self.session_name}'")

        except Exception as e:
            logger.error(f'Failed to load session data: {e}')
            raise SessionError(
                f'Failed to load session data: {e}', session_name=self.session_name
            ) from e

    # Core Telethon session methods

    def clone(self, to_instance: MemorySession | None = None) -> 'RedisSession':
        """
        Clone session to another instance.

        :param to_instance: Target session instance
        :returns: Cloned session
        """
        if to_instance is None:
            # Create new RedisSession with same configuration
            cloned = RedisSession(
                f'{self.session_name}_clone',
                redis_client=self._client,
                key_prefix=self._key_prefix.split(':')[0],
                ttl_seconds=self._ttl_seconds,
                save_entities=self.save_entities,
            )
        else:
            cloned = to_instance

        # Copy session data
        cloned._dc_id = self._dc_id
        cloned._server_address = self._server_address
        cloned._port = self._port
        cloned._auth_key = self._auth_key
        cloned._takeout_id = self._takeout_id

        return cloned

    def save(self) -> None:
        """Save current session state to Redis."""
        if not self._dc_id:
            return

        try:
            # Prepare session data
            auth_key_b64 = ''
            if self._auth_key:
                auth_key_b64 = base64.standard_b64encode(self._auth_key.key).decode()

            session_data = {
                'session_name': self.session_name,
                'dc_id': self._dc_id,
                'server_address': self._server_address,
                'port': self._port,
                'auth_key': auth_key_b64,
                'takeout_id': self._takeout_id,
                'saved_at': datetime.now(UTC).isoformat(),
                'version': '0.1.0',
            }

            # Save with optional TTL
            self._client.set_key(
                self._session_key,
                session_data,
                self._ttl_seconds if self._ttl_seconds > 0 else None,
            )
            logger.debug(f"Session '{self.session_name}' saved to Redis")

        except Exception as e:
            logger.error(f'Failed to save session: {e}')
            raise SessionError(
                f'Failed to save session: {e}', session_name=self.session_name
            ) from e

    def close(self) -> None:
        """Close session and cleanup resources."""
        try:
            self._client.close()
            logger.debug(f"Session '{self.session_name}' closed")
        except Exception as e:
            logger.warning(f'Error closing session: {e}')

    def delete(self) -> None:
        """Delete all session data from Redis."""
        self.close()

    def list_sessions(self) -> list[str]:
        """
        List all available sessions.

        :returns: List of session names
        """
        return [self.session_name]

    def set_dc(self, dc_id: int, server_address: str, port: int) -> None:
        """
        Set data center information.

        :param dc_id: Data center ID
        :param server_address: Server address
        :param port: Server port
        """
        super().set_dc(dc_id, server_address, port)
        self.save()

    # Properties for compatibility

    @property
    def dc_id(self) -> int | None:
        """Get data center ID."""
        return getattr(self, '_dc_id', None)

    @property
    def server_address(self) -> str | None:
        """Get server address."""
        return getattr(self, '_server_address', None)

    @property
    def port(self) -> int | None:
        """Get server port."""
        return getattr(self, '_port', None)

    @property
    def auth_key(self) -> Any:  # AuthKey from telethon, but mypy doesn't know it
        """Get authentication key."""
        return getattr(self, '_auth_key', None)

    @auth_key.setter
    def auth_key(self, value: Any) -> None:
        """Set authentication key. Telethon assigns it on connect and login."""
        self._auth_key = value

    @property
    def takeout_id(self) -> int | None:
        """Get takeout ID."""
        return getattr(self, '_takeout_id', None)

    @takeout_id.setter
    def takeout_id(self, value: int | None) -> None:
        """Set takeout ID. Telethon assigns it in ``client.takeout()``."""
        self._takeout_id = value

    # Entity management methods

    def process_entities(self, tlo: Any) -> None:
        """
        Process and cache entities from Telethon objects.

        :param tlo: Telethon object containing entities
        """
        if not self.save_entities:
            return

        try:
            rows = self._entities_to_rows(tlo)
            if not rows:
                return

            for entity_id, access_hash, username, phone, name in rows:
                entity_data = {
                    'id': entity_id,
                    'access_hash': access_hash,
                    'username': username or '',
                    'phone': phone or '',
                    'name': name or '',
                    'cached_at': datetime.now(UTC).isoformat(),
                }

                self._client.hash_set(self._entities_key, str(entity_id), entity_data)

            # Set TTL on entities hash
            if self._ttl_seconds > 0:
                self._client.expire_key(self._entities_key, self._ttl_seconds)

            logger.debug(f'Cached {len(rows)} entities')

        except Exception as e:
            logger.error(f'Failed to process entities: {e}')

    def get_entity_rows_by_id(
        self, entity_id: int, exact: bool = True
    ) -> tuple[int, int] | None:
        """
        Get entity by ID.

        :param entity_id: Entity ID
        :param exact: Exact match (ignored, always exact)
        :returns: (entity_id, access_hash), or None if not cached
        """
        try:
            entity_data = self._client.hash_get(self._entities_key, str(entity_id))
            if entity_data:
                return entity_data['id'], entity_data['access_hash']
            return None
        except Exception as e:
            logger.debug(f'Entity lookup by ID failed: {e}')
            return None

    def get_entity_rows_by_username(self, username: str) -> tuple[int, int] | None:
        """
        Get entity by username.

        :param username: Username to search for
        :returns: (entity_id, access_hash), or None if not cached
        """
        try:
            for _field, entity_data in self._client.hash_scan(self._entities_key):
                if entity_data.get('username') == username:
                    return entity_data['id'], entity_data['access_hash']
            return None
        except Exception as e:
            logger.debug(f'Entity lookup by username failed: {e}')
            return None

    def get_entity_rows_by_phone(self, phone: str) -> tuple[int, int] | None:
        """
        Get entity by phone.

        :param phone: Phone number to search for
        :returns: (entity_id, access_hash), or None if not cached
        """
        try:
            for _field, entity_data in self._client.hash_scan(self._entities_key):
                if entity_data.get('phone') == phone:
                    return entity_data['id'], entity_data['access_hash']
            return None
        except Exception as e:
            logger.debug(f'Entity lookup by phone failed: {e}')
            return None

    def get_entity_rows_by_name(self, name: str) -> tuple[int, int] | None:
        """
        Get entity by name.

        :param name: Name to search for
        :returns: (entity_id, access_hash), or None if not cached
        """
        try:
            for _field, entity_data in self._client.hash_scan(self._entities_key):
                if entity_data.get('name') == name:
                    return entity_data['id'], entity_data['access_hash']
            return None
        except Exception as e:
            logger.debug(f'Entity lookup by name failed: {e}')
            return None

    def get_input_entity(self, key: Any) -> Any:
        """
        Get input entity.

        :param key: Entity key
        :returns: Input entity
        """
        return super().get_input_entity(key)

    # Update state management

    def get_update_state(self, entity_id: int) -> State | None:
        """
        Get update state for specific entity.

        :param entity_id: Entity ID
        :returns: Update state or None
        """
        try:
            state_data = self._client.hash_get(self._update_states_key, str(entity_id))
            if state_data:
                return State(
                    pts=state_data['pts'],
                    qts=state_data['qts'],
                    date=datetime.fromisoformat(state_data['date'])
                    if state_data.get('date')
                    else None,
                    seq=state_data['seq'],
                    unread_count=state_data['unread_count'],
                )
            return None
        except Exception as e:
            logger.debug(f'Failed to get update state for entity {entity_id}: {e}')
            return None

    def get_update_states(self) -> ItemsView[int, State]:
        """
        Get all update states.

        :returns: (entity_id, State) pairs, as MemorySession returns them
        """
        states: dict[int, State] = {}
        try:
            for field, state_data in self._client.hash_scan(self._update_states_key):
                try:
                    entity_id = int(field)
                    states[entity_id] = State(
                        pts=state_data['pts'],
                        qts=state_data['qts'],
                        date=datetime.fromisoformat(state_data['date'])
                        if state_data.get('date')
                        else None,
                        seq=state_data['seq'],
                        unread_count=state_data['unread_count'],
                    )
                except (ValueError, KeyError):
                    continue
        except Exception as e:
            logger.debug(f'Failed to get update states: {e}')
        return states.items()

    def set_update_state(self, entity_id: int, state: State) -> None:
        """
        Set update state for specific entity.

        :param entity_id: Entity ID
        :param state: Update state
        """
        try:
            state_data = {
                'entity_id': entity_id,
                'pts': state.pts,
                'qts': state.qts,
                'date': state.date.isoformat() if state.date else None,
                'seq': state.seq,
                'unread_count': state.unread_count,
                'updated_at': datetime.now(UTC).isoformat(),
            }

            self._client.hash_set(self._update_states_key, str(entity_id), state_data)

            # Set TTL on update states hash
            if self._ttl_seconds > 0:
                self._client.expire_key(self._update_states_key, self._ttl_seconds)

        except Exception as e:
            logger.error(f'Failed to set update state for entity {entity_id}: {e}')

    # File caching methods

    def get_file(
        self, md5_digest: bytes, file_size: int, cls: type[_SentFileType]
    ) -> _SentFileType | None:
        """
        Get cached file information.

        :param md5_digest: MD5 digest of file
        :param file_size: File size in bytes
        :param cls: File type class (InputPhoto or InputDocument)
        :returns: Cached file info or None
        """
        try:
            file_key = f'{md5_digest.hex()}_{file_size}'
            file_data = self._client.hash_get(self._sent_files_key, file_key)

            if file_data:
                if cls == InputPhoto:
                    return InputPhoto(
                        id=file_data['id'],
                        access_hash=file_data['access_hash'],
                        file_reference=bytes.fromhex(file_data['file_reference'])
                        if file_data['file_reference']
                        else b'',
                    )
                elif cls == InputDocument:
                    return InputDocument(
                        id=file_data['id'],
                        access_hash=file_data['access_hash'],
                        file_reference=bytes.fromhex(file_data['file_reference'])
                        if file_data['file_reference']
                        else b'',
                    )
            return None
        except Exception as e:
            logger.debug(f'Failed to get cached file: {e}')
            return None

    def cache_file(
        self, md5_digest: bytes, file_size: int, instance: _SentFileType
    ) -> None:
        """
        Cache file information.

        :param md5_digest: MD5 digest of file
        :param file_size: File size in bytes
        :param instance: File instance to cache
        """
        try:
            file_key = f'{md5_digest.hex()}_{file_size}'

            file_data = {
                'md5_digest': md5_digest.hex(),
                'file_size': file_size,
                'id': instance.id,
                'access_hash': instance.access_hash,
                'file_reference': instance.file_reference.hex()
                if instance.file_reference
                else '',
                'type': 'photo' if isinstance(instance, InputPhoto) else 'document',
                'cached_at': datetime.now(UTC).isoformat(),
            }

            self._client.hash_set(self._sent_files_key, file_key, file_data)

            # Set TTL on sent files hash
            if self._ttl_seconds > 0:
                self._client.expire_key(self._sent_files_key, self._ttl_seconds)

        except Exception as e:
            logger.error(f'Failed to cache file: {e}')

    # Additional utility methods

    def get_health_info(self) -> dict[str, Any]:
        """
        Get session health information.

        :returns: Health information dictionary
        """
        try:
            ping_success = self._client.ping()
            server_info = self._client.get_info()
            client_info = self._client.get_client_info()

            return {
                'session_name': self.session_name,
                'connection_healthy': ping_success,
                'server_info': server_info,
                'client_info': client_info,
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
        except Exception as e:
            return {
                'session_name': self.session_name,
                'connection_healthy': False,
                'error': str(e),
            }

    def get_statistics(self) -> dict[str, Any]:
        """
        Get session usage statistics.

        :returns: Statistics dictionary
        """
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
        except Exception as e:
            return {
                'session_name': self.session_name,
                'error': str(e),
            }

    # Context manager support

    def __enter__(self) -> 'RedisSession':
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
