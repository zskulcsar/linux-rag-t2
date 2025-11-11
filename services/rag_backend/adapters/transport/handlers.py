"""Request routing and serialization for Unix socket transport endpoints."""

from __future__ import annotations

import dataclasses
import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from services.rag_backend.ports import (
    HealthPort,
    HealthReport,
    HealthStatus,
    IngestionJob,
    IngestionPort,
    IngestionTrigger,
    QueryPort,
    QueryRequest,
    QueryResponse,
    Reference,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
)
from services.rag_backend.ports.ingestion import IngestionStatus, SourceStatus, SourceType
from services.rag_backend.ports.query import Citation
from services.rag_backend.telemetry import trace_call, trace_section


class TransportError(RuntimeError):
    """Base transport-level error mapped to standardized response payloads."""

    def __init__(self, *, status: int, code: str, message: str, remediation: str | None = None) -> None:
        """Initialize the transport error.

        Args:
            status: HTTP-like status code returned over the transport channel.
            code: Stable application error code.
            message: Human-readable error description.
            remediation: Optional remediation guidance presented to callers.
        """

        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.remediation = remediation

    def to_payload(self) -> dict[str, Any]:
        """Convert the error into a JSON-serializable payload.

        Returns:
            Dictionary containing the standardized error representation.
        """

        payload = {
            "code": self.code,
            "message": self.message,
        }
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload


