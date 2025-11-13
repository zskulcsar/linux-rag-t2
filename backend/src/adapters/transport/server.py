"""Async Unix socket server implementation for CLI transport requests."""

from __future__ import annotations

import asyncio
import functools
import json
import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from telemetry import async_trace_section, trace_call

from .handlers import (
    IndexUnavailableError,
    TransportError,
    TransportHandlers,
    create_default_handlers,
)

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


class TransportConnectionClosed(TransportProtocolError):
    """Raised when the client closes the connection gracefully."""


def _normalize_correlation_id(candidate: Any | None, fallback: str) -> str:
    """Ensure correlation identifiers are always non-empty strings."""

    if isinstance(candidate, str) and candidate:
        return candidate
    return fallback


@trace_call
def _ensure_socket_directory(socket_path: Path) -> None:
    """Ensure the socket directory exists before binding.

    Args:
        socket_path: Fully-qualified socket path including directory.

    Raises:
        TransportProtocolError: If a stale socket file cannot be removed.
    """

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
    """Consume a single length-prefixed JSON frame from the reader.

    Args:
        reader: Stream reader associated with the client socket.

    Returns:
        Decoded mapping representing the JSON payload.

    Raises:
        TransportConnectionClosed: If the client closes the connection.
        TransportProtocolError: If framing or JSON decoding fails.
    """

    length_line = await reader.readline()
    if not length_line:
        raise TransportConnectionClosed("connection closed by client")

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
    """Serialize a JSON message and write it as a framed payload.

    Args:
        writer: Stream writer associated with the client socket.
        message: JSON-serializable payload to send.
    """

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
    """Validate the handshake request and prepare the acknowledgement payload.

    Args:
        request: First frame received from the client.
        request_correlation_id: Correlation identifier extracted from the request.

    Returns:
        Dictionary representing the handshake acknowledgement frame.

    Raises:
        TransportProtocolError: If the handshake payload fails validation.
    """

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
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    handlers: TransportHandlers,
) -> None:
    """Handle a single client connection life-cycle.

    Args:
        reader: Stream reader created from the accepted socket.
        writer: Stream writer associated with the client socket.
        handlers: Transport handler dispatch table.
    """

    peername = writer.get_extra_info("peername")
    sockname = writer.get_extra_info("sockname")
    correlation_id = uuid.uuid4().hex
    metadata = {
        "peer": str(peername),
        "socket": str(sockname),
        "correlation_id": correlation_id,
    }
    async with async_trace_section(
        "transport.connection", metadata=metadata
    ) as section:
        request: dict[str, Any] | None = None
        try:
            request = await _read_frame(reader)
            request_correlation_id = _normalize_correlation_id(
                request.get("correlation_id"), correlation_id
            )
            section.debug("handshake_request", correlation_id=request_correlation_id)
            response = _handshake_response(
                request, request_correlation_id=request_correlation_id
            )
            await _write_frame(writer, response)
            section.debug("handshake_ack_sent", correlation_id=request_correlation_id)
        except TransportConnectionClosed:
            section.debug("connection_closed_before_handshake")
            return
        except TransportProtocolError as exc:
            section.debug("protocol_error", error=str(exc))
            await _send_error(
                writer,
                status=400,
                correlation_id=_normalize_correlation_id(
                    request.get("correlation_id") if isinstance(request, dict) else None,
                    correlation_id,
                ),
                code="HANDSHAKE_ERROR",
                message=str(exc),
            )
            return
        except Exception as exc:  # pragma: no cover - defensive guard
            section.debug("unexpected_handshake_error", error=str(exc))
            await _send_error(
                writer,
                status=500,
                correlation_id=correlation_id,
                code="HANDSHAKE_FAILURE",
                message="Handshake failed due to internal error",
            )
            return

        try:
            while True:
                try:
                    frame = await _read_frame(reader)
                except TransportConnectionClosed:
                    break
                except TransportProtocolError as exc:
                    section.debug("protocol_error", error=str(exc))
                    await _send_error(
                        writer,
                        status=400,
                        correlation_id=correlation_id,
                        code="INVALID_FRAME",
                        message=str(exc),
                    )
                    continue

                frame_type = frame.get("type")
                if frame_type != "request":
                    section.debug("unexpected_frame_type", frame_type=frame_type)
                    await _send_error(
                        writer,
                        status=400,
                        correlation_id=_normalize_correlation_id(
                            frame.get("correlation_id"), correlation_id
                        ),
                        code="INVALID_FRAME_TYPE",
                        message=f"Expected frame type 'request', got {frame_type!r}",
                    )
                    continue

                path_value = frame.get("path")
                if not isinstance(path_value, str) or not path_value:
                    section.debug("missing_path", path=path_value)
                    await _send_error(
                        writer,
                        status=400,
                        correlation_id=_normalize_correlation_id(
                            frame.get("correlation_id"), correlation_id
                        ),
                        code="INVALID_PATH",
                        message="Request path must be a non-empty string",
                    )
                    continue
                path = path_value
                correlation = _normalize_correlation_id(
                    frame.get("correlation_id"), correlation_id
                )
                body = frame.get("body") or {}

                try:
                    status, payload = handlers.dispatch(path=path, body=body)
                except IndexUnavailableError as exc:
                    section.debug("index_unavailable", path=path, code=exc.code)
                    await _write_frame(
                        writer,
                        {
                            "type": "response",
                            "status": exc.status,
                            "correlation_id": correlation,
                            "body": exc.to_payload(),
                        },
                    )
                    continue
                except TransportError as exc:
                    section.debug("transport_error", path=path, code=exc.code)
                    await _write_frame(
                        writer,
                        {
                            "type": "response",
                            "status": exc.status,
                            "correlation_id": correlation,
                            "body": exc.to_payload(),
                        },
                    )
                    continue
                except (
                    Exception
                ) as exc:  # pragma: no cover - guard against unexpected failures
                    section.debug("handler_exception", error=str(exc), path=path)
                    await _send_error(
                        writer,
                        status=500,
                        correlation_id=correlation,
                        code="INTERNAL_ERROR",
                        message="Internal server error",
                    )
                    continue

                section.debug("request_ok", path=path, status=status)
                await _write_frame(
                    writer,
                    {
                        "type": "response",
                        "status": status,
                        "correlation_id": correlation,
                        "body": payload,
                    },
                )
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            finally:
                section.debug("connection_closed")


