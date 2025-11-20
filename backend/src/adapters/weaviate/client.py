"""Weaviate vector adapter handling ingestion flows."""

import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from weaviate.collections.classes.filters import Filter

from ports.ingestion import SourceType
from telemetry import trace_call, trace_section


class IngestionMetrics(Protocol):
    """Interface for recording ingestion metrics per alias."""

    def record_ingestion(
        self, alias: str, count: int, latency_ms: float
    ) -> None:  # pragma: no cover - Protocol
        """Record document ingestion latency and counts.

        Args:
            alias: Source alias for which ingestion occurred.
            count: Number of documents ingested in the batch.
            latency_ms: Duration (in milliseconds) of the batch operation.
        """


class QueryMetrics(Protocol):
    """Interface for recording query latency per alias."""

    def record_query(
        self, alias: str, latency_ms: float, result_count: int
    ) -> None:  # pragma: no cover - Protocol
        """Record a query round-trip for observability dashboards.

        Args:
            alias: Source alias targeted by the retrieval query.
            latency_ms: Time spent executing the query call.
            result_count: Number of documents returned.
        """


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

    _QUERY_FIELDS = [
        "text",
        "checksum",
        "chunk_id",
        "source_alias",
        "source_type",
        "language",
        "embedding",
    ]

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

    def __enter__(self) -> "WeaviateAdapter":
        """Return the adapter instance for use within a context manager."""

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        """Ensure the underlying client closes when leaving a context block."""

        self.close()
        return False

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
            dynamic_method = getattr(batch, "dynamic", None)
            if callable(dynamic_method):
                self._ingest_dynamic_batch(
                    batch_wrapper=batch,
                    documents=doc_list,
                    alias_counts=alias_counts,
                    section=section,
                )
            else:
                self._ingest_legacy_batch(
                    batch_context=batch,
                    documents=doc_list,
                    alias_counts=alias_counts,
                    section=section,
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
            collections = getattr(self._client, "collections", None)
            if collections is not None and hasattr(collections, "get"):
                documents = self._query_with_collections(
                    collections=collections,
                    alias=alias,
                    source_type=source_type,
                    language=language,
                    limit=limit,
                )
            else:
                query_client = getattr(self._client, "query", None)
                if query_client is None:
                    raise ValueError("Weaviate client does not expose a query interface")
                documents = self._query_with_legacy_client(
                    query_client=query_client,
                    alias=alias,
                    source_type=source_type,
                    language=language,
                    limit=limit,
                )

            elapsed_ms = (time.perf_counter() - start) * 1000.0
            if self._query_metrics:
                self._query_metrics.record_query(alias, elapsed_ms, len(documents))
            section.debug("query_complete", result_count=len(documents))
            return documents

    @trace_call
    def close(self) -> None:
        """Close the underlying Weaviate client to prevent socket leaks.

        Example:
            >>> adapter = WeaviateAdapter(client=client, class_name="Document")
            >>> adapter.close()
        """

        client_close = getattr(self._client, "close", None)
        if callable(client_close):
            client_close()


    def _ingest_dynamic_batch(
        self,
        *,
        batch_wrapper: Any,
        documents: list[Document],
        alias_counts: dict[str, int],
        section: Any,
    ) -> None:
        dynamic_method = getattr(batch_wrapper, "dynamic", None)
        if not callable(dynamic_method):
            raise ValueError("batch wrapper missing dynamic()")
        context = dynamic_method()
        with context as batch_ctx:
            add_object = getattr(batch_ctx, "add_object", None)
            if add_object is None:
                raise ValueError("Weaviate batch context missing add_object")
            for document in documents:
                alias_counts[document.alias] = alias_counts.get(document.alias, 0) + 1
                payload = self._document_payload(document)
                add_object(
                    collection=self._class_name,
                    properties=payload,
                    uuid=document.document_id,
                )
                section.debug(
                    "document_enqueued",
                    alias=document.alias,
                    chunk_id=document.chunk_id,
                )

    def _ingest_legacy_batch(
        self,
        *,
        batch_context: Any,
        documents: list[Document],
        alias_counts: dict[str, int],
        section: Any,
    ) -> None:
        if not hasattr(batch_context, "__enter__"):
            raise ValueError("Weaviate client must expose a 'batch' context manager")
        with batch_context:
            for document in documents:
                alias_counts[document.alias] = alias_counts.get(document.alias, 0) + 1
                payload = self._document_payload(document)
                batch_context.add_data_object(  # type: ignore[attr-defined]
                    payload, class_name=self._class_name, uuid=document.document_id
                )
                section.debug(
                    "document_enqueued",
                    alias=document.alias,
                    chunk_id=document.chunk_id,
                )

    def _document_payload(self, document: Document) -> dict[str, Any]:
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
        return payload

    def _query_with_collections(
        self,
        *,
        collections: Any,
        alias: str,
        source_type: SourceType,
        language: str,
        limit: int,
    ) -> list[Document]:
        collection = collections.get(self._class_name)
        query_namespace = getattr(collection, "query", None)
        if query_namespace is None:
            raise ValueError("collections interface missing query namespace")

        filters = self._build_v4_filters(alias=alias, source_type=source_type, language=language)
        result = query_namespace.fetch_objects(  # type: ignore[call-arg]
            filters=filters,
            limit=limit,
            return_properties=self._QUERY_FIELDS,
        )
        records = getattr(result, "objects", None)
        if records is None:
            raise ValueError("collections interface returned unexpected payload")
        return [self._document_from_properties(obj.properties) for obj in records]

    def _build_v4_filters(
        self, *, alias: str, source_type: SourceType, language: str
    ) -> Any:
        return Filter.all_of(
            [
                Filter.by_property("source_alias").equal(alias),
                Filter.by_property("source_type").equal(source_type.value),
                Filter.by_property("language").equal(language),
            ]
        )

    def _query_with_legacy_client(
        self,
        *,
        query_client: Any,
        alias: str,
        source_type: SourceType,
        language: str,
        limit: int,
    ) -> list[Document]:
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

        builder = query_client.get(self._class_name, self._QUERY_FIELDS)
        response = builder.with_where(filters).with_limit(limit).do()
        raw_entries = response.get("data", {}).get("Get", {}).get(self._class_name, [])
        return [self._document_from_properties(entry) for entry in raw_entries]

    def _document_from_properties(self, payload: Mapping[str, Any]) -> Document:
        try:
            return Document(
                alias=str(payload["source_alias"]),
                checksum=str(payload["checksum"]),
                chunk_id=int(payload["chunk_id"]),
                text=str(payload["text"]),
                source_type=SourceType(str(payload["source_type"])),
                language=str(payload["language"]),
                embedding=payload.get("embedding"),
            )
        except KeyError as exc:
            raise ValueError("query result missing required field") from exc


__all__ = ["Document", "WeaviateAdapter", "IngestionMetrics", "QueryMetrics"]
