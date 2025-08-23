"""
Redis/Dragonfly schemas for Telethon session storage.

Documentation for data structures used in native Redis Hash storage.
"""

from dataclasses import dataclass
from typing import NamedTuple


class SearchFilter(NamedTuple):
    """Filter for searching in Redis data (legacy compatibility)."""

    index_name: str
    field_name: str
    field_value: str | int


@dataclass(frozen=True, slots=True)
class RedisSchemas:
    """
    Schema definitions for redisthon storage structures.

    Documentation for data structures stored using native Redis Hash commands.
    """

    @staticmethod
    def get_session_structure() -> dict[str, str]:
        """
        Session data structure stored as msgpack-serialized binary in Redis.

        :returns: Dictionary describing session structure

        Storage: Single Redis key with msgpack binary data
        Key pattern: {key_prefix}:data
        """
        return {
            'session_name': 'str - Session identifier',
            'dc_id': 'int - Telegram data center ID',
            'server_address': 'str - Telegram server address',
            'port': 'int - Server port',
            'auth_key': 'str - Base64 encoded auth key',
            'takeout_id': 'int|None - Takeout session ID',
            'saved_at': 'str - ISO timestamp when saved',
            'version': 'str - Library version',
        }

    @staticmethod
    def get_entity_structure() -> dict[str, str]:
        """
        Entity data structure stored in Redis Hash.

        :returns: Dictionary describing entity structure

        Storage: Redis Hash with entity_id as field, msgpack binary as value
        Key pattern: {key_prefix}:entities
        Hash fields: entity_id -> msgpack(entity_data)
        """
        return {
            'id': 'int - Telegram entity ID',
            'access_hash': 'int - Entity access hash',
            'username': 'str - Username (if available)',
            'phone': 'str - Phone number (if available)',
            'name': 'str - Display name',
            'cached_at': 'str - ISO timestamp when cached',
        }

    @staticmethod
    def get_update_state_structure() -> dict[str, str]:
        """
        Update state structure stored in Redis Hash.

        :returns: Dictionary describing update state structure

        Storage: Redis Hash with entity_id as field, msgpack binary as value
        Key pattern: {key_prefix}:update_states
        Hash fields: entity_id -> msgpack(state_data)
        """
        return {
            'entity_id': 'int - Entity ID',
            'pts': 'int - PTS value',
            'qts': 'int - QTS value',
            'date': 'str|None - ISO timestamp',
            'seq': 'int - Sequence number',
            'unread_count': 'int - Unread messages count',
            'updated_at': 'str - ISO timestamp when updated',
        }

    @staticmethod
    def get_sent_file_structure() -> dict[str, str]:
        """
        Sent file structure stored in Redis Hash.

        :returns: Dictionary describing sent file structure

        Storage: Redis Hash with composite key as field, msgpack binary as value
        Key pattern: {key_prefix}:sent_files
        Hash fields: {md5_hex}_{file_size} -> msgpack(file_data)
        """
        return {
            'md5_digest': 'str - MD5 hash in hex',
            'file_size': 'int - File size in bytes',
            'id': 'int - Telegram file ID',
            'access_hash': 'int - File access hash',
            'file_reference': 'str - File reference in hex',
            'type': 'str - photo or document',
            'cached_at': 'str - ISO timestamp when cached',
        }


# Legacy exports for backward compatibility
session_schema = RedisSchemas.get_session_structure()
entity_schema = RedisSchemas.get_entity_structure()
update_state_schema = RedisSchemas.get_update_state_structure()
sent_file_schema = RedisSchemas.get_sent_file_structure()

__all__ = [
    'SearchFilter',
    'RedisSchemas',
    'session_schema',
    'entity_schema',
    'update_state_schema',
    'sent_file_schema',
]
