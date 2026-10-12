"""
redisthon - Telethon session storage in Redis or Dragonfly.
"""

from .client import RedisClient
from .exceptions import ConnectionError, RedisthonError, SerializationError
from .session import RedisSession

__version__ = '0.1.0'
__author__ = 'AI-Stratov'
__description__ = 'Telethon session storage in Redis or Dragonfly'

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
