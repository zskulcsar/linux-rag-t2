"""Integration tests for Weaviate and Ollama vector adapters."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import math

from services.rag_backend.adapters.ollama.client import OllamaAdapter
from services.rag_backend.adapters.weaviate.client import Document, WeaviateAdapter
from services.rag_backend.ports.ingestion import SourceType


@dataclass
class _FakeBatch:
    """Simulate the weaviate client's dynamic batch context."""

    operations: list[dict[str, Any]] = field(default_factory=list)

    def __enter__(self) -> "_FakeBatch":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        """No-op context manager exit."""

    def add_data_object(self, data_object: dict[str, Any], class_name: str, uuid: str) -> None:
        self.operations.append(
            {
                "data": data_object,
                "class_name": class_name,
                "uuid": uuid,
            }
        )


@dataclass
class _FakeWeaviateClient:
    """Stub exposing only the ``batch`` attribute used by the adapter."""

    batch: _FakeBatch = field(default_factory=_FakeBatch)


@dataclass
class _RecordingMetrics:
    """Capture per-alias ingestion counts for assertions."""

    ingestions: dict[str, int] = field(default_factory=dict)
    embeddings: dict[str, int] = field(default_factory=dict)

    def record_ingestion(self, alias: str, count: int, latency_ms: float) -> None:
        self.ingestions[alias] = self.ingestions.get(alias, 0) + count
        assert latency_ms >= 0.0

    def record_embedding(self, alias: str, vector_size: int, latency_ms: float) -> None:
        self.embeddings[alias] = self.embeddings.get(alias, 0) + vector_size
        assert latency_ms >= 0.0


def test_weaviate_adapter_batches_documents_and_records_metrics() -> None:
    """Ensure metadata and deterministic IDs survive ingestion with per-alias metrics."""

    documents = [
        Document(
            alias="man-pages",
            checksum="abc123",
            chunk_id=0,
            text="chmod changes file mode.",
            source_type=SourceType.MAN,
            language="en",
            embedding=[0.1, 0.2, 0.3],
        ),
        Document(
            alias="man-pages",
            checksum="abc123",
            chunk_id=1,
            text="chown alters file ownership.",
            source_type=SourceType.MAN,
            language="en",
            embedding=[0.4, 0.5, 0.6],
        ),
        Document(
            alias="info-pages",
            checksum="def456",
            chunk_id=0,
            text="info pages provide extended manuals.",
            source_type=SourceType.INFO,
            language="en",
            embedding=[0.7, 0.8, 0.9],
        ),
    ]

    fake_client = _FakeWeaviateClient()
    metrics = _RecordingMetrics()
    adapter = WeaviateAdapter(client=fake_client, class_name="Document", metrics=metrics)

    adapter.ingest(documents)

    assert len(fake_client.batch.operations) == len(documents)
    recorded_ids = {entry["uuid"] for entry in fake_client.batch.operations}
    expected_ids = {doc.document_id for doc in documents}
    assert recorded_ids == expected_ids

    for operation in fake_client.batch.operations:
        payload = operation["data"]
        assert payload["source_alias"] in {"man-pages", "info-pages"}
        assert payload["language"] == "en"
        assert payload["source_type"] in {"man", "info"}
        assert math.isclose(sum(payload["embedding"]), sum(payload["embedding"]))

    assert metrics.ingestions == {"man-pages": 2, "info-pages": 1}


@dataclass
class _FakeResponse:
    """Simple JSON response wrapper for the fake HTTP client."""

    payload: dict[str, Any]

    def json(self) -> dict[str, Any]:
        return self.payload


@dataclass
class _FakeHttpClient:
    """Capture POST requests and return queued responses."""

    responses: Iterable[_FakeResponse]
    posts: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._response_iter = iter(self.responses)

    def post(self, url: str, json: dict[str, Any], timeout: float) -> _FakeResponse:
        self.posts.append({"url": url, "json": json, "timeout": timeout})
        try:
            return next(self._response_iter)
        except StopIteration as exc:  # pragma: no cover - guard for test misuse
            raise AssertionError("no more fake responses configured") from exc


def _embedding_payload(vectors: Sequence[Sequence[float]]) -> dict[str, Any]:
    return {"model": "embeddinggemma:latest", "embeddings": [list(vector) for vector in vectors]}


def test_ollama_adapter_returns_embeddings_and_records_metrics() -> None:
    """Ensure embeddings align with documents and metrics record vector sizes per alias."""

    documents = [
        Document(
            alias="man-pages",
            checksum="abc123",
            chunk_id=0,
            text="chmod synopsis chunk",
            source_type=SourceType.MAN,
            language="en",
        ),
        Document(
            alias="info-pages",
            checksum="def456",
            chunk_id=0,
            text="info overview chunk",
            source_type=SourceType.INFO,
            language="en",
        ),
    ]

    fake_client = _FakeHttpClient(
        responses=[_FakeResponse(_embedding_payload([[0.1, 0.2], [0.3, 0.4]]))]
    )
    metrics = _RecordingMetrics()
    adapter = OllamaAdapter(
        http_client=fake_client,
        base_url="http://localhost:11434",
        model="embeddinggemma:latest",
        metrics=metrics,
    )

    results = adapter.embed_documents(documents)

    assert len(results) == 2
    assert results[0].alias == "man-pages"
    assert results[0].embedding == [0.1, 0.2]
    assert results[1].alias == "info-pages"
    assert results[1].embedding == [0.3, 0.4]

    assert fake_client.posts[0]["url"].endswith("/api/embeddings")
    request_body = fake_client.posts[0]["json"]
    assert request_body["model"] == "embeddinggemma:latest"
    assert request_body["input"] == [doc.text for doc in documents]

    assert metrics.embeddings == {"man-pages": 2, "info-pages": 2}

