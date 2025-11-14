"""Ollama adapter for embedding generation."""


import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from adapters.weaviate.client import Document
from telemetry import trace_call, trace_section


class EmbeddingMetrics(Protocol):
    """Interface for recording embedding metrics per alias."""

    def record_embedding(
        self, alias: str, vector_size: int, latency_ms: float
    ) -> None:  # pragma: no cover - Protocol
        ...


class HttpClient(Protocol):
    """Minimal HTTP client protocol required for Ollama interactions."""

    def post(
        self, url: str, json: dict[str, Any], timeout: float
    ) -> Any:  # pragma: no cover - Protocol
        ...


class GenerationMetrics(Protocol):
    """Interface for recording completion latency metrics."""

    def record_generation(
        self,
        alias: str,
        latency_ms: float,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:  # pragma: no cover - Protocol
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
        generation_metrics: GenerationMetrics | None = None,
        timeout: float = 30.0,
    ) -> None:
        """Initialize the adapter.

        Args:
            http_client: HTTP client capable of synchronous POST calls.
            base_url: Base URL for the local Ollama service.
            model: Embedding model identifier to invoke.
            metrics: Optional metrics recorder for embedding latency.
            generation_metrics: Optional metrics recorder for completion latency.
            timeout: Request timeout in seconds.

        Example:
            >>> adapter = OllamaAdapter(http_client=client, base_url="http://localhost:11434", model="embeddinggemma:latest")
        """

        self._http_client = http_client
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._metrics = metrics
        self._generation_metrics = generation_metrics
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
                    self._metrics.record_embedding(
                        document.alias, len(vector), elapsed_ms
                    )
                    section.debug(
                        "metrics_recorded",
                        alias=document.alias,
                        vector_length=len(vector),
                        latency_ms=elapsed_ms,
                    )

        return results

    @trace_call
    def generate_completion(
        self,
        *,
        prompt: str,
        alias: str,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate a completion using the configured Ollama model.

        Args:
            prompt: Prompt text sent to the Ollama completion endpoint.
            alias: Source alias associated with the request for metrics tagging.
            options: Optional dictionary of Ollama generation parameters.

        Returns:
            The JSON payload returned by the Ollama completion endpoint.
        """

        payload: dict[str, Any] = {"model": self._model, "prompt": prompt}
        if options:
            payload["options"] = options

        start = time.perf_counter()
        with trace_section(
            "ollama.generate",
            metadata={"alias": alias, "model": self._model},
        ) as section:
            response = self._http_client.post(
                f"{self._base_url}/api/generate", json=payload, timeout=self._timeout
            )
            body = response.json()
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            prompt_tokens = int(body.get("prompt_eval_count", 0))
            completion_tokens = int(body.get("eval_count", 0))
            if self._generation_metrics:
                self._generation_metrics.record_generation(
                    alias,
                    elapsed_ms,
                    prompt_tokens,
                    completion_tokens,
                )
            section.debug(
                "generation_complete",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            return body


__all__ = [
    "EmbeddingResult",
    "EmbeddingMetrics",
    "GenerationMetrics",
    "HttpClient",
    "OllamaAdapter",
]
