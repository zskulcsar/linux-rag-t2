"""Observability helpers for structlog and Phoenix instrumentation."""

import logging
from typing import Any, Iterable

from telemetry import trace_call


@trace_call
def configure_structlog(
    *,
    service_name: str,
    log_level: int = logging.INFO,
    processors: Iterable[Any] | None = None,
) -> None:
    """Configure structlog (if available) for JSON logging.

    Args:
        service_name: Logical service identifier added to each log record.
        log_level: Base logging level to apply to the root logger.
        processors: Optional iterable of structlog processors. When omitted, a
            sensible JSON pipeline is configured automatically.
    """

    try:
        import structlog  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - exercised via tests
        logging.basicConfig(level=log_level, format="%(message)s")
        logging.getLogger(__name__).warning(
            "configure_structlog(service_name=%s) :: structlog_missing", service_name
        )
        return

    logging.basicConfig(level=log_level, format="%(message)s")

    default_processors = processors or [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]

    structlog.configure(
        processors=list(default_processors),
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    if hasattr(structlog.contextvars, "bind_contextvars"):
        structlog.contextvars.bind_contextvars(service=service_name)


@trace_call
def configure_phoenix(
    *,
    service_name: str,
    endpoint: str | None = None,
    instrumentors: Iterable[str] | None = None,
) -> None:
    """Configure Arize Phoenix OTEL instrumentation.

    Args:
        service_name: Service name passed to Phoenix.
        endpoint: Optional endpoint URL overriding the default Phoenix backend.
        instrumentors: Optional iterable of instrumentor identifiers passed to
            :func:`phoenix.otel.register`.

    Raises:
        RuntimeError: If the Phoenix package is not installed.
    """

    try:
        from phoenix.otel import register  # type: ignore
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via tests
        raise RuntimeError(
            "configure_phoenix(service_name=%s) :: phoenix package not installed"
            % service_name
        ) from exc

    kwargs: dict[str, Any] = {
        "project_name": service_name,
        "auto_instrument": True,
    }
    if endpoint:
        kwargs["endpoint"] = endpoint
    if instrumentors:
        kwargs["instrumentors"] = tuple(instrumentors)

    register(**kwargs)


__all__ = ["configure_structlog", "configure_phoenix"]
