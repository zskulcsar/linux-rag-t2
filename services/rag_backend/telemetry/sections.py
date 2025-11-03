"""Context managers for instrumenting critical code sections."""

from __future__ import annotations

import time
from contextlib import AbstractAsyncContextManager, AbstractContextManager
from typing import Any

from .logger import get_logger


class TraceSection(AbstractContextManager["TraceSection"]):
    """Context manager that logs start, finish, and duration of a section.

    Args:
        name: Human-readable name describing the logical section.
        logger: Optional structured logger implementing ``info``/``debug``/``error``.
        metadata: Immutable metadata to attach to every log emitted by this
            context manager.
    """

    def __init__(
        self,
        *,
        name: str,
        logger: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._metadata = dict(metadata or {})
        self._logger = logger or get_logger(f"rag_backend.telemetry.section.{name}")
        self._start: float | None = None

    def __enter__(self) -> "TraceSection":
        """Enter the context, emitting a start log."""

        self._start = time.perf_counter()
        self._logger.info(
            "%s :: start",
            self._name,
            metadata=self._metadata or None,
        )
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Exit the context, logging completion or error details.

        Args:
            exc_type: Exception type if the context exits via an exception.
            exc: Exception instance when present.
            tb: Traceback object associated with the exception.

        Returns:
            ``False`` so any exception propagates to the caller.
        """

        end = time.perf_counter()
        duration_ms = (end - (self._start or end)) * 1000.0
        if exc:
            self._logger.error(
                "%s :: error",
                self._name,
                metadata=self._metadata or None,
                duration_ms=duration_ms,
                error=str(exc),
            )
            return False

        self._logger.info(
            "%s :: complete",
            self._name,
            metadata=self._metadata or None,
            duration_ms=duration_ms,
        )
        return False

    def debug(self, message: str, **kwargs: Any) -> None:
        """Emit a DEBUG message associated with the active section.

        Args:
            message: Human-readable annotation describing the event.
            **kwargs: Additional metadata merged with the static metadata.
        """

        payload = dict(self._metadata)
        payload.update(kwargs)
        self._logger.debug(
            "%s :: %s",
            self._name,
            message,
            metadata=payload or None,
        )


class AsyncTraceSection(AbstractAsyncContextManager["AsyncTraceSection"]):
    """Async variant of :class:`TraceSection`.

    Args:
        name: Human-readable section name.
        logger: Optional structured logger.
        metadata: Immutable metadata to attach to logs.
    """

    def __init__(
        self,
        *,
        name: str,
        logger: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._sync_delegate = TraceSection(name=name, logger=logger, metadata=metadata)

    async def __aenter__(self) -> "AsyncTraceSection":
        """Enter the async context, emitting the start log."""

        self._sync_delegate.__enter__()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        """Exit the async context, mirroring :meth:`TraceSection.__exit__`."""

        return self._sync_delegate.__exit__(exc_type, exc, tb)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Emit a DEBUG message for the active async section.

        Args:
            message: Human-readable annotation.
            **kwargs: Additional metadata merged into the log payload.
        """

        self._sync_delegate.debug(message, **kwargs)


def trace_section(
    name: str,
    *,
    logger: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> TraceSection:
    """Instantiate a :class:`TraceSection`.

    Args:
        name: Section identifier.
        logger: Optional structured logger.
        metadata: Additional context applied to each log record.

    Returns:
        A configured :class:`TraceSection` instance.
    """

    return TraceSection(name=name, logger=logger, metadata=metadata)


def async_trace_section(
    name: str,
    *,
    logger: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> AsyncTraceSection:
    """Instantiate an :class:`AsyncTraceSection`.

    Args:
        name: Section identifier.
        logger: Optional structured logger.
        metadata: Additional context applied to each log record.

    Returns:
        A configured :class:`AsyncTraceSection` instance.
    """

    return AsyncTraceSection(name=name, logger=logger, metadata=metadata)


__all__ = ["TraceSection", "AsyncTraceSection", "trace_section", "async_trace_section"]
