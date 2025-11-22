"""Unit tests for the transport handler factory."""

import datetime as dt
from pathlib import Path

import pytest

from adapters.storage.catalog import CatalogStorage
from adapters.transport.handlers import IndexUnavailableError
from adapters.transport.handlers import factory as handler_factory
from adapters.ollama.client import EmbeddingResult
from adapters.weaviate.client import Document
from ports.health import HealthComponent
from ports.ingestion import (
    IngestionStatus,
    IngestionTrigger,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
)
from ports.query import QueryRequest


@pytest.fixture(autouse=True)
def _fake_services_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_BACKEND_FAKE_SERVICES", "1")


def _seed_catalog(storage: CatalogStorage) -> None:
    """Persist a catalog snapshot with active sources for query tests."""

    now = dt.datetime(2025, 1, 2, 12, tzinfo=dt.timezone.utc)
    sources = [
        SourceRecord(
            alias="man-pages",
            type=SourceType.MAN,
            location="/usr/share/man",
            language="en",
            size_bytes=1024,
            last_updated=now,
            status=SourceStatus.ACTIVE,
            checksum="sha256:man",
        ),
        SourceRecord(
            alias="info-pages",
            type=SourceType.INFO,
            location="/usr/share/info",
            language="en",
            size_bytes=2048,
            last_updated=now,
            status=SourceStatus.ACTIVE,
            checksum="sha256:info",
        ),
    ]
    snapshots = [
        SourceSnapshot(alias="man-pages", checksum="sha256:man"),
        SourceSnapshot(alias="info-pages", checksum="sha256:info"),
    ]
    catalog = SourceCatalog(
        version=1,
        updated_at=now,
        sources=sources,
        snapshots=snapshots,
    )
    storage.save(catalog)


def test_query_port_requires_index_presence(
    monkeypatch: pytest.MonkeyPatch,
    make_transport_handlers,
) -> None:
    """Query requests should raise when no index snapshot exists."""

    monkeypatch.setenv("RAG_BACKEND_DISABLE_BOOTSTRAP", "1")
    handlers = make_transport_handlers()
    request = QueryRequest(question="How do I change file permissions?")

    with pytest.raises(IndexUnavailableError):
        handlers.query_port.query(request)


def test_query_port_reflects_catalog_metadata(
    catalog_storage: CatalogStorage,
    monkeypatch: pytest.MonkeyPatch,
    make_transport_handlers,
) -> None:
    """Query responses should incorporate catalog metadata when the index exists."""

    monkeypatch.setenv("RAG_BACKEND_DISABLE_BOOTSTRAP", "1")
    _seed_catalog(catalog_storage)

    handlers = make_transport_handlers()
    response = handlers.query_port.query(
        QueryRequest(
            question="How do I change file permissions?",
            max_context_tokens=2048,
            trace_id="unit-test-trace",
        )
    )

    assert response.trace_id == "unit-test-trace"
    assert 0.0 <= response.confidence <= 1.0


def test_ingestion_port_start_reindex_returns_job(
    catalog_storage: CatalogStorage,
    monkeypatch: pytest.MonkeyPatch,
    make_transport_handlers,
) -> None:
    """start_reindex should return an IngestionJob with sensible defaults."""

    monkeypatch.setenv("RAG_BACKEND_DISABLE_BOOTSTRAP", "1")
    _seed_catalog(catalog_storage)

    handlers = make_transport_handlers()
    job = handlers.ingestion_port.start_reindex(IngestionTrigger.MANUAL)

    assert job.source_alias == "*"
    assert job.status in {IngestionStatus.QUEUED, IngestionStatus.RUNNING}
    assert job.stage is not None
    assert job.trigger is IngestionTrigger.MANUAL


def test_chunk_builder_embeds_and_ingests(tmp_path: Path) -> None:
    """Chunk builder should embed generated chunks and forward them to Weaviate."""

    text_path = tmp_path / "source.txt"
    text_path.write_text("line 1\nline 2\nline 3", encoding="utf-8")
    embedding = _StubOllamaAdapter()
    vector = _StubWeaviateAdapter()

    builder = handler_factory._chunk_builder_factory(
        embedding_adapter=embedding,
        vector_adapter=vector,
        max_chunk_tokens=4,
    )

    documents = builder(
        alias="man-pages",
        checksum="abc123",
        location=text_path,
        source_type=SourceType.MAN,
    )

    assert documents, "expected at least one generated document"
    assert embedding.calls, "expected embeddings to be requested"
    assert vector.calls, "expected ingestion to receive the documents"
    assert len(vector.calls) == len(documents)
    for call in vector.calls:
        assert len(call) == 1
        assert call[0].embedding is not None


