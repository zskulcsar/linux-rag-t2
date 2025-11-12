"""Logging helper providing a structlog-compatible interface with fallback."""

from __future__ import annotations

import logging
from typing import Any

try:  # pragma: no cover - environment-dependent import
    import structlog as _structlog
except ModuleNotFoundError:  # pragma: no cover - fallback expected in tests
    _structlog = None

_ROOT_LOGGER = logging.getLogger("rag_backend.telemetry.logger")


class _FallbackLogger:
    """Minimal logger emulating the structlog API."""

    def __init__(self, name: str, context: dict[str, Any] | None = None) -> None:
        """Initialize the logger adapter."""

        self._logger = logging.getLogger(name)
        self._context = context or {}
        self._logger.debug(
            "FallbackLogger.__init__(name, context) :: start",
            extra={"context": {"name": name, "keys": list(self._context)}},
        )

    def bind(self, **kwargs: Any) -> "_FallbackLogger":
        """Return a new logger with additional context."""

        merged = {**self._context, **kwargs}
        self._logger.debug(
            "FallbackLogger.bind(**kwargs) :: start",
            extra={"context": {"keys": list(merged)}},
        )
        return _FallbackLogger(self._logger.name, merged)

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        payload = {**self._context, **kwargs}
        formatted = msg % args if args else msg
        if payload:
            formatted = f"{formatted} | context={payload}"
        self._logger.log(level, formatted)

    def info(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an INFO level message."""

        self._log(logging.INFO, msg, *args, **kwargs)

    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a DEBUG level message."""

        self._log(logging.DEBUG, msg, *args, **kwargs)

    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a WARNING level message."""

        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an ERROR level message."""

        self._log(logging.ERROR, msg, *args, **kwargs)


def get_logger(name: str):
    """Return a structlog logger when available, otherwise a fallback logger.

    Args:
        name: Fully qualified logger name.

    Returns:
        Logger compatible with the subset of structlog used by the project.

    Example:
        >>> log = get_logger("rag_backend.example")
        >>> log.info("ExampleLogger.get_logger(name) :: start")
    """

    _ROOT_LOGGER.debug(
        "LoggerFactory.get_logger(name) :: start",
        extra={
            "context": {
                "logger_name": name,
                "structlog_available": _structlog is not None,
            }
        },
    )

    if _structlog is not None:
        return _structlog.get_logger(name)

    logging.basicConfig(level=logging.INFO)
    return _FallbackLogger(name)


__all__ = ["get_logger"]
