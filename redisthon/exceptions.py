"""
Exception hierarchy for redisthon.
"""


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
    Raised when Redis/Dragonfly connection fails.

    :param message: Error message
    :param host: Redis host
    :param port: Redis port
    """

    def __init__(
        self,
        message: str,
        host: str | None = None,
        port: int | None = None
    ) -> None:
        details = {}
        if host:
            details['host'] = host
        if port:
            details['port'] = str(port)

        super().__init__(message, details)
        self.host = host
        self.port = port


class SerializationError(RedisthonError):
    """
    Raised when data serialization/deserialization fails.

    :param message: Error message
    :param serializer: Serializer name
    """

    def __init__(self, message: str, serializer: str | None = None) -> None:
        details = {}
        if serializer:
            details['serializer'] = serializer

        super().__init__(message, details)
        self.serializer = serializer


class ConfigurationError(RedisthonError):
    """
    Raised when configuration is invalid.

    :param message: Error message
    :param parameter: Configuration parameter name
    """

    def __init__(self, message: str, parameter: str | None = None) -> None:
        details = {}
        if parameter:
            details['parameter'] = parameter

        super().__init__(message, details)
        self.parameter = parameter


class SessionError(RedisthonError):
    """
    Raised when session operations fail.

    :param message: Error message
    :param session_name: Session name
    """

    def __init__(self, message: str, session_name: str | None = None) -> None:
        details = {}
        if session_name:
            details['session_name'] = session_name

        super().__init__(message, details)
        self.session_name = session_name
