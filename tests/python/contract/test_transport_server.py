"""Contract tests for the Unix socket transport server handshake."""

from pathlib import Path

import pytest

from adapters.transport import server
from tests.python.helpers.ipc import close_writer, connect_and_handshake

HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "contract-tests",
}

EXPECTED_HANDSHAKE_RESPONSE = {
    "type": "handshake_ack",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "server": "rag-backend",
}


@pytest.mark.asyncio
async def test_transport_server_creates_socket_and_acknowledges_handshake(
    tmp_path: Path,
) -> None:
    """The server should bind a Unix socket and respond to the handshake."""

    socket_path = tmp_path / "backend.sock"

    async with server.transport_server(socket_path=socket_path):
        assert socket_path.exists(), "transport server must create the Unix socket file"

        reader, writer = await connect_and_handshake(
            socket_path,
            request=HANDSHAKE_REQUEST,
            expected_response=EXPECTED_HANDSHAKE_RESPONSE,
            newline_error="transport must terminate frames with a trailing newline sentinel",
        )
        await close_writer(writer)


@pytest.mark.asyncio
async def test_transport_server_closes_default_handlers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The server should close handlers when it instantiates them."""

    socket_path = tmp_path / "backend.sock"
    closed: list[bool] = []

    class _StubHandlers:
        def dispatch(self, path: str, body: dict[str, str]):
            return 200, {"ok": True}

        def close(self):
            closed.append(True)

    monkeypatch.setattr(server, "create_default_handlers", lambda: _StubHandlers())

    async with server.transport_server(socket_path=socket_path):
        pass

    assert closed == [True], "transport_server must close default handlers on exit"
