"""IPC helpers for transport contract and integration tests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

DEFAULT_HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "tests",
}

EXPECTED_HANDSHAKE_RESPONSE = {
    "type": "handshake_ack",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "server": "rag-backend",
}


async def write_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    """Send a framed JSON message using <len>\\n<payload>\\n semantics."""

    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(body)}\n".encode("ascii")
    writer.write(header)
    writer.write(body)
    writer.write(b"\n")
    await writer.drain()


async def read_frame(
    reader: asyncio.StreamReader,
    *,
    newline_error: str = "transport must terminate frames with newline sentinel",
) -> dict[str, Any]:
    """Read a framed JSON message using <len>\\n<payload>\\n semantics."""

    length_line = await reader.readline()
    if not length_line:
        raise AssertionError("expected length-prefixed frame, got EOF")

    try:
        payload_length = int(length_line.decode("ascii").strip())
    except ValueError as exc:  # pragma: no cover - defensive guard
        raise AssertionError(f"invalid length prefix: {length_line!r}") from exc

    payload = await reader.readexactly(payload_length)
    newline = await reader.readexactly(1)
    assert newline == b"\n", newline_error
    return json.loads(payload.decode("utf-8"))


async def connect_and_handshake(
    socket_path: Path,
    *,
    request: dict[str, Any] | None = None,
    expected_response: dict[str, Any] | None = None,
    timeout: float = 1.0,
    newline_error: str = "transport must terminate frames with newline sentinel",
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the socket, perform the handshake, and return the streams."""

    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(path=str(socket_path)), timeout=timeout
    )
    handshake_request = request or DEFAULT_HANDSHAKE_REQUEST
    await asyncio.wait_for(write_frame(writer, handshake_request), timeout=timeout)
    handshake_response = await asyncio.wait_for(
        read_frame(reader, newline_error=newline_error), timeout=timeout
    )
    expected = expected_response or EXPECTED_HANDSHAKE_RESPONSE
    if expected is not None:
        assert handshake_response == expected
    return reader, writer


async def close_writer(writer: asyncio.StreamWriter) -> None:
    """Close the writer stream and wait for completion."""

    writer.close()
    await writer.wait_closed()


__all__ = [
    "DEFAULT_HANDSHAKE_REQUEST",
    "EXPECTED_HANDSHAKE_RESPONSE",
    "close_writer",
    "connect_and_handshake",
    "read_frame",
    "write_frame",
]
