"""CLI entrypoint that launches the Linux RAG backend service.

The launcher configures logging, enforces offline operation, optionally enables
deep tracing, and starts the Unix socket transport server used by the CLI
clients. A simple example invocation mirrors the quickstart instructions::

    python -m main \
        --config /etc/ragcli/ragcli-config.yaml \
        --socket /tmp/ragcli/backend.sock \
        --weaviate-url http://127.0.0.1:8080 \
        --ollama-url http://127.0.0.1:11434 \
        --phoenix-url http://127.0.0.1:6006
"""


import argparse
import asyncio
import functools
import logging
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

from adapters.transport import (
    create_default_handlers,
    transport_server,
)
from application import offline_guard
from telemetry import TraceController
from telemetry.logger import get_logger

LOGGER = get_logger("rag_backend.launcher")


@dataclass(frozen=True)
class LauncherConfig:
    """Runtime configuration for the backend launcher.

    Attributes:
        config_path: Location of the ragcli YAML configuration file.
        socket_path: Filesystem path for the Unix domain socket.
        weaviate_url: HTTP URL pointing at the local Weaviate deployment.
        ollama_url: HTTP URL targeting the Ollama service for generation or embeddings.
        phoenix_url: HTTP URL pointing at the Phoenix observability endpoint.
        enable_trace: Whether to enable the optional trace controller.
        log_level: Logging verbosity for stdlib logging.

    Example:
        >>> LauncherConfig(  # doctest: +ELLIPSIS
        ...     config_path=Path('/etc/ragcli/ragcli-config.yaml'),
        ...     socket_path=Path('/tmp/backend.sock'),
        ...     weaviate_url='http://127.0.0.1:8080',
        ...     ollama_url='http://127.0.0.1:11434',
        ...     phoenix_url='http://127.0.0.1:6006',
        ...     enable_trace=False,
        ...     log_level='INFO',
        ... )
        LauncherConfig(...)
    """

    config_path: Path
    socket_path: Path
    weaviate_url: str
    ollama_url: str
    phoenix_url: str
    enable_trace: bool
    log_level: str