@asynccontextmanager
@trace_call
async def transport_server(
    *,
    socket_path: str | Path,
    backlog: int = 100,
    handlers: TransportHandlers | None = None,
) -> AsyncIterator[asyncio.AbstractServer]:
    """Start a Unix domain socket server for CLI transport traffic.

    Args:
        socket_path: Location of the socket file that clients will connect to.
        backlog: Maximum number of queued connections accepted by the listener.
        handlers: Transport handlers used to serve requests. When ``None``
            bootstrap handlers backed by static data are used.

    Yields:
        The running asyncio server instance for additional inspection if needed.
    """

    path = Path(socket_path)
    _ensure_socket_directory(path)

    active_handlers = handlers or create_default_handlers()
    connection_handler = functools.partial(_handle_connection, handlers=active_handlers)
    server = await asyncio.start_unix_server(
        connection_handler,
        path=str(path),
        backlog=backlog,
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


@trace_call
async def _send_error(
    writer: asyncio.StreamWriter,
    *,
    status: int,
    correlation_id: str,
    code: str,
    message: str,
    remediation: str | None = None,
) -> None:
    """Helper to send error responses for malformed frames.

    Args:
        writer: Stream writer associated with the client socket.
        status: HTTP-like status code to emit.
        correlation_id: Correlation identifier associated with the request.
        code: Stable error code describing the issue.
        message: Human-readable error message.
        remediation: Optional remediation guidance string.
    """

    body = {
        "code": code,
        "message": message,
    }
    if remediation:
        body["remediation"] = remediation
    await _write_frame(
        writer,
        {
            "type": "response",
            "status": status,
            "correlation_id": correlation_id,
            "body": body,
        },
    )
