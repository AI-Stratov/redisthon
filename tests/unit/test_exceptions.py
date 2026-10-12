"""
Unit tests for the exception hierarchy.
"""

import pytest

from redisthon import (
    ConfigurationError,
    ConnectionError,
    RedisthonError,
    SerializationError,
    SessionError,
)


@pytest.mark.parametrize(
    ('error', 'details'),
    [
        (ConnectionError('m', host='h', port=1), {'host': 'h', 'port': '1'}),
        (ConnectionError('m'), {}),
        (SerializationError('m', serializer='msgpack'), {'serializer': 'msgpack'}),
        (ConfigurationError('m', parameter='p'), {'parameter': 'p'}),
        (SessionError('m', session_name='s'), {'session_name': 's'}),
        (SessionError('m'), {}),
    ],
)
def test_details(error, details):
    assert isinstance(error, RedisthonError)
    assert error.message == 'm'
    assert str(error) == 'm'
    assert error.details == details
