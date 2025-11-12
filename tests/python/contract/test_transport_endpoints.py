"""Contract tests for Unix socket transport endpoints."""

import asyncio
import datetime as dt
import json
from pathlib import Path
from typing import cast

import pytest

from services.rag_backend.adapters.transport import create_default_handlers, server
from services.rag_backend.ports import (
    IngestionPort,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
)
from services.rag_backend.ports.ingestion import SourceStatus, SourceType

HANDSHAKE_REQUEST = {
    "type": "handshake",
    "protocol": "rag-cli-ipc",
    "version": 1,
    "client": "contract-tests",
}


async def _write_frame(writer: asyncio.StreamWriter, message: dict) -> None:
    """Send a framed JSON message using <len>\\n<payload>\\n semantics."""

    body = json.dumps(message, separators=(",", ":"), sort_keys=True).encode("utf-8")
    header = f"{len(body)}\n".encode("ascii")
    writer.write(header)
    writer.write(body)
    writer.write(b"\n")
    await writer.drain()


async def _read_frame(reader: asyncio.StreamReader) -> dict:
    """Read a framed JSON message using <len>\\n<payload>\\n semantics."""

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


async def _connect_and_handshake(
    socket_path: Path,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
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
async def test_query_endpoint_returns_structured_response(tmp_path: Path) -> None:
    """`/v1/query` should return the structured query response contract."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-query"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/query",
            "correlation_id": correlation_id,
            "body": {
                "question": "How do I change file permissions?",
                "max_context_tokens": 4096,
                "trace_id": "contract-trace",
            },
        }

        try:
            await asyncio.wait_for(_write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert response["type"] == "response"
    assert response["status"] == 200
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert "summary" in body and body["summary"]
    assert isinstance(body.get("steps"), list)
    assert isinstance(body.get("references"), list)
    assert isinstance(body.get("confidence"), (int, float))
    assert body.get("trace_id")


@pytest.mark.asyncio
async def test_sources_endpoint_lists_catalog_snapshot(tmp_path: Path) -> None:
    """`/v1/sources` should provide the catalog snapshot with metadata."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-sources"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/sources",
            "correlation_id": correlation_id,
            "body": {},
        }

        try:
            await asyncio.wait_for(_write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert response["type"] == "response"
    assert response["status"] == 200
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert isinstance(body.get("catalog_version"), int)
    sources = body.get("sources")
    assert isinstance(sources, list)
    assert sources, "expected at least one source record in catalog listing"
    first = sources[0]
    assert "alias" in first and "type" in first and "status" in first


@pytest.mark.asyncio
async def test_reindex_endpoint_triggers_ingestion_job(tmp_path: Path) -> None:
    """`/v1/index/reindex` should accept the request and return job metadata."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-reindex"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/index/reindex",
            "correlation_id": correlation_id,
            "body": {"trigger": "manual"},
        }

        try:
            await asyncio.wait_for(_write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert response["type"] == "response"
    assert response["status"] == 202
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert "job" in body
    assert isinstance(body["job"], dict)
    assert body["job"].get("status") in {"queued", "running", "succeeded", "failed"}


@pytest.mark.asyncio
async def test_admin_init_endpoint_reports_dependency_checks(tmp_path: Path) -> None:
    """`/v1/admin/init` should return init results with seeded directories and sources."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
        }

        try:
            await asyncio.wait_for(_write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(_read_frame(reader), timeout=1)
        finally:
            writer.close()
            await writer.wait_closed()

    assert response["type"] == "response"
    assert response["status"] == 200
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert isinstance(body.get("catalog_version"), int)
    assert isinstance(body.get("created_directories"), list)
    assert isinstance(body.get("seeded_sources"), list)


@pytest.mark.asyncio
async def test_admin_init_rejects_when_index_missing(tmp_path: Path) -> None:
    """`/v1/admin/init` should reject when no index snapshot exists for the catalog."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init-missing"

    handlers = create_default_handlers()

    class _MissingIndexPort:
        def list_sources(self) -> SourceCatalog:
            now = dt.datetime.now(dt.timezone.utc)
            return SourceCatalog(version=0, updated_at=now, sources=[], snapshots=[])

        def create_source(
            self, request
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def update_source(
            self, alias, request
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def remove_source(
            self, alias
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def start_reindex(
            self, trigger
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

    handlers.ingestion_port = cast(IngestionPort, _MissingIndexPort())

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
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
    assert body["code"] == "INDEX_MISSING"
    assert "reindex" in body["remediation"].lower()


@pytest.mark.asyncio
async def test_admin_init_rejects_when_catalog_newer_than_index(tmp_path: Path) -> None:
    """`/v1/admin/init` should reject when catalog checksums differ from index snapshots."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init-stale"

    handlers = create_default_handlers()

    class _StaleIndexPort:
        def list_sources(self) -> SourceCatalog:
            now = dt.datetime.now(dt.timezone.utc)
            sources = [
                SourceRecord(
                    alias="man-pages",
                    type=SourceType.MAN,
                    location="/usr/share/man",
                    language="en",
                    size_bytes=1024,
                    last_updated=now,
                    status=SourceStatus.ACTIVE,
                    checksum="sha256:newer-man",
                ),
                SourceRecord(
                    alias="info-pages",
                    type=SourceType.INFO,
                    location="/usr/share/info",
                    language="en",
                    size_bytes=512,
                    last_updated=now,
                    status=SourceStatus.ACTIVE,
                    checksum="sha256:bootstrap-info",
                ),
            ]
            snapshots = [
                SourceSnapshot(alias="man-pages", checksum="sha256:bootstrap-man"),
                SourceSnapshot(alias="info-pages", checksum="sha256:bootstrap-info"),
            ]
            return SourceCatalog(
                version=2, updated_at=now, sources=sources, snapshots=snapshots
            )

        def create_source(
            self, request
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def update_source(
            self, alias, request
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def remove_source(
            self, alias
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

        def start_reindex(
            self, trigger
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

    handlers.ingestion_port = cast(IngestionPort, _StaleIndexPort())

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await _connect_and_handshake(socket_path)

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
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
    assert body["code"] == "INDEX_STALE"
    assert "reindex" in body["remediation"].lower()
