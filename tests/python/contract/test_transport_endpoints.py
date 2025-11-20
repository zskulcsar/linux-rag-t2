"""Contract tests for Unix socket transport endpoints."""

import asyncio
import datetime as dt
from pathlib import Path
from typing import Any, cast

import pytest

from adapters.transport import server
from ports import (
    IngestionPort,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
)
from ports.ingestion import SourceStatus, SourceType
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
async def test_query_endpoint_returns_structured_response(tmp_path: Path) -> None:
    """`/v1/query` should return the structured query response contract."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-query"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

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
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(read_frame(reader), timeout=1)
        finally:
            await close_writer(writer)

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
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/sources",
            "correlation_id": correlation_id,
            "body": {},
        }

        try:
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(read_frame(reader), timeout=1)
        finally:
            await close_writer(writer)

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
async def test_reindex_endpoint_streams_job_updates(tmp_path: Path) -> None:
    """`/v1/index/reindex` should stream job progress frames until completion."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-reindex"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/index/reindex",
            "correlation_id": correlation_id,
            "body": {"trigger": "manual"},
        }

        frames: list[dict[str, Any]] = []
        try:
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            frames.append(await asyncio.wait_for(read_frame(reader), timeout=1))
            while frames[-1]["body"]["job"]["status"] not in {"succeeded", "failed"}:
                frames.append(await asyncio.wait_for(read_frame(reader), timeout=1))
        finally:
            await close_writer(writer)

    initial = frames[0]
    assert initial["type"] == "response"
    assert initial["status"] == 202
    assert initial["correlation_id"] == correlation_id
    assert isinstance(initial["body"].get("job"), dict)

    assert len(frames) >= 2, "expected at least one progress update frame"
    final_frame = frames[-1]
    assert final_frame["type"] == "response"
    assert final_frame["correlation_id"] == correlation_id

    job = final_frame["body"]["job"]
    assert job["status"] == "succeeded"
    assert job["stage"] == "completed"
    assert job["percent_complete"] == 100
    assert isinstance(job["documents_processed"], int)

    progress_stages = [frame["body"]["job"]["stage"] for frame in frames[:-1]]
    assert any(stage and stage.startswith("ingesting:") for stage in progress_stages)


@pytest.mark.asyncio
async def test_admin_init_endpoint_reports_dependency_checks(tmp_path: Path) -> None:
    """`/v1/admin/init` should return init results with seeded directories and sources."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
        }

        try:
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(read_frame(reader), timeout=1)
        finally:
            await close_writer(writer)

    assert response["type"] == "response"
    assert response["status"] == 200
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert isinstance(body.get("catalog_version"), int)
    assert isinstance(body.get("created_directories"), list)
    assert isinstance(body.get("seeded_sources"), list)


@pytest.mark.asyncio
async def test_admin_health_endpoint_returns_component_results(tmp_path: Path) -> None:
    """`/v1/admin/health` should return component health results and trace IDs."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-health"
    trace_id = "contract-health-trace"

    async with server.transport_server(socket_path=socket_path):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/admin/health",
            "correlation_id": correlation_id,
            "body": {"trace_id": trace_id},
        }

        try:
            await asyncio.wait_for(write_frame(writer, request), timeout=1)
            response = await asyncio.wait_for(read_frame(reader), timeout=1)
        finally:
            await close_writer(writer)

    assert response["type"] == "response"
    assert response["status"] == 200
    assert response["correlation_id"] == correlation_id

    body = response["body"]
    assert isinstance(body, dict)
    assert body.get("trace_id") == trace_id
    assert body.get("overall_status") in {"pass", "warn", "fail"}

    results = body.get("results")
    assert isinstance(results, list) and results, "expected component results"
    components = {result.get("component") for result in results if isinstance(result, dict)}
    assert {"disk_capacity", "index_freshness", "source_access"}.issubset(components)
    assert "ollama" in components and "weaviate" in components

@pytest.mark.asyncio
async def test_admin_init_rejects_when_index_missing(
    tmp_path: Path, make_transport_handlers
) -> None:
    """`/v1/admin/init` should reject when no index snapshot exists for the catalog."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init-missing"

    handlers = make_transport_handlers()

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
            self, trigger, *, force_rebuild=False, callbacks=None
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

    handlers.ingestion_port = cast(IngestionPort, _MissingIndexPort())

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
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
    assert body["code"] == "INDEX_MISSING"
    assert "reindex" in body["remediation"].lower()


@pytest.mark.asyncio
async def test_admin_init_rejects_when_catalog_newer_than_index(
    tmp_path: Path, make_transport_handlers
) -> None:
    """`/v1/admin/init` should reject when catalog checksums differ from index snapshots."""

    socket_path = tmp_path / "backend.sock"
    correlation_id = "contract-admin-init-stale"

    handlers = make_transport_handlers()

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
            self, trigger, *, force_rebuild=False, callbacks=None
        ):  # pragma: no cover - not needed for contract tests
            raise NotImplementedError

    handlers.ingestion_port = cast(IngestionPort, _StaleIndexPort())

    async with server.transport_server(socket_path=socket_path, handlers=handlers):
        reader, writer = await connect_and_handshake(
            socket_path, request=HANDSHAKE_REQUEST
        )

        request = {
            "type": "request",
            "path": "/v1/admin/init",
            "correlation_id": correlation_id,
            "body": {},
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
    assert body["code"] == "INDEX_STALE"
    assert "reindex" in body["remediation"].lower()
