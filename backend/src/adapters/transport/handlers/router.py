"""Routing logic for Unix transport requests."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from ports import (
    HealthPort,
    IngestionPort,
    IngestionTrigger,
    QueryPort,
    QueryRequest,
    SourceCatalog,
    SourceRecord,
)
from ports.ingestion import SourceStatus
from telemetry import trace_call, trace_section

from .errors import IndexUnavailableError, TransportError
from .serializers import (
    serialize_catalog,
    serialize_ingestion_job,
    serialize_query_response,
    serialize_source_record,
)


@dataclass
class TransportHandlers:
    """Route transport frames to domain ports and serialize responses."""

    query_port: QueryPort
    ingestion_port: IngestionPort
    health_port: HealthPort | None = None
    _clock: Callable[[], dt.datetime] = field(
        default=lambda: dt.datetime.now(dt.timezone.utc)
    )

    def dispatch(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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
        raise TransportError(
            status=404,
            code="NOT_FOUND",
            message=f"Unknown path {path!r}",
        )

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

    def _handle_reindex(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
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

        job = self.ingestion_port.start_reindex(trigger)
        return 202, {"job": serialize_ingestion_job(job)}

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


__all__ = ["TransportHandlers"]
