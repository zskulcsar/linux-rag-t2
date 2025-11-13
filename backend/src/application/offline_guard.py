"""Offline enforcement utilities for backend adapters.

The offline guard replaces ``socket.create_connection`` with a defensive wrapper
that disallows outbound network access to non-loopback hosts. This aligns with
functional requirement FR-010, ensuring the backend remains fully offline after
sources are downloaded.

Example:
    >>> from application.offline_guard import offline_mode
    >>> import socket
    >>> with offline_mode():
    ...     socket.create_connection(("127.0.0.1", 9000))  # Allowed
    ...     socket.create_connection(("198.51.100.10", 443))
    Traceback (most recent call last):
      ...
    OfflineNetworkError: outbound network access blocked for host 198.51.100.10
"""

from collections.abc import Callable, Iterator
import contextlib
import ipaddress
import socket
import threading
from typing import Any
from contextlib import AbstractContextManager


CreateConnection = Callable[..., socket.socket]

_lock = threading.RLock()
_install_count = 0
_original_create_connection: CreateConnection | None = None


class OfflineNetworkError(RuntimeError):
    """Raised when an outbound network connection violates offline guarantees."""


def offline_mode() -> AbstractContextManager[None]:
    """Activate offline enforcement for the current process.

    When active, attempts to open TCP connections to non-loopback hosts raise
    :class:`OfflineNetworkError`. Loopback addresses, Unix domain sockets, and
    other local transports continue to function normally.

    Yields:
        None: The context manager yields control while the guard is active.
    """

    @contextlib.contextmanager
    def _guard() -> Iterator[None]:
        global _install_count, _original_create_connection

        with _lock:
            if _install_count == 0:
                _original_create_connection = socket.create_connection
                socket.create_connection = _guarded_create_connection  # type: ignore[assignment]
            _install_count += 1
        try:
            yield
        finally:
            with _lock:
                _install_count -= 1
                if _install_count == 0 and _original_create_connection is not None:
                    socket.create_connection = _original_create_connection  # type: ignore[assignment]
                    _original_create_connection = None

    return _guard()


def _guarded_create_connection(
    address: Any, *args: Any, **kwargs: Any
) -> socket.socket:
    """Wrapper that blocks outbound connections that target remote hosts."""

    host = _extract_host(address)
    if host is None:
        return _call_original(address, *args, **kwargs)

    if _is_remote_host(host):
        raise OfflineNetworkError(f"outbound network access blocked for host {host}")

    return _call_original(address, *args, **kwargs)


def _call_original(address: Any, *args: Any, **kwargs: Any) -> socket.socket:
    """Call the original ``socket.create_connection`` implementation."""

    if _original_create_connection is None:
        raise RuntimeError("offline guard original create_connection missing")
    return _original_create_connection(address, *args, **kwargs)


def _extract_host(address: Any) -> str | None:
    """Extract the host component from the address used by ``create_connection``."""

    if isinstance(address, tuple) and address:
        host = address[0]
    else:
        host = address

    if isinstance(host, bytes):
        try:
            return host.decode("ascii")
        except UnicodeDecodeError:
            return None

    if isinstance(host, str):
        return host.strip()

    return None


def _is_remote_host(host: str) -> bool:
    """Return True if the host represents a remote address."""

    if not host:
        return False

    lowered = host.lower()
    if lowered in {"localhost", "127.0.0.1", "::1"}:
        return False

    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        # Hostnames other than localhost are treated as remote to avoid DNS lookups.
        return True

    return not ip_obj.is_loopback
