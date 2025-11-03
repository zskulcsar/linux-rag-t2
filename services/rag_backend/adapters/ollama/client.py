"""Ollama adapter for embedding generation."""

from __future__ import annotations

import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from services.rag_backend.adapters.weaviate.client import Document
from services.rag_backend.telemetry import trace_call, trace_section


class EmbeddingMetrics(Protocol):
    """Interface for recording embedding metrics per alias."""

    def record_embedding(self, alias: str, vector_size: int, latency_ms: float) -> None:  # pragma: no cover - Protocol
        ...


class HttpClient(Protocol):
    """Minimal HTTP client protocol required for Ollama interactions."""

    def post(self, url: str, json: dict[str, Any], timeout: float) -> Any:  # pragma: no cover - Protocol
        ...


@dataclass(slots=True)
class EmbeddingResult:
    """Embedding response associated with a document.

    Attributes:
        alias: Source alias associated with the embedding.
        checksum: Content checksum used for deterministic IDs.
        chunk_id: Chunk identifier within the source checksum.
        embedding: Dense embedding vector returned by Ollama.

    Example:
        >>> EmbeddingResult(alias="man-pages", checksum="abc", chunk_id=0, embedding=[0.1]).alias
        'man-pages'
    """

    alias: str
    checksum: str
    chunk_id: int
    embedding: list[float]


class OllamaAdapter:
    """Thin adapter around the Ollama embeddings endpoint."""

    @trace_call
    def __init__(
        self,
        *,
        http_client: HttpClient,
        base_url: str,
        model: str,
        metrics: EmbeddingMetrics | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the adapter.

        Args:
            http_client: HTTP client capable of synchronous POST calls.
            base_url: Base URL for the local Ollama service.
            model: Embedding model identifier to invoke.
            metrics: Optional metrics recorder for latency tracking.
            timeout: Request timeout in seconds.

        Example:
            >>> adapter = OllamaAdapter(http_client=client, base_url="http://localhost:11434", model="embeddinggemma:latest")
        """

        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._metrics = metrics
        self._timeout = timeout

    @trace_call
    def embed_documents(self, documents: Sequence[Document]) -> list[EmbeddingResult]:
        """Request embeddings for the provided documents."""

        if not documents:
            return []

        payload = {
            "model": self._model,
            "input": [document.text for document in documents],
        }
        response = self._http_client.post(
            f"{self._base_url}/api/embeddings", json=payload, timeout=self._timeout
        )
        body = response.json()
        embeddings = body.get("embeddings")
        if embeddings is None:
            raise ValueError("embedding response must include 'embeddings'")

        if len(embeddings) != len(documents):
            raise ValueError("embedding count must match input document count")

        start = time.perf_counter()
        results: list[EmbeddingResult] = []

        with trace_section(
            "ollama.embed",
            metadata={"model": self._model, "document_count": len(documents)},
        ) as section:
            for document, vector in zip(documents, embeddings, strict=True):
                vector_list = list(vector)
                results.append(
                    EmbeddingResult(
                        alias=document.alias,
                        checksum=document.checksum,
                        chunk_id=document.chunk_id,
                        embedding=vector_list,
                    )
                )
                section.debug(
                    "embedding_mapped",
                    alias=document.alias,
                    chunk_id=document.chunk_id,
                    vector_length=len(vector_list),
                )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if self._metrics:
                for document, vector in zip(documents, embeddings, strict=True):
                    self._metrics.record_embedding(document.alias, len(vector), elapsed_ms)
                    section.debug(
                        "metrics_recorded",
                        alias=document.alias,
                        vector_length=len(vector),
                        latency_ms=elapsed_ms,
                    )

        return results


__all__ = ["EmbeddingResult", "EmbeddingMetrics", "HttpClient", "OllamaAdapter"]
