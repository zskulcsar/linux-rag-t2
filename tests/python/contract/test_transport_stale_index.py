"""Contract tests covering stale index rejection semantics."""

import asyncio
from pathlib import Path

import pytest

from adapters.transport import IndexUnavailableError, server
from ports.query import QueryPort, QueryRequest, QueryResponse
from tests.python.helpers.ipc import (
    close_writer,
    connect_and_handshake,
    read_frame,
    write_frame,
)

HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "contract-tests",
}


@pytest.fixture(autouse=True)
def _fake_services(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_BACKEND_FAKE_SERVICES", "1")


@pytest.mark.asyncio
async def test_query_rejects_when_index_stale(
    tmp_path: Path, make_transport_handlers
) -> None:
    """`/v1/query` should reject requests with HTTP 409 when the index is stale."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-stale-index"

    handlers = make_transport_handlers()

    class _StaleQueryPort(QueryPort):
        def query(self, request: QueryRequest) -> QueryResponse:
            raise IndexUnavailableError(
                code="INDEX_STALE",
                message="The active index is stale.",
                remediation="Reindex the catalog via ragadmin reindex.",
            )

    handlers.query_port = _StaleQueryPort()

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

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
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(read_frame(reader), timeout=1)
        finally:
            await close_writer(writer)

    assert response["type"] == "response"
    assert response["status"] == 409
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert body["code"] in {"INDEX_STALE", "INDEX_MISSING"}
    assert body["message"]
    assert body["remediation"]
