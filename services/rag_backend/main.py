"""CLI entrypoint that launches the Linux RAG backend service.

The launcher configures logging, enforces offline operation, optionally enables
deep tracing, and starts the Unix socket transport server used by the CLI
clients. A simple example invocation mirrors the quickstart instructions::

    python -m services.rag_backend.main \
        --socket /tmp/ragcli/backend.sock \
        --weaviate-url http://127.0.0.1:8080 \
        --ollama-url http://127.0.0.1:11434 \
        --phoenix-url http://127.0.0.1:6006
"""

from __future__ import annotations

import argparse
import asyncio
import functools
import logging
import os
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from services.rag_backend.adapters.transport import create_default_handlers, transport_server
from services.rag_backend.application import offline_guard
from services.rag_backend.telemetry import TraceController
from services.rag_backend.telemetry.logger import get_logger

LOGGER = get_logger("rag_backend.launcher")


@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration for the backend launcher.

    Attributes:
        socket_path: Filesystem path for the Unix domain socket.
        weaviate_url: HTTP URL pointing at the local Weaviate deployment.
        ollama_url: HTTP URL targeting the Ollama service for generation or embeddings.
        phoenix_url: HTTP URL pointing at the Phoenix observability endpoint.
        enable_trace: Whether to enable the optional trace controller.
        log_level: Logging verbosity for stdlib logging.

    Example:
        >>> LauncherConfig(  # doctest: +ELLIPSIS
        ...     socket_path=Path('/tmp/backend.sock'),
        ...     weaviate_url='http://127.0.0.1:8080',
        ...     ollama_url='http://127.0.0.1:11434',
        ...     phoenix_url='http://127.0.0.1:6006',
        ...     enable_trace=False,
        ...     log_level='INFO',
        ... )
        LauncherConfig(...)
    """

    socket_path: Path
    weaviate_url: str
    ollama_url: str
    phoenix_url: str
    enable_trace: bool
    log_level: str


def parse_args(argv: Sequence[str] | None = None) -> LauncherConfig:
    """Parse CLI arguments into a :class:`LauncherConfig`.

    Args:
        argv: Optional argument vector. When ``None`` (default) the arguments are
            pulled from :data:`sys.argv`.

    Returns:
        Configured :class:`LauncherConfig` instance.

    Example:
        >>> parse_args([  # doctest: +ELLIPSIS
        ...     '--socket', '/tmp/backend.sock',
        ...     '--weaviate-url', 'http://127.0.0.1:8080',
        ...     '--ollama-url', 'http://127.0.0.1:11434',
        ...     '--phoenix-url', 'http://127.0.0.1:6006',
        ... ])
        LauncherConfig(...)
    """

    parser = argparse.ArgumentParser(description="Launch the Linux RAG backend server.")
    parser.add_argument(
        "--socket",
        required=True,
        help="Filesystem path for the Unix domain socket used by ragman/ragadmin.",
    )
    parser.add_argument(
        "--weaviate-url",
        required=True,
        help="HTTP endpoint for the local Weaviate deployment (e.g. http://127.0.0.1:8080).",
    )
    parser.add_argument(
        "--ollama-url",
        required=True,
        help="HTTP endpoint for the local Ollama service (e.g. http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--phoenix-url",
        required=True,
        help="HTTP endpoint for Phoenix observability dashboards (e.g. http://127.0.0.1:6006).",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        default=False,
        help="Enable deep tracing for debugging instrumentation issues.",
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("RAGCLI_LOG_LEVEL", "INFO"),
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Set the stdlib logging level (default: INFO).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)
    socket_path = Path(args.socket).expanduser()
    return LauncherConfig(
        socket_path=socket_path,
        weaviate_url=args.weaviate_url,
        ollama_url=args.ollama_url,
        phoenix_url=args.phoenix_url,
        enable_trace=bool(args.trace),
        log_level=args.log_level.upper(),
    )


def configure_logging(level: str) -> None:
    """Configure stdlib logging for the launcher process.

    Args:
        level: Logging severity string such as ``"INFO"``.

    Returns:
        ``None``.

    Example:
        >>> configure_logging("DEBUG")
    """

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


async def _wait_for_shutdown(signals: Iterable[int], *, logger) -> None:
    """Block until one of the provided signals requests shutdown.

    Args:
        signals: Iterable of POSIX signals to monitor.
        logger: Structured logger instance for diagnostics.

    Returns:
        ``None`` once shutdown has been requested.

    Example:
        >>> asyncio.run(_wait_for_shutdown([], logger=LOGGER))  # doctest: +SKIP
    """

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(sig: int) -> None:
        readable = signal.Signals(sig).name
        logger.info(
            "BackendLauncher._wait_for_shutdown(signals, logger) :: signal_received",
            signal=readable,
        )
        stop_event.set()

    for sig in signals:
        try:
            loop.add_signal_handler(sig, functools.partial(_signal_handler, sig))
        except NotImplementedError:  # pragma: no cover - Windows fallback
            pass

    try:
        await stop_event.wait()
    finally:
        for sig in signals:
            try:
                loop.remove_signal_handler(sig)
            except NotImplementedError:  # pragma: no cover - Windows fallback
                pass


async def _run_server(config: LauncherConfig) -> None:
    """Start the Unix socket transport server and block until shutdown.

    Args:
        config: Fully-populated launcher configuration.

    Returns:
        ``None`` once the transport server shuts down.

    Example:
        >>> asyncio.run(_run_server(  # doctest: +SKIP
        ...     LauncherConfig(
        ...         socket_path=Path('/tmp/backend.sock'),
        ...         weaviate_url='http://127.0.0.1:8080',
        ...         ollama_url='http://127.0.0.1:11434',
        ...         phoenix_url='http://127.0.0.1:6006',
        ...         enable_trace=False,
        ...         log_level='INFO',
        ...     )
        ... ))
    """

    handlers = create_default_handlers()
    LOGGER.info(
        "BackendLauncher._run_server(config) :: preparing_transport",
        socket=str(config.socket_path),
    )
    async with transport_server(socket_path=config.socket_path, handlers=handlers):
        LOGGER.info(
            "BackendLauncher._run_server(config) :: transport_ready",
            socket=str(config.socket_path),
        )
        await _wait_for_shutdown((signal.SIGINT, signal.SIGTERM), logger=LOGGER)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point invoked by ``python -m services.rag_backend.main``.

    Args:
        argv: Optional argument vector override for testing.

    Returns:
        Process exit code where ``0`` indicates success.

    Example:
        >>> main([  # doctest: +SKIP
        ...     '--socket', '/tmp/backend.sock',
        ...     '--weaviate-url', 'http://127.0.0.1:8080',
        ...     '--ollama-url', 'http://127.0.0.1:11434',
        ...     '--phoenix-url', 'http://127.0.0.1:6006',
        ... ])
        0
    """

    config = parse_args(argv)
    configure_logging(config.log_level)
    trace_controller = TraceController()
    if config.enable_trace:
        trace_controller.enable()

    LOGGER.info(
        "BackendLauncher.main(argv) :: configuration_loaded",
        socket=str(config.socket_path),
        weaviate_url=config.weaviate_url,
        ollama_url=config.ollama_url,
        phoenix_url=config.phoenix_url,
    )
    LOGGER.info("BackendLauncher.main(argv) :: offline_mode_enabled", offline_mode="active")

    try:
        with offline_guard.offline_mode():
            asyncio.run(_run_server(config))
        return 0
    except asyncio.CancelledError:  # pragma: no cover - defensive guard
        LOGGER.warning("BackendLauncher.main(argv) :: cancelled")
        return 1
    except KeyboardInterrupt:
        LOGGER.info("BackendLauncher.main(argv) :: interrupted")
        return 0
    finally:
        if trace_controller.is_enabled():
            trace_controller.disable()


if __name__ == "__main__":  # pragma: no cover - module execution guard
    raise SystemExit(main())
