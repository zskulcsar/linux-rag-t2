"""Weaviate vector adapter handling ingestion flows."""

from __future__ import annotations

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from services.rag_backend.ports.ingestion import SourceType
from services.rag_backend.telemetry import trace_call, trace_section


class IngestionMetrics(Protocol):
    """Interface for recording ingestion metrics per alias."""

    def record_ingestion(self, alias: str, count: int, latency_ms: float) -> None:  # pragma: no cover - Protocol
        ...


@dataclass(slots=True)
class Document:
    """Canonical document payload persisted to Weaviate.

    Attributes:
        alias: Knowledge source alias that produced the content.
        checksum: Checksum representing the content version.
        chunk_id: Sequential chunk identifier within the checksum scope.
        text: Raw chunk text forwarded to the vector store.
        source_type: Source category for filtering and metrics.
        language: ISO language code associated with the chunk.
        embedding: Optional embedding payload ready for persistence.

    Example:
        >>> doc = Document(
        ...     alias="man-pages",
        ...     checksum="abc123",
        ...     chunk_id=0,
        ...     text="chmod synopsis",
        ...     source_type=SourceType.MAN,
        ...     language="en",
        ... )
        >>> doc.document_id
        'man-pages:abc123:0'
    """

    alias: str
    checksum: str
    chunk_id: int
    text: str
    source_type: SourceType
    language: str
    embedding: Sequence[float] | None = None

    @property
    def document_id(self) -> str:
        """Return the deterministic document identifier.

        Returns:
            The identifier composed as ``<alias>:<checksum>:<chunk_id>``.

        Example:
            >>> Document(
            ...     alias="info-pages",
            ...     checksum="def456",
            ...     chunk_id=3,
            ...     text="info snippet",
            ...     source_type=SourceType.INFO,
            ...     language="en",
            ... ).document_id
            'info-pages:def456:3'
        """

        return f"{self.alias}:{self.checksum}:{self.chunk_id}"


class WeaviateAdapter:
    """Adapter responsible for batching document ingestion into Weaviate.

    Example:
        >>> adapter = WeaviateAdapter(client=client, class_name="Document")
        >>> adapter.ingest([doc])
    """

    @trace_call
    def __init__(
        self,
        *,
        client: Any,
        class_name: str,
        metrics: IngestionMetrics | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            client: Weaviate client exposing a ``batch`` context manager.
            class_name: Target class name for ingested documents.
            metrics: Optional metrics sink for ingestion counters.
        """

        self._client = client
        self._class_name = class_name
        self._metrics = metrics

    @trace_call
    def ingest(self, documents: Iterable[Document]) -> None:
        """Persist documents to Weaviate using the dynamic batch writer.

        Args:
            documents: Iterable of prepared :class:`Document` instances.

        Raises:
            ValueError: If the client does not expose a ``batch`` context.

        Example:
            >>> adapter.ingest([doc_a, doc_b])
        """

        doc_list = list(documents)
        if not doc_list:
            return

        batch = getattr(self._client, "batch", None)
        if batch is None:
            msg = "Weaviate client must expose a 'batch' context manager"
            raise ValueError(msg)

        alias_counts: dict[str, int] = {}
        start = time.perf_counter()

        with trace_section(
            "weaviate.ingest",
            metadata={"class_name": self._class_name, "document_count": len(doc_list)},
        ) as section:
            with batch:
                for document in doc_list:
                    alias_counts[document.alias] = alias_counts.get(document.alias, 0) + 1

                    payload = {
                        "text": document.text,
                        "source_alias": document.alias,
                        "source_type": document.source_type.value,
                        "language": document.language,
                        "checksum": document.checksum,
                        "chunk_id": document.chunk_id,
                    }
                    if document.embedding is not None:
                        payload["embedding"] = list(document.embedding)

                    batch.add_data_object(payload, class_name=self._class_name, uuid=document.document_id)
                    section.debug("document_enqueued", alias=document.alias, chunk_id=document.chunk_id)

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if self._metrics:
                for alias, count in alias_counts.items():
                    self._metrics.record_ingestion(alias, count, elapsed_ms)
                    section.debug("metrics_recorded", alias=alias, count=count, latency_ms=elapsed_ms)


__all__ = ["Document", "WeaviateAdapter", "IngestionMetrics"]
