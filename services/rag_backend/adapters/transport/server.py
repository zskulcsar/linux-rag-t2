"""Async Unix socket server implementation for CLI transport handshakes."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from services.rag_backend.telemetry import async_trace_section, trace_call

FRAME_SEPARATOR = b"\n"
HANDSHAKE_REQUEST_TYPE = "handshake"
HANDSHAKE_RESPONSE = {
    "type": "handshake_ack",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "server": "rag-backend",
}

class TransportProtocolError(RuntimeError):
    """Raised when a client sends an invalid transport frame."""


@trace_call
def _ensure_socket_directory(socket_path: Path) -> None:
    """Ensure the socket directory exists before binding."""

    socket_path.parent.mkdir(parents=True, exist_ok=True)
    if socket_path.exists():
        try:
            socket_path.unlink()
        except OSError as exc:  # pragma: no cover - defensive guard
            raise TransportProtocolError(
                f"Unable to remove stale socket at {socket_path}"
            ) from exc


@trace_call
async def _read_frame(reader: asyncio.StreamReader) -> dict[str, Any]:
    """Consume a single length-prefixed JSON frame from the reader."""

    length_line = await reader.readline()
    if not length_line:
        raise TransportProtocolError("EOF before reading frame length")

    try:
        payload_length = int(length_line.decode("ascii").strip())
    except ValueError as exc:
        raise TransportProtocolError("Invalid frame length prefix") from exc

    payload = await reader.readexactly(payload_length)
    trailing = await reader.readexactly(1)
    if trailing != FRAME_SEPARATOR:
        raise TransportProtocolError("Frame must terminate with newline sentinel")

    try:
        return json.loads(payload.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise TransportProtocolError("Frame payload is not valid JSON") from exc


@trace_call
async def _write_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    """Serialize a JSON message and write it as a framed payload."""

    encoded = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(encoded)}\n".encode("ascii")
    writer.write(header)
    writer.write(encoded)
    writer.write(FRAME_SEPARATOR)
    await writer.drain()


@trace_call
def _handshake_response(
    request: dict[str, Any], *, request_correlation_id: str | None
) -> dict[str, Any]:
    """Validate the handshake request and prepare the acknowledgement payload."""

    if request.get("type") != HANDSHAKE_REQUEST_TYPE:
        raise TransportProtocolError("First frame must be a handshake request")

    protocol = request.get("protocol")
    if protocol != HANDSHAKE_RESPONSE["protocol"]:
        raise TransportProtocolError(f"Unsupported protocol: {protocol!r}")

    version = request.get("version")
    if version != HANDSHAKE_RESPONSE["version"]:
        raise TransportProtocolError(f"Unsupported protocol version: {version!r}")

    return dict(HANDSHAKE_RESPONSE)


@trace_call
async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Handle a single client connection life-cycle."""

    peername = writer.get_extra_info("peername")
    sockname = writer.get_extra_info("sockname")
    correlation_id = uuid.uuid4().hex
    metadata = {
        "peer": str(peername),
        "socket": str(sockname),
        "correlation_id": correlation_id,
    }
    async with async_trace_section("transport.connection", metadata=metadata) as section:
        try:
            request = await _read_frame(reader)
            request_correlation_id = request.get("correlation_id") or correlation_id
            section.debug("handshake_request", correlation_id=request_correlation_id)
            response = _handshake_response(
                request, request_correlation_id=request_correlation_id
            )
            await _write_frame(writer, response)
            section.debug("handshake_ack_sent", correlation_id=request_correlation_id)
        except TransportProtocolError as exc:
            section.debug("protocol_error", error=str(exc))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            finally:
                section.debug("connection_closed")


@asynccontextmanager
@trace_call
async def transport_server(
    *, socket_path: str | Path, backlog: int = 100
) -> AsyncIterator[asyncio.AbstractServer]:
    """Start a Unix domain socket server for CLI handshake traffic.

    Args:
        socket_path: Location of the socket file that clients will connect to.
        backlog: Maximum number of queued connections accepted by the listener.

    Yields:
        The running asyncio server instance for additional inspection if needed.
    """

    path = Path(socket_path)
    _ensure_socket_directory(path)

    loop = asyncio.get_running_loop()
    server = await asyncio.start_unix_server(
        _handle_connection, path=str(path), backlog=backlog
    )
    async with async_trace_section(
        "transport.server", metadata={"socket": str(path), "backlog": backlog}
    ) as section:
        try:
            yield server
        finally:
            server.close()
            await server.wait_closed()
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError as exc:  # pragma: no cover - defensive guard
                section.debug("cleanup_failed", error=str(exc))