class IndexUnavailableError(TransportError):
    """Raised when the content index is stale or missing."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        """Initialize a stale-index error.

        Args:
            code: Stable error code (``INDEX_STALE`` or ``INDEX_MISSING``).
            message: Human-readable description of the index issue.
            remediation: Recommended action for the operator.
        """

        super().__init__(status=409, code=code, message=message, remediation=remediation)


@dataclass
class TransportHandlers:
    """Route transport frames to domain ports and serialize responses."""

    query_port: QueryPort
    ingestion_port: IngestionPort
    health_port: HealthPort | None = None
    _clock: Callable[[], dt.datetime] = field(default=lambda: dt.datetime.now(dt.timezone.utc))

    def dispatch(self, path: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Dispatch a transport path to the appropriate handler.

        Args:
            path: Transport endpoint path (e.g., ``/v1/query``).
            body: Request body payload provided by the client.

        Returns:
            Tuple containing the status code and JSON-serializable payload.

        Raises:
            TransportError: If the request is malformed or the path is unknown.
            IndexUnavailableError: If the query port reports a stale index.
        """

        if path == "/v1/query":
            return self._handle_query(body)
        if path == "/v1/sources":
            return self._handle_list_sources()
        if path == "/v1/index/reindex":
            return self._handle_reindex(body)
        if path == "/v1/admin/init":
            return self._handle_admin_init()
        raise TransportError(status=404, code="NOT_FOUND", message=f"Unknown path {path!r}")

    def _handle_query(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Invoke the query port and serialize the structured response.

        Args:
            body: Request body payload decoded from the transport frame.

        Returns:
            Tuple containing the successful status code and serialized response.

        Raises:
            TransportError: If the request payload is malformed.
            IndexUnavailableError: Propagated when the index is stale or missing.
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
        except IndexUnavailableError:
            raise
        except TransportError:
            raise
        except Exception as exc:  # pragma: no cover - guard for unexpected failures
            raise TransportError(
                status=500,
                code="QUERY_FAILED",
                message="Query execution failed",
            ) from exc

        return 200, _serialize_query_response(response)

    def _handle_list_sources(self) -> tuple[int, dict[str, Any]]:
        """Return the catalog snapshot using the ingestion port.

        Returns:
            Tuple containing the status code and catalog payload.
        """

        catalog = self.ingestion_port.list_sources()
        return 200, _serialize_catalog(catalog)

    def _handle_reindex(self, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Trigger a reindex job and serialize the job metadata.

        Args:
            body: Request body payload containing the optional trigger field.

        Returns:
            Tuple containing the accepted status code and job payload.

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
        return 202, {"job": _serialize_ingestion_job(job)}

    @trace_call
    def _handle_admin_init(self) -> tuple[int, dict[str, Any]]:
        """Return the initialization status for admin bootstrap workflows.

        Returns:
            Tuple containing the successful status code and init payload.
        """

        catalog = self.ingestion_port.list_sources()
        metadata = {
            "catalog_version": catalog.version,
            "source_count": len(catalog.sources),
            "snapshot_count": len(catalog.snapshots),
        }

        with trace_section("transport.admin_init.catalog", metadata=metadata):
            _ensure_index_current(catalog)
            seeded_sources = [_serialize_source_record(source) for source in catalog.sources]
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
def _ensure_index_current(catalog: SourceCatalog) -> None:
    """Validate that the catalog index snapshots match active source metadata.

    Args:
        catalog: Catalog snapshot retrieved from the ingestion port.

    Raises:
        IndexUnavailableError: If the catalog lacks an index or the snapshots are stale.
    """

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

    snapshot_checksums: Dict[str, str] = {snapshot.alias: snapshot.checksum for snapshot in catalog.snapshots}
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


@trace_call
def _is_active_source(source: SourceRecord) -> bool:
    """Return ``True`` when a source is active.

    Args:
        source: Source record from the catalog.

    Returns:
        ``True`` if the source status is :attr:`SourceStatus.ACTIVE`.
    """

    status = source.status if isinstance(source.status, SourceStatus) else SourceStatus(str(source.status))
    return status is SourceStatus.ACTIVE


def _serialize_query_response(response: QueryResponse) -> dict[str, Any]:
    """Convert a :class:`QueryResponse` into a JSON-serializable mapping.

    Args:
        response: Query response returned by the application port.

    Returns:
        Dictionary following the transport schema for query responses.
    """

    payload = dataclasses.asdict(response)
    payload["citations"] = [dataclasses.asdict(citation) for citation in response.citations]
    payload["references"] = [dataclasses.asdict(reference) for reference in response.references]
    return payload


def _serialize_catalog(catalog: SourceCatalog) -> dict[str, Any]:
    """Serialize the source catalog to the transport schema.

    Args:
        catalog: Catalog snapshot representing current knowledge sources.

    Returns:
        Dictionary containing version, timestamps, sources, and snapshots.
    """

    return {
        "catalog_version": catalog.version,
        "updated_at": catalog.updated_at.isoformat(),
        "sources": [_serialize_source_record(source) for source in catalog.sources],
        "snapshots": [
            {"alias": snapshot.alias, "checksum": snapshot.checksum}
            for snapshot in catalog.snapshots
        ],
    }


def _serialize_source_record(record: SourceRecord) -> dict[str, Any]:
    """Serialize a single :class:`SourceRecord` to transport format.

    Args:
        record: Source record returned from the ingestion port.

    Returns:
        Dictionary matching the Source schema defined in the contract.
    """

    return {
        "alias": record.alias,
        "type": record.type.value if isinstance(record.type, SourceType) else str(record.type),
        "location": record.location,
        "language": record.language,
        "size_bytes": record.size_bytes,
        "last_updated": record.last_updated.isoformat(),
        "status": record.status.value if isinstance(record.status, SourceStatus) else str(record.status),
        "checksum": record.checksum,
        "notes": record.notes,
    }


def _serialize_ingestion_job(job: IngestionJob) -> dict[str, Any]:
    """Serialize an :class:`IngestionJob` to transport format.

    Args:
        job: Job metadata returned from the ingestion port.

    Returns:
        Dictionary containing job identifiers, timestamps, and status fields.
    """

    return {
        "job_id": job.job_id,
        "source_alias": job.source_alias,
        "status": job.status.value if isinstance(job.status, IngestionStatus) else str(job.status),
        "requested_at": job.requested_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "documents_processed": job.documents_processed,
        "stage": job.stage,
        "percent_complete": job.percent_complete,
        "error_message": job.error_message,
        "trigger": job.trigger.value if isinstance(job.trigger, IngestionTrigger) else str(job.trigger),
    }


class _StaticQueryPort(QueryPort):
    """Static query port used for bootstrap tests prior to real wiring."""

    def query(self, request: QueryRequest) -> QueryResponse:
        """Return a deterministic query response for contract tests.

        Args:
            request: Query request issued by the transport layer.

        Returns:
            QueryResponse populated with canned answer metadata.
        """

        references = [
            Reference(label="chmod(1)"),
            Reference(label="chown(1)", notes="Ownership management guidance"),
        ]
        citations = [
            Citation(alias="man-pages", document_ref="chmod.1"),
        ]
        return QueryResponse(
            summary="Use chmod to modify file permission bits.",
            steps=[
                "Invoke chmod with the desired octal mode (e.g., chmod 755 <file>).",
                "Verify the updated permissions with ls -l.",
            ],
            references=references,
            citations=citations,
            confidence=0.82,
            trace_id=request.trace_id or "bootstrap-trace",
            latency_ms=128,
            retrieval_latency_ms=48,
            llm_latency_ms=72,
            index_version="bootstrap-index",
            no_answer=False,
        )


class _StaticIngestionPort(IngestionPort):
    """Static ingestion port providing deterministic catalog metadata."""

    def __init__(self, *, clock: Callable[[], dt.datetime] | None = None) -> None:
        """Create the bootstrap ingestion port.

        Args:
            clock: Callable returning the current UTC time for deterministic tests.
        """

        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def list_sources(self) -> SourceCatalog:
        """Return a static catalog snapshot used by contract tests.

        Returns:
            SourceCatalog containing canned MAN and INFO sources.
        """

        now = self._clock()
        sources = [
            SourceRecord(
                alias="man-pages",
                type=SourceType.MAN,
                location="/usr/share/man",
                language="en",
                size_bytes=1024 * 1024 * 350,
                last_updated=now,
                status=SourceStatus.ACTIVE,
                checksum="sha256:bootstrap-man",
            ),
            SourceRecord(
                alias="info-pages",
                type=SourceType.INFO,
                location="/usr/share/info",
                language="en",
                size_bytes=1024 * 1024 * 120,
                last_updated=now,
                status=SourceStatus.ACTIVE,
                checksum="sha256:bootstrap-info",
            ),
        ]
        snapshots = [
            SourceSnapshot(alias="man-pages", checksum="sha256:bootstrap-man"),
            SourceSnapshot(alias="info-pages", checksum="sha256:bootstrap-info"),
        ]
        return SourceCatalog(version=1, updated_at=now, sources=sources, snapshots=snapshots)

    def create_source(self, request):  # pragma: no cover - future transport tasks
        """Placeholder for future create-source implementation."""
        raise NotImplementedError

    def update_source(self, alias, request):  # pragma: no cover - future transport tasks
        """Placeholder for future update-source implementation."""
        raise NotImplementedError

    def remove_source(self, alias):  # pragma: no cover - future transport tasks
        """Placeholder for future remove-source implementation."""
        raise NotImplementedError

    def start_reindex(self, trigger: IngestionTrigger) -> IngestionJob:
        """Return a deterministic reindex job.

        Args:
            trigger: Trigger type requested by the caller.

        Returns:
            IngestionJob representing a queued bootstrap job.
        """

        now = self._clock()
        return IngestionJob(
            job_id="bootstrap-job",
            source_alias="*",
            status=IngestionStatus.QUEUED,
            requested_at=now,
            started_at=None,
            completed_at=None,
            documents_processed=0,
            stage="queued",
            percent_complete=0.0,
            error_message=None,
            trigger=trigger,
        )


class _StaticHealthPort(HealthPort):
    """Static health port stub for bootstrap flows."""

    def evaluate(self) -> HealthReport:  # pragma: no cover - reserved for future use
        """Return a static health report with PASS status."""

        now = dt.datetime.now(dt.timezone.utc)
        return HealthReport(status=HealthStatus.PASS, generated_at=now, checks=[])


def create_default_handlers() -> TransportHandlers:
    """Create transport handlers backed by static bootstrap ports.

    Returns:
        TransportHandlers instance preconfigured for contract tests.
    """

    clock = lambda: dt.datetime.now(dt.timezone.utc)
    return TransportHandlers(
        query_port=_StaticQueryPort(),
        ingestion_port=_StaticIngestionPort(clock=clock),
        health_port=_StaticHealthPort(),
        _clock=clock,
    )


__all__ = [
    "TransportHandlers",
    "TransportError",
    "IndexUnavailableError",
    "create_default_handlers",
]
