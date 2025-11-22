"""Routing logic for Unix transport requests."""

import asyncio
import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Dict, Literal

from adapters.storage.audit_log import AuditLogger
from ports import (
    HealthPort,
    IngestionPort,
    IngestionTrigger,
    QueryPort,
    QueryRequest,
    SourceCatalog,
    SourceRecord,
)
from ports.ingestion import IngestionJob, ReindexCallbacks, SourceStatus
from telemetry import trace_call, trace_section

from common.serializers import (
    serialize_catalog,
    serialize_health_report,
    serialize_ingestion_job,
    serialize_query_response,
    serialize_source_record,
)

from .errors import IndexUnavailableError, TransportError

LOGGER = logging.getLogger(__name__)


@dataclass
class StreamingResponse:
    """Streaming payload returned from handlers for incremental updates."""

    initial_status: int
    initial_body: dict[str, Any]
    stream: AsyncIterator[dict[str, Any]]


@dataclass
class TransportHandlers:
    """Route transport frames to domain ports and serialize responses."""

    query_port: QueryPort
    ingestion_port: IngestionPort
    health_port: HealthPort | None = None
    audit_logger: AuditLogger | None = None
    _clock: Callable[[], dt.datetime] = field(
        default=lambda: dt.datetime.now(dt.timezone.utc)
    )
    _shutdown_hooks: list[Callable[[], None]] = field(default_factory=list, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)

    def __enter__(self) -> "TransportHandlers":
        """Return the handler collection for context-manager usage."""

        return self

    def __exit__(self, exc_type, exc, tb) -> Literal[False]:
        """Close the handler collection when exiting a context manager."""

        self.close()
        return False

    def dispatch(
        self, path: str, body: dict[str, Any]
    ) -> tuple[int, dict[str, Any]] | StreamingResponse:
        """Dispatch a transport path to the appropriate handler.

        Args:
            path: Transport endpoint path (e.g., ``/v1/query``).
            body: Request payload decoded from the transport frame.

        Returns:
            Tuple containing the HTTP-like status code and a serialized payload.

        Raises:
            TransportError: If the path is unknown or the request is malformed.
            IndexUnavailableError: When the query port reports a stale index.
        """

        if path == "/v1/query":
            return self._handle_query(body)
        if path == "/v1/sources":
            return self._handle_list_sources()
        if path == "/v1/index/reindex":
            return self._handle_reindex(body)
        if path == "/v1/admin/init":
            return self._handle_admin_init()
        if path == "/v1/admin/health":
            return self._handle_admin_health(body)
        raise TransportError(
            status=404,
            code="NOT_FOUND",
            message=f"Unknown path {path!r}",
        )

    def register_shutdown_hook(self, hook: Callable[[], None] | None) -> None:
        """Register a callable executed when close() runs.

        Args:
            hook: Callable that cleans up adapter state. ``None`` values are ignored.
        """

        if hook is None:
            return
        self._shutdown_hooks.append(hook)

    def close(self) -> None:
        """Run all registered shutdown hooks exactly once."""

        if self._closed:
            return
        for hook in self._shutdown_hooks:
            try:
                hook()
            except Exception as exc:  # pragma: no cover - defensive logging
                LOGGER.warning(
                    "TransportHandlers.close() :: hook_failed", exc_info=exc
                )
        self._closed = True

    def _handle_query(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Execute a query request and serialize the response.

        Args:
            body: Request payload containing the question and optional metadata.

        Returns:
            Status code and serialized :class:`QueryResponse`.

        Raises:
            TransportError: If the request payload is malformed.
            IndexUnavailableError: Propagated from the query port when the index
                is stale or missing.
        """
        if "question" not in body:
            raise TransportError(
                status=400,
                code="INVALID_REQUEST",
                message="Missing 'question' field in query request body",
            )

        try:
            request = QueryRequest(
                question=str(body["question"]),
                conversation_id=body.get("conversation_id"),
                max_context_tokens=int(body.get("max_context_tokens", 4096)),
                trace_id=body.get("trace_id"),
            )
        except (TypeError, ValueError) as exc:
            raise TransportError(
                status=400,
                code="INVALID_REQUEST",
                message="Query request fields are malformed",
            ) from exc

        try:
            response = self.query_port.query(request)
        except (TransportError, IndexUnavailableError):
            raise
        except Exception as exc:  # pragma: no cover
            raise TransportError(
                status=500,
                code="QUERY_FAILED",
                message="Query execution failed",
            ) from exc

        return 200, serialize_query_response(response)

    def _handle_list_sources(self) -> tuple[int, dict[str, Any]]:
        """Return the catalog snapshot using the ingestion port.

        Returns:
            Tuple containing the status code and catalog payload.
        """
        catalog = self.ingestion_port.list_sources()
        return 200, serialize_catalog(catalog)

    def _handle_reindex(self, body: dict[str, Any]) -> StreamingResponse:
        """Trigger a reindex job and serialize the job metadata.

        Args:
            body: Request payload containing an optional trigger override.

        Returns:
            Tuple of status code and serialized job payload.

        Raises:
            TransportError: If the trigger value is unsupported.
        """
        trigger_value = body.get("trigger", IngestionTrigger.MANUAL.value)
        try:
            trigger = IngestionTrigger(trigger_value)
        except ValueError as exc:
            raise TransportError(
                status=400,
                code="INVALID_TRIGGER",
                message=f"Unsupported reindex trigger {trigger_value!r}",
            ) from exc

        force_value = body.get("force", False)
        force_rebuild = force_value if isinstance(force_value, bool) else False
        stream = _JobStream(asyncio.get_running_loop())
        job = self.ingestion_port.start_reindex(
            trigger, force_rebuild=force_rebuild, callbacks=stream.callbacks
        )
        return StreamingResponse(
            initial_status=202,
            initial_body={"job": serialize_ingestion_job(job)},
            stream=stream,
        )

    @trace_call
    def _handle_admin_init(self) -> tuple[int, dict[str, Any]]:
        """Return initialization metadata for admin bootstrap workflows.

        Returns:
            Tuple containing the status code and initialization payload.
        """
        catalog = self.ingestion_port.list_sources()
        metadata = {
            "catalog_version": catalog.version,
            "source_count": len(catalog.sources),
            "snapshot_count": len(catalog.snapshots),
        }

        with trace_section("transport.admin_init.catalog", metadata=metadata):
            _ensure_index_current(catalog)
            seeded_sources = [
                serialize_source_record(source) for source in catalog.sources
            ]
            created_directories = [
                "~/.config/ragcli",
                "~/.local/share/ragcli",
                "~/.local/state/ragcli",
            ]
            return (
                200,
                {
                    "catalog_version": catalog.version,
                    "created_directories": created_directories,
                    "seeded_sources": seeded_sources,
                },
            )

    @trace_call
    def _handle_admin_health(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Return aggregated health diagnostics for admin workflows.

        Args:
            body: Request payload that may contain a ``trace_id`` field.

        Returns:
            Tuple of HTTP-like status and serialized health summary payload.

        Raises:
            TransportError: When no health port has been configured.

        Example:
            >>> handlers = TransportHandlers(  # doctest: +SKIP
            ...     query_port=..., ingestion_port=..., health_port=...
            ... )
            >>> status, payload = handlers._handle_admin_health({"trace_id": "trace"})  # doctest: +SKIP
            >>> status  # doctest: +SKIP
            200
        """

        body = body or {}

        if self.health_port is None:
            raise TransportError(
                status=503,
                code="HEALTH_UNAVAILABLE",
                message="Health diagnostics are unavailable on this backend.",
            )

        trace_id = _extract_trace_id(body)
        report = self.health_port.evaluate()
        payload = serialize_health_report(report)
        payload["trace_id"] = trace_id
        metadata = {
            "overall_status": payload["overall_status"],
            "trace_id": trace_id,
            "result_count": len(payload["results"]),
        }
        with trace_section("transport.admin_health.report", metadata=metadata):
            if self.audit_logger:
                self.audit_logger.log_admin_health(
                    overall_status=payload["overall_status"],
                    trace_id=trace_id,
                    results=payload["results"],
                )
        return 200, payload


def _ensure_index_current(catalog: SourceCatalog) -> None:
    """Validate that the catalog index snapshots match active source metadata."""

    if catalog.version <= 0 or not catalog.snapshots:
        raise IndexUnavailableError(
            code="INDEX_MISSING",
            message="No content index is available for the current catalog.",
            remediation="Run ragadmin reindex to build the knowledge index before continuing.",
        )

    snapshot_aliases = {snapshot.alias for snapshot in catalog.snapshots}
    if len(snapshot_aliases) != len(catalog.snapshots):
        raise IndexUnavailableError(
            code="INDEX_STALE",
            message="Duplicate index snapshots detected for the catalog.",
            remediation="Run ragadmin reindex to rebuild the index with a clean snapshot set.",
        )

    active_sources = [source for source in catalog.sources if _is_active_source(source)]
    active_aliases = {source.alias for source in active_sources}

    if snapshot_aliases != active_aliases:
        raise IndexUnavailableError(
            code="INDEX_STALE",
            message="Index snapshots do not align with active catalog sources.",
            remediation="Run ragadmin reindex to align the index with the current catalog.",
        )

    snapshot_checksums: Dict[str, str] = {
        snapshot.alias: snapshot.checksum for snapshot in catalog.snapshots
    }
    for source in active_sources:
        checksum = source.checksum
        if checksum is None:
            raise IndexUnavailableError(
                code="INDEX_STALE",
                message=f"Source {source.alias!r} is active without a recorded checksum.",
                remediation="Run ragadmin reindex to validate and snapshot active sources.",
            )

        snapshot_checksum = snapshot_checksums.get(source.alias)
        if snapshot_checksum != checksum:
            raise IndexUnavailableError(
                code="INDEX_STALE",
                message=f"Source {source.alias!r} has changed since the last index build.",
                remediation="Run ragadmin reindex to rebuild the index with the latest sources.",
            )


def _is_active_source(source: SourceRecord) -> bool:
    """Return ``True`` when the source is marked as active."""
    status = (
        source.status
        if isinstance(source.status, SourceStatus)
        else SourceStatus(str(source.status))
    )
    return status is SourceStatus.ACTIVE


def _extract_trace_id(body: dict[str, Any]) -> str:
    """Return a sanitized trace ID from the request body or generate one."""

    candidate = body.get("trace_id") if isinstance(body, dict) else None
    if isinstance(candidate, str):
        trimmed = candidate.strip()
        if trimmed:
            return trimmed
    return uuid.uuid4().hex


__all__ = ["TransportHandlers", "StreamingResponse"]


class _JobStream:
    """Async iterator that relays job snapshots from callbacks."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        self.callbacks = ReindexCallbacks(
            on_progress=self._enqueue_progress,
            on_complete=self._complete,
        )

    def _enqueue_progress(self, job: IngestionJob) -> None:
        """Schedule a serialized job snapshot for downstream consumers.

        Args:
            job: Latest job metadata emitted by the reindex service.
        """

        payload = {"job": serialize_ingestion_job(job)}
        self._loop.call_soon_threadsafe(self._queue.put_nowait, payload)

    def _complete(self, job: IngestionJob) -> None:
        """Finalize the stream by enqueueing the snapshot and sentinel.

        Args:
            job: Terminal job snapshot describing success or failure.
        """

        self._enqueue_progress(job)
        self._loop.call_soon_threadsafe(self._queue.put_nowait, None)

    def __aiter__(self) -> "_JobStream":
        """Return the async iterator interface for ``async for`` consumers."""

        return self

    async def __anext__(self) -> dict[str, Any]:
        """Yield the next payload from the queue or terminate the iterator.

        Returns:
            Serialized job payload suitable for transport framing.

        Raises:
            StopAsyncIteration: When the completion sentinel is observed.
        """

        payload = await self._queue.get()
        if payload is None:
            raise StopAsyncIteration
        return payload
