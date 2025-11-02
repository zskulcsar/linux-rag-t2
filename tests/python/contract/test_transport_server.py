"""Contract tests for the Unix socket transport server handshake."""

import asyncio
import json
from pathlib import Path

import pytest

from services.rag_backend.adapters.transport import server

HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "contract-tests",
}


async def _write_frame(writer: asyncio.StreamWriter, message: dict) -> None:
    """Send a framed JSON message using <len>\n<payload>\n semantics."""

    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(body)}\n".encode("ascii")
    writer.write(header)
    writer.write(body)
    writer.write(b"\n")
    await writer.drain()


async def _read_frame(reader: asyncio.StreamReader) -> dict:
    """Read a framed JSON message using <len>\n<payload>\n semantics."""

    length_line = await reader.readline()
    if not length_line:
        raise AssertionError("expected length-prefixed frame, got EOF")
    try:
        payload_length = int(length_line.decode("ascii").strip())
    except ValueError as exc:  # pragma: no cover - defensive guard for clarity
        raise AssertionError(f"invalid length prefix: {length_line!r}") from exc

    payload = await reader.readexactly(payload_length)
    newline = await reader.readexactly(1)
    assert (
        newline == b"\n"
    ), "transport must terminate frames with a trailing newline sentinel"

    return json.loads(payload.decode("utf-8"))


@pytest.mark.asyncio
async def test_transport_server_creates_socket_and_acknowledges_handshake(
    tmp_path: Path,
) -> None:
    """The server should bind a Unix socket and respond to the handshake."""

    socket_path = tmp_path / "backend.sock"

    async with server.transport_server(socket_path=socket_path):
        assert socket_path.exists(), "transport server must create the Unix socket file"

        reader, writer = await asyncio.wait_for(
            asyncio.open_unix_connection(path=str(socket_path)), timeout=1
        )

        try:
            await asyncio.wait_for(_write_frame(writer, HANDSHAKE_REQUEST), timeout=1)
            handshake_response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert handshake_response == {
        "type": "handshake_ack",
        "protocol": "rag-cli-ipc",
        "version": 1,
        "server": "rag-backend",
    }

