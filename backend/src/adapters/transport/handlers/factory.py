"""Factory helpers and bootstrap ports for transport handlers."""


import datetime as dt
from typing import Callable

from ports import (
    HealthPort,
    HealthReport,
    HealthStatus,
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
from ports.ingestion import IngestionJob, IngestionStatus, SourceStatus, SourceType
from ports.query import Citation

from .router import TransportHandlers


class _StaticQueryPort(QueryPort):
    """Static query port used for bootstrap tests prior to real wiring."""

    def query(self, request: QueryRequest) -> QueryResponse:
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
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

    def list_sources(self) -> SourceCatalog:
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
        return SourceCatalog(
            version=1, updated_at=now, sources=sources, snapshots=snapshots
        )

    def create_source(self, request):  # pragma: no cover - placeholders
        raise NotImplementedError

    def update_source(self, alias, request):  # pragma: no cover
        raise NotImplementedError

    def remove_source(self, alias):  # pragma: no cover
        raise NotImplementedError

    def start_reindex(self, trigger: IngestionTrigger) -> IngestionJob:
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

    def evaluate(self) -> HealthReport:
        now = dt.datetime.now(dt.timezone.utc)
        return HealthReport(status=HealthStatus.PASS, generated_at=now, checks=[])


def create_default_handlers() -> TransportHandlers:
    """Create transport handlers backed by static bootstrap ports."""

    def clock() -> dt.datetime:
        return dt.datetime.now(dt.timezone.utc)

    return TransportHandlers(
        query_port=_StaticQueryPort(),
        ingestion_port=_StaticIngestionPort(clock=clock),
        health_port=_StaticHealthPort(),
        _clock=clock,
    )


__all__ = ["create_default_handlers"]