def test_chunk_builder_handles_missing_source_gracefully(tmp_path: Path) -> None:
    """Missing source files should not raise errors and return an empty plan."""

    embedding = _StubOllamaAdapter()
    vector = _StubWeaviateAdapter()
    builder = handler_factory._chunk_builder_factory(
        embedding_adapter=embedding,
        vector_adapter=vector,
    )

    documents = builder(
        alias="info-pages",
        checksum="def456",
        location=tmp_path / "missing.txt",
        source_type=SourceType.INFO,
    )

    assert documents == []
    assert embedding.calls == []
    assert vector.calls == []


def test_chunk_builder_raises_on_embedding_error(tmp_path: Path) -> None:
    """Embedding failures should propagate to callers."""

    text_path = tmp_path / "source.txt"
    text_path.write_text("data", encoding="utf-8")
    embedding = _FailingOllamaAdapter()
    vector = _StubWeaviateAdapter()

    builder = handler_factory._chunk_builder_factory(
        embedding_adapter=embedding,
        vector_adapter=vector,
    )

    with pytest.raises(RuntimeError, match="embedding failed"):
        builder(
            alias="man-pages",
            checksum="abc123",
            location=text_path,
            source_type=SourceType.MAN,
        )


def test_chunk_builder_raises_on_ingestion_error(tmp_path: Path) -> None:
    """Vector ingestion failures should propagate to callers."""

    text_path = tmp_path / "source.txt"
    text_path.write_text("data", encoding="utf-8")
    embedding = _StubOllamaAdapter()
    vector = _FailingWeaviateAdapter()

    builder = handler_factory._chunk_builder_factory(
        embedding_adapter=embedding,
        vector_adapter=vector,
    )

    with pytest.raises(RuntimeError, match="vector ingestion failed"):
        builder(
            alias="info-pages",
            checksum="def456",
            location=text_path,
            source_type=SourceType.INFO,
        )


def test_health_port_reports_dependency_checks(
    catalog_storage: CatalogStorage,
    monkeypatch: pytest.MonkeyPatch,
    make_transport_handlers,
) -> None:
    """Health port should include Ollama, Weaviate, and Phoenix dependency checks."""

    monkeypatch.setenv("RAG_BACKEND_DISABLE_BOOTSTRAP", "1")
    monkeypatch.setenv("RAG_BACKEND_PHOENIX_URL", "http://phoenix.local")
    _seed_catalog(catalog_storage)
    handlers = make_transport_handlers()

    report = handlers.health_port.evaluate()
    components = {check.component for check in report.checks}
    assert HealthComponent.OLLAMA in components
    assert HealthComponent.WEAVIATE in components
    assert HealthComponent.PHOENIX in components


class _StubOllamaAdapter:
    def __init__(self) -> None:
        self.calls: list[list[Document]] = []

    def embed_documents(self, documents: list[Document]) -> list[EmbeddingResult]:
        self.calls.append(documents)
        results: list[EmbeddingResult] = []
        for document in documents:
            results.append(
                EmbeddingResult(
                    alias=document.alias,
                    checksum=document.checksum,
                    chunk_id=document.chunk_id,
                    embedding=[float(document.chunk_id)],
                )
            )
        return results


class _StubWeaviateAdapter:
    def __init__(self) -> None:
        self.calls: list[list[Document]] = []

    def ingest(self, documents: list[Document]) -> None:
        self.calls.append(list(documents))


class _FailingOllamaAdapter(_StubOllamaAdapter):
    def embed_documents(self, documents: list[Document]) -> list[EmbeddingResult]:
        raise RuntimeError("embedding boom")


class _FailingWeaviateAdapter(_StubWeaviateAdapter):
    def ingest(self, documents: list[Document]) -> None:
        raise RuntimeError("ingest boom")
