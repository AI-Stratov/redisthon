"""
Exception hierarchy for redisthon.
"""

from typing import Any


def _details(**values: Any) -> dict[str, str]:
    return {name: str(value) for name, value in values.items() if value is not None}


class RedisthonError(Exception):
    """
    Base exception for all redisthon errors.

    :param message: Error message
    :param details: Additional error details
    """

    def __init__(self, message: str, details: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConnectionError(RedisthonError):
    """
    Raised when a Redis/Dragonfly command fails.

    :param message: Error message
    :param host: Redis host
    :param port: Redis port
    """

    def __init__(
        self, message: str, host: str | None = None, port: int | None = None
    ) -> None:
        super().__init__(message, _details(host=host, port=port))
        self.host = host
        self.port = port


class SerializationError(RedisthonError):
    """
    Raised when data cannot be serialized or deserialized.

    :param message: Error message
    :param serializer: Serializer name
    """

    def __init__(self, message: str, serializer: str | None = None) -> None:
        super().__init__(message, _details(serializer=serializer))
        self.serializer = serializer


class ConfigurationError(RedisthonError):
    """
    Raised when configuration is invalid.

    :param message: Error message
    :param parameter: Configuration parameter name
    """

    def __init__(self, message: str, parameter: str | None = None) -> None:
        super().__init__(message, _details(parameter=parameter))
        self.parameter = parameter


class SessionError(RedisthonError):
    """
    Raised when the session cannot be loaded or saved.

    :param message: Error message
    :param session_name: Session name
    """

    def __init__(self, message: str, session_name: str | None = None) -> None:
        super().__init__(message, _details(session_name=session_name))
        self.session_name = session_name
