"""
redisthon - Telethon session storage in Redis or Dragonfly.
"""

from ._version import __version__
from .client import RedisClient
from .exceptions import (
    ConfigurationError,
    ConnectionError,
    RedisthonError,
    SerializationError,
    SessionError,
)
from .session import RedisSession

__author__ = 'AI-Stratov'
__description__ = 'Telethon session storage in Redis or Dragonfly'

__all__ = [
    'ConfigurationError',
    'ConnectionError',
    'RedisClient',
    'RedisSession',
    'RedisthonError',
    'SerializationError',
    'SessionError',
    '__version__',
]
