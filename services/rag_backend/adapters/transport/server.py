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

import structlog

FRAME_SEPARATOR = b"\n"
HANDSHAKE_REQUEST_TYPE = "handshake"
HANDSHAKE_RESPONSE = {
    "type": "handshake_ack",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "server": "rag-backend",
}

logger = structlog.get_logger("rag_backend.transport.server")


class TransportProtocolError(RuntimeError):
    """Raised when a client sends an invalid transport frame."""


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


async def _write_frame(writer: asyncio.StreamWriter, message: dict[str, Any]) -> None:
    """Serialize a JSON message and write it as a framed payload."""

    encoded = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(encoded)}\n".encode("ascii")
    writer.write(header)
    writer.write(encoded)
    writer.write(FRAME_SEPARATOR)
    await writer.drain()


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

    response = dict(HANDSHAKE_RESPONSE)
    if request_correlation_id:
        response["correlation_id"] = request_correlation_id
    return response


async def _handle_connection(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Handle a single client connection life-cycle."""

    peername = writer.get_extra_info("peername")
    sockname = writer.get_extra_info("sockname")
    correlation_id = uuid.uuid4().hex
    log = logger.bind(peer=peername, socket=sockname, correlation_id=correlation_id)
    log.info("TransportServer._handle_connection(reader, writer) :: start")

    try:
        request = await _read_frame(reader)
        request_correlation_id = request.get("correlation_id")
        log = log.bind(correlation_id=request_correlation_id or correlation_id)
        response = _handshake_response(
            request, request_correlation_id=request_correlation_id
        )
        await _write_frame(writer, response)
        log.info("TransportServer._handle_connection(reader, writer) :: handshake_ack")
    except TransportProtocolError as exc:
        log.warning(
            "TransportServer._handle_connection(reader, writer) :: protocol_error",
            error=str(exc),
        )
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        finally:
            log.info("TransportServer._handle_connection(reader, writer) :: end")


@asynccontextmanager
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
    log = logger.bind(socket=str(path))
    log.info("TransportServer.transport_server(socket_path) :: start")

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
            log.warning(
                "TransportServer.transport_server(socket_path) :: cleanup_failed",
                error=str(exc),
            )
        log.info("TransportServer.transport_server(socket_path) :: stop")
