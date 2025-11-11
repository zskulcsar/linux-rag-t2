"""Contract tests covering stale index rejection semantics."""

import asyncio
import json
from pathlib import Path

import pytest

from services.rag_backend.adapters.transport import (
    IndexUnavailableError,
    TransportHandlers,
    create_default_handlers,
    server,
)
from services.rag_backend.ports.query import QueryPort, QueryRequest, QueryResponse

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
    assert newline == b"\n", "transport must terminate frames with newline sentinel"

    return json.loads(payload.decode("utf-8"))


async def _connect_and_handshake(socket_path: Path) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    """Connect to the server and validate the handshake prior to issuing requests."""

    reader, writer = await asyncio.wait_for(
        asyncio.open_unix_connection(path=str(socket_path)), timeout=1
    )
    await asyncio.wait_for(_write_frame(writer, HANDSHAKE_REQUEST), timeout=1)
    handshake_response = await asyncio.wait_for(_read_frame(reader), timeout=1)

    assert handshake_response == {
        "type": "handshake_ack",
        "protocol": "rag-cli-ipc",
        "version": 1,
        "server": "rag-backend",
    }

    return reader, writer


@pytest.mark.asyncio
async def test_query_rejects_when_index_stale(tmp_path: Path) -> None:
    """`/v1/query` should reject requests with HTTP 409 when the index is stale."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-stale-index"

    handlers = create_default_handlers()

    class _StaleQueryPort(QueryPort):
        def query(self, request: QueryRequest) -> QueryResponse:
            raise IndexUnavailableError(
                code="INDEX_STALE",
                message="The active index is stale.",
                remediation="Reindex the catalog via ragadmin reindex.",
            )

    handlers.query_port = _StaleQueryPort()

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/query",
            "correlation_id": correlation_id,
            "body": {
                "question": "List users with sudo access.",
                "max_context_tokens": 4096,
                "trace_id": "contract-stale-trace",
            },
        }

        try:
            await asyncio.wait_for(_write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert response["type"] == "response"
    assert response["status"] == 409
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert body["code"] in {"INDEX_STALE", "INDEX_MISSING"}
    assert body["message"]
    assert body["remediation"]
