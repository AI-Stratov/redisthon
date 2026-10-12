"""
redisthon - High-performance Redis/Dragonfly session storage for Telethon.

Modern implementation with modular architecture.
"""

from .client import RedisClient
from .exceptions import ConnectionError, RedisthonError, SerializationError
from .session import RedisSession

__version__ = '0.1.0'
__author__ = 'AI-Stratov'
__description__ = 'High-performance Redis/Dragonfly session storage for Telethon'

__all__ = [
    'ConnectionError',
    'RedisClient',
    # Main classes
    'RedisSession',
    # Exceptions
    'RedisthonError',
    'SerializationError',
    # Metadata
    '__version__',
]