class LauncherConfigError(RuntimeError):
    """Raised when configuration files or overrides are invalid."""


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the launcher.

    Args:
        argv: Optional argument vector. When ``None`` (default) the arguments are
            pulled from :data:`sys.argv`.

    Returns:
        Parsed :class:`argparse.Namespace` with CLI options.

    Example:
        >>> parse_args([  # doctest: +ELLIPSIS
        ...     '--config', '/etc/ragcli/config.yaml',
        ...     '--socket', '/tmp/backend.sock',
        ... ])
        Namespace(...)
    """

    parser = argparse.ArgumentParser(description="Launch the Linux RAG backend server.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to ragcli-config.yaml containing backend settings.",
    )
    parser.add_argument(
        "--socket",
        help="Filesystem path for the Unix domain socket used by ragman/ragadmin.",
    )
    parser.add_argument(
        "--weaviate-url",
        help="HTTP endpoint for the local Weaviate deployment (e.g. http://127.0.0.1:8080).",
    )
    parser.add_argument(
        "--ollama-url",
        help="HTTP endpoint for the local Ollama service (e.g. http://127.0.0.1:11434).",
    )
    parser.add_argument(
        "--phoenix-url",
        help="HTTP endpoint for Phoenix observability dashboards (e.g. http://127.0.0.1:6006).",
    )
    parser.add_argument(
        "--trace",
        dest="trace",
        action="store_const",
        const=True,
        default=None,
        help="Enable deep tracing for debugging instrumentation issues.",
    )
    parser.add_argument(
        "--no-trace",
        dest="trace",
        action="store_const",
        const=False,
        help="Disable tracing even if the config file enables it.",
    )
    parser.add_argument(
        "--log-level",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Override the stdlib logging level defined in the config file.",
    )

    return parser.parse_args(list(argv) if argv is not None else None)


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


def _load_backend_settings(config_path: Path) -> dict[str, Any]:
    """Load backend configuration from the ragcli YAML file."""

    try:
        content = config_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LauncherConfigError(
            f"Configuration file {config_path} not found"
        ) from exc
    except OSError as exc:  # pragma: no cover - defensive guard
        raise LauncherConfigError(
            f"Unable to read configuration file {config_path}"
        ) from exc

    raw_data = yaml.safe_load(content) or {}
    if not isinstance(raw_data, dict):
        raise LauncherConfigError(
            "Configuration file must contain a mapping at the root."
        )

    backend_data = raw_data.get("backend")
    if backend_data is None:
        backend_data = raw_data

    if not isinstance(backend_data, dict):
        raise LauncherConfigError("Backend configuration must be a mapping.")
    return backend_data


def _coalesce_value(
    *,
    name: str,
    cli_value: str | None,
    config: dict[str, Any],
    default: str | None = None,
) -> str:
    """Return the CLI override, config value, or default for a string option."""

    if cli_value not in {None, ""}:
        return str(cli_value)
    candidate = config.get(name)
    if candidate not in {None, ""}:
        return str(candidate)
    if default is not None:
        return default
    raise LauncherConfigError(
        f"Missing required '{name}' setting in --config or CLI overrides."
    )


def _coalesce_bool(
    *,
    name: str,
    cli_value: bool | None,
    config: dict[str, Any],
    default: bool = False,
) -> bool:
    """Return CLI override, config value, or default for boolean settings."""

    if cli_value is not None:
        return cli_value
    candidate = config.get(name)
    if isinstance(candidate, bool):
        return candidate
    if isinstance(candidate, str):
        lowered = candidate.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    if candidate is None:
        return default
    raise LauncherConfigError(f"Invalid boolean value for '{name}': {candidate!r}")


def build_launcher_config(args: argparse.Namespace) -> LauncherConfig:
    """Combine config file values and CLI overrides into a launcher config."""

    config_path = Path(args.config).expanduser()
    backend_settings = _load_backend_settings(config_path)

    socket_value = _coalesce_value(
        name="socket",
        cli_value=args.socket,
        config=backend_settings,
    )
    weaviate_url = _coalesce_value(
        name="weaviate_url",
        cli_value=args.weaviate_url,
        config=backend_settings,
    )
    ollama_url = _coalesce_value(
        name="ollama_url",
        cli_value=args.ollama_url,
        config=backend_settings,
    )
    phoenix_url = _coalesce_value(
        name="phoenix_url",
        cli_value=args.phoenix_url,
        config=backend_settings,
    )
    log_level = _coalesce_value(
        name="log_level",
        cli_value=args.log_level,
        config=backend_settings,
        default="INFO",
    ).upper()
    trace_enabled = _coalesce_bool(
        name="trace",
        cli_value=args.trace,
        config=backend_settings,
        default=False,
    )

    return LauncherConfig(
        config_path=config_path,
        socket_path=Path(socket_value).expanduser(),
        weaviate_url=weaviate_url,
        ollama_url=ollama_url,
        phoenix_url=phoenix_url,
        enable_trace=trace_enabled,
        log_level=log_level,
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point invoked by ``python -m main``.

    Args:
        argv: Optional argument vector override for testing.

    Returns:
        Process exit code where ``0`` indicates success.

    Example:
        >>> main([  # doctest: +SKIP
        ...     '--config', '/etc/ragcli/ragcli-config.yaml',
    ... ])
        0
    """

    args = parse_args(argv)
    try:
        config = build_launcher_config(args)
    except LauncherConfigError as exc:
        print(f"rag_backend launcher error: {exc}", file=sys.stderr)
        return 2

    configure_logging(config.log_level)
    trace_controller = TraceController()
    if config.enable_trace:
        trace_controller.enable()

    LOGGER.info(
        "BackendLauncher.main(argv) :: configuration_loaded",
        config=str(config.config_path),
        socket=str(config.socket_path),
        weaviate_url=config.weaviate_url,
        ollama_url=config.ollama_url,
        phoenix_url=config.phoenix_url,
        log_level=config.log_level,
    )
    LOGGER.info(
        "BackendLauncher.main(argv) :: offline_mode_enabled", offline_mode="active"
    )

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
