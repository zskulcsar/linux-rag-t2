"""Offline compliance tests ensuring the backend never performs outbound HTTP."""

from collections.abc import Iterator
import http.client
import socket
from contextlib import contextmanager

import pytest

from application import offline_guard


@contextmanager
def _patched_create_connection(
    monkeypatch: pytest.MonkeyPatch,
    delegate: callable,
) -> Iterator[None]:
    """Patch socket.create_connection with the provided delegate for the test duration."""

    monkeypatch.setattr(socket, "create_connection", delegate)
    yield


def test_offline_guard_blocks_remote_ipv4_addresses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure remote IPv4 TCP connections raise the offline guard exception."""

    calls: int = 0

    def fake_create_connection(
        address: tuple[str, int], *args: object, **kwargs: object
    ) -> object:
        nonlocal calls
        calls += 1
        return object()

    with _patched_create_connection(monkeypatch, fake_create_connection):
        with offline_guard.offline_mode():
            with pytest.raises(offline_guard.OfflineNetworkError) as excinfo:
                socket.create_connection(("198.51.100.10", 443))

    assert calls == 0, (
        "remote connections must be short-circuited before touching the dialer"
    )
    assert "198.51.100.10" in str(excinfo.value)


def test_offline_guard_allows_loopback_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure loopback connections continue to reach local services."""

    sentinel = object()
    calls: int = 0

    def fake_create_connection(
        address: tuple[str, int], *args: object, **kwargs: object
    ) -> object:
        nonlocal calls
        calls += 1
        return sentinel

    with _patched_create_connection(monkeypatch, fake_create_connection):
        with offline_guard.offline_mode():
            result = socket.create_connection(("127.0.0.1", 8080))

    assert result is sentinel
    assert calls == 1, (
        "loopback connections should use the original dialer exactly once"
    )


def test_offline_guard_restores_original_create_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure the guard cleans up and restores the original socket dialer."""

    def fake_create_connection(
        address: tuple[str, int], *args: object, **kwargs: object
    ) -> str:
        return f"dialed:{address[0]}:{address[1]}"

    with _patched_create_connection(monkeypatch, fake_create_connection):
        with offline_guard.offline_mode():
            pass

        # After exiting the context manager the original delegate must be restored.
        assert socket.create_connection is fake_create_connection
        assert socket.create_connection(("127.0.0.1", 7000)) == "dialed:127.0.0.1:7000"


def test_http_client_connects_fail_fast_for_remote_hosts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure higher-level HTTP clients also surface the offline guard failure."""

    def fake_create_connection(
        address: tuple[str, int], *args: object, **kwargs: object
    ) -> object:
        raise AssertionError(
            "HTTP clients should be blocked before reaching the socket layer"
        )

    with _patched_create_connection(monkeypatch, fake_create_connection):
        with offline_guard.offline_mode():
            connection = http.client.HTTPConnection("203.0.113.25", 80, timeout=0.1)
            with pytest.raises(offline_guard.OfflineNetworkError):
                connection.connect()
            connection.close()
