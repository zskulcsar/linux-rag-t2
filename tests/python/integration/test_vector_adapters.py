"""Integration tests for Weaviate and Ollama vector adapters."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import math

from adapters.ollama.client import OllamaAdapter
from adapters.weaviate.client import Document, WeaviateAdapter
from ports.ingestion import SourceType


@dataclass
class _FakeBatch:
    """Simulate the weaviate client's dynamic batch context."""

    operations: list[dict[str, Any]] = field(default_factory=list)

    def __enter__(self) -> "_FakeBatch":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        """No-op context manager exit."""

    def add_data_object(
        self, data_object: dict[str, Any], class_name: str, uuid: str
    ) -> None:
        self.operations.append(
            {
                "data": data_object,
                "class_name": class_name,
                "uuid": uuid,
            }
        )


@dataclass
class _FakeWeaviateQueryBuilder:
    """Simulate the typed get/where/limit chaining API."""

    class_name: str
    fields: list[str]
    results: list[dict[str, Any]]
    where: dict[str, Any] | None = None
    limit: int | None = None

    def with_where(self, where: dict[str, Any]) -> "_FakeWeaviateQueryBuilder":
        self.where = where
        return self

    def with_limit(self, limit: int) -> "_FakeWeaviateQueryBuilder":
        self.limit = limit
        return self

    def do(self) -> dict[str, Any]:
        return {"data": {"Get": {self.class_name: self.results}}}


@dataclass
class _FakeWeaviateQuery:
    """Stub for the query builder entry point."""

    results: list[dict[str, Any]]
    last_builder: _FakeWeaviateQueryBuilder | None = None

    def get(self, class_name: str, fields: list[str]) -> _FakeWeaviateQueryBuilder:
        builder = _FakeWeaviateQueryBuilder(class_name, fields, self.results)
        self.last_builder = builder
        return builder


@dataclass
class _FakeWeaviateClient:
    """Stub exposing the interfaces used by the adapter."""

    batch: _FakeBatch = field(default_factory=_FakeBatch)
    query: _FakeWeaviateQuery = field(
        default_factory=lambda: _FakeWeaviateQuery(results=[])
    )


@dataclass
class _RecordingMetrics:
    """Capture per-alias ingestion counts for assertions."""

    ingestions: dict[str, int] = field(default_factory=dict)
    embeddings: dict[str, int] = field(default_factory=dict)
    queries: dict[str, tuple[float, int]] = field(default_factory=dict)
    generations: dict[str, tuple[float, int, int]] = field(default_factory=dict)

    def record_ingestion(self, alias: str, count: int, latency_ms: float) -> None:
        self.ingestions[alias] = self.ingestions.get(alias, 0) + count
        assert latency_ms >= 0.0

    def record_embedding(self, alias: str, vector_size: int, latency_ms: float) -> None:
        self.embeddings[alias] = self.embeddings.get(alias, 0) + vector_size
        assert latency_ms >= 0.0

    def record_query(self, alias: str, latency_ms: float, result_count: int) -> None:
        self.queries[alias] = (latency_ms, result_count)
        assert latency_ms >= 0.0

    def record_generation(
        self,
        alias: str,
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        self.generations[alias] = (latency_ms, prompt_tokens, completion_tokens)
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
    adapter = WeaviateAdapter(
        client=fake_client, class_name="Document", metrics=metrics
    )

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


def test_weaviate_adapter_query_applies_filters_and_records_metrics() -> None:
    """Ensure query enforces alias/type/language filters and records metrics."""

    query_results = [
        {
            "text": "chmod changes file mode.",
            "checksum": "abc123",
            "chunk_id": 0,
            "source_alias": "man-pages",
            "source_type": "man",
            "language": "en",
            "embedding": [0.1, 0.2, 0.3],
        }
    ]
    fake_query = _FakeWeaviateQuery(results=query_results)
    client = _FakeWeaviateClient(query=fake_query)
    metrics = _RecordingMetrics()
    adapter = WeaviateAdapter(
        client=client,
        class_name="Document",
        metrics=metrics,
        query_metrics=metrics,
    )

    documents = adapter.query_documents(
        alias="man-pages", source_type=SourceType.MAN, language="en", limit=5
    )

    assert len(documents) == 1
    assert documents[0].alias == "man-pages"
    assert documents[0].checksum == "abc123"

    builder = fake_query.last_builder
    assert builder is not None
    assert builder.limit == 5
    where = builder.where or {}
    operands = where.get("operands", [])
    assert any(
        op.get("path") == ["source_alias"] and op.get("valueString") == "man-pages"
        for op in operands
    )
    assert any(
        op.get("path") == ["source_type"] and op.get("valueString") == "man"
        for op in operands
    )
    assert any(
        op.get("path") == ["language"] and op.get("valueString") == "en"
        for op in operands
    )

    assert "man-pages" in metrics.queries
    _, result_count = metrics.queries["man-pages"]
    assert result_count == 1


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

    def post(self, url: str, payload: dict[str, Any], timeout: float) -> _FakeResponse:
        self.posts.append({"url": url, "payload": payload, "timeout": timeout})
        try:
            return next(self._response_iter)
        except StopIteration as exc:  # pragma: no cover - guard for test misuse
            raise AssertionError("no more fake responses configured") from exc


def _embedding_payload(vectors: Sequence[Sequence[float]]) -> dict[str, Any]:
    return {
        "model": "embeddinggemma:latest",
        "embeddings": [list(vector) for vector in vectors],
    }


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

    assert fake_client.posts[0]["url"].endswith("/api/embed")
    request_body = fake_client.posts[0]["payload"]
    assert request_body["model"] == "embeddinggemma:latest"
    assert request_body["input"] == [doc.text for doc in documents]

    assert metrics.embeddings == {"man-pages": 2, "info-pages": 2}


def test_ollama_adapter_generate_records_metrics() -> None:
    """Ensure generation requests call the API and record latency metrics."""

    fake_client = _FakeHttpClient(
        responses=[
            _FakeResponse(
                {
                    "response": "Answer text",
                    "prompt_eval_count": 12,
                    "eval_count": 34,
                }
            )
        ]
    )
    metrics = _RecordingMetrics()
    adapter = OllamaAdapter(
        http_client=fake_client,
        base_url="http://localhost:11434",
        model="gemma3:1b",
        metrics=metrics,
        generation_metrics=metrics,
    )

    result = adapter.generate_completion(prompt="Explain chmod", alias="man-pages")

    assert result["response"] == "Answer text"
    request = fake_client.posts[0]
    assert request["url"].endswith("/api/generate")
    assert request["payload"]["model"] == "gemma3:1b"
    assert request["payload"]["prompt"] == "Explain chmod"

    assert "man-pages" in metrics.generations
