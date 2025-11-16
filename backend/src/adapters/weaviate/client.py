"""Weaviate vector adapter handling ingestion flows."""

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ports.ingestion import SourceType
from telemetry import trace_call, trace_section


class IngestionMetrics(Protocol):
    """Interface for recording ingestion metrics per alias."""

    def record_ingestion(
        self, alias: str, count: int, latency_ms: float
    ) -> None:  # pragma: no cover - Protocol
        ...


class QueryMetrics(Protocol):
    """Interface for recording query latency per alias."""

    def record_query(
        self, alias: str, latency_ms: float, result_count: int
    ) -> None:  # pragma: no cover - Protocol
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
        query_metrics: QueryMetrics | None = None,
    ) -> None:
        """Initialize the adapter.

        Args:
            client: Weaviate client exposing a ``batch`` context manager.
            class_name: Target class name for ingested documents.
            metrics: Optional metrics sink for ingestion counters.
            query_metrics: Optional metrics sink for query latency recording.
        """

        self._client = client
        self._class_name = class_name
        self._metrics = metrics
        self._query_metrics = query_metrics

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
                    alias_counts[document.alias] = (
                        alias_counts.get(document.alias, 0) + 1
                    )

                    payload: dict[str, Any] = {
                        "text": document.text,
                        "source_alias": document.alias,
                        "source_type": document.source_type.value,
                        "language": document.language,
                        "checksum": document.checksum,
                        "chunk_id": document.chunk_id,
                    }
                    if document.embedding is not None:
                        payload["embedding"] = list(document.embedding)

                    batch.add_data_object(
                        payload, class_name=self._class_name, uuid=document.document_id
                    )
                    section.debug(
                        "document_enqueued",
                        alias=document.alias,
                        chunk_id=document.chunk_id,
                    )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if self._metrics:
                for alias, count in alias_counts.items():
                    self._metrics.record_ingestion(alias, count, elapsed_ms)
                    section.debug(
                        "metrics_recorded",
                        alias=alias,
                        count=count,
                        latency_ms=elapsed_ms,
                    )

    @trace_call
    def query_documents(
        self,
        *,
        alias: str,
        source_type: SourceType,
        language: str,
        limit: int = 10,
    ) -> list[Document]:
        """Query Weaviate for documents matching the required filters.

        Args:
            alias: Source alias to filter on.
            source_type: Source type (`man`, `kiwix`, or `info`) to filter on.
            language: Language filter to apply (e.g., ``"en"``).
            limit: Maximum number of documents to return. Defaults to ``10``.

        Returns:
            List of :class:`Document` instances satisfying the filters.

        Raises:
            ValueError: If the client does not expose the expected query API or
                the response payload is malformed.
        """

        if not alias or not language:
            raise ValueError("alias and language must be provided")

        query_client = getattr(self._client, "query", None)
        if query_client is None:
            raise ValueError("Weaviate client does not expose a query interface")

        filters = {
            "operator": "And",
            "operands": [
                {"path": ["source_alias"], "operator": "Equal", "valueString": alias},
                {
                    "path": ["source_type"],
                    "operator": "Equal",
                    "valueString": source_type.value,
                },
                {"path": ["language"], "operator": "Equal", "valueString": language},
            ],
        }

        start = time.perf_counter()
        with trace_section(
            "weaviate.query",
            metadata={
                "alias": alias,
                "source_type": source_type.value,
                "language": language,
                "limit": limit,
            },
        ) as section:
            builder = query_client.get(
                self._class_name,
                [
                    "text",
                    "checksum",
                    "chunk_id",
                    "source_alias",
                    "source_type",
                    "language",
                    "embedding",
                ],
            )
            response = builder.with_where(filters).with_limit(limit).do()
            raw_entries = (
                response.get("data", {}).get("Get", {}).get(self._class_name, [])
            )

            documents: list[Document] = []
            for entry in raw_entries:
                try:
                    document = Document(
                        alias=entry["source_alias"],
                        checksum=entry["checksum"],
                        chunk_id=int(entry["chunk_id"]),
                        text=entry["text"],
                        source_type=SourceType(entry["source_type"]),
                        language=entry["language"],
                        embedding=entry.get("embedding"),
                    )
                except KeyError as exc:
                    raise ValueError("query result missing required field") from exc
                documents.append(document)

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if self._query_metrics:
                self._query_metrics.record_query(alias, elapsed_ms, len(documents))
            section.debug("query_complete", result_count=len(documents))
            return documents


__all__ = ["Document", "WeaviateAdapter", "IngestionMetrics", "QueryMetrics"]
