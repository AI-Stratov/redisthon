"""
redisthon - High-performance Redis/Dragonfly session storage for Telethon.

Modern implementation with modular architecture.
"""

from .client import RedisClient
from .exceptions import RedisthonError, ConnectionError, SerializationError
from .session import RedisSession

__version__ = '0.1.0'
__author__ = 'AI-Stratov'
__description__ = 'High-performance Redis/Dragonfly session storage for Telethon'

__all__ = [
    # Main classes
    'RedisSession',
    'RedisClient',

    # Exceptions
    'RedisthonError',
    'ConnectionError',
    'SerializationError',

    # Metadata
    '__version__',
]
