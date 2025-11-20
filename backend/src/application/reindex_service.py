"""Application-level orchestration for full catalog reindex operations."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
import datetime as dt
import hashlib
from pathlib import Path
import uuid
from typing import Callable, Protocol

from adapters.storage.audit_log import AuditLogger
from adapters.storage.catalog import CatalogStorage
from adapters.weaviate.client import Document
from application.source_catalog import _resolve_location, _stat_size
from domain.models import ContentIndexVersion, IndexStatus
from ports import ingestion as ingestion_ports
from telemetry import trace_call, trace_section


class ChunkBuilder(Protocol):
    """Protocol describing the chunk builder dependency."""

    def __call__(
        self,
        *,
        alias: str,
        checksum: str,
        location: Path,
        source_type: ingestion_ports.SourceType,
    ) -> Sequence[Document]:
        """Return chunked document payloads for ingestion."""


class ReindexService:
    """Coordinate full catalog reindex runs and persistence."""

    def __init__(
        self,
        *,
        storage: CatalogStorage,
        chunk_builder: ChunkBuilder,
        checksum_calculator: Callable[[Path], str],
        audit_logger: AuditLogger | None = None,
        index_writer: Callable[[ContentIndexVersion], None] | None = None,
        clock: Callable[[], dt.datetime] | None = None,
        job_id_factory: Callable[[], str] | None = None,
    ) -> None:
        """Store constructor dependencies for later execution."""

        self._storage = storage
        self._chunk_builder = chunk_builder
        self._checksum_calculator = checksum_calculator
        self._audit_logger = audit_logger
        self._index_writer = index_writer
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))
        self._job_id_factory = job_id_factory or (
            lambda: f"reindex-{uuid.uuid4().hex}"
        )

    @trace_call
    def run(
        self,
        trigger: ingestion_ports.IngestionTrigger,
        *,
        job_id: str | None = None,
        callbacks: ingestion_ports.ReindexCallbacks | None = None,
    ) -> ingestion_ports.IngestionJob:
        """Execute the reindex workflow and return the final job snapshot."""

        started_at = self._clock()
        job = ingestion_ports.IngestionJob(
            job_id=job_id or self._job_id_factory(),
            source_alias="*",
            status=ingestion_ports.IngestionStatus.RUNNING,
            requested_at=started_at,
            started_at=started_at,
            completed_at=None,
            documents_processed=0,
            stage="preparing_index",
            percent_complete=0.0,
            error_message=None,
            trigger=trigger,
        )
        self._emit_progress(callbacks, job)
        self._log_audit(
            status="started",
            job_id=job.job_id,
            details=None,
        )

        try:
            catalog = self._storage.load()
            active_sources = [
                record
                for record in catalog.sources
                if record.status == ingestion_ports.SourceStatus.ACTIVE
            ]
            total_sources = len(active_sources)
            processed_sources = 0
            documents_processed = 0
            updated_sources: list[ingestion_ports.SourceRecord] = []
            new_snapshots: list[ingestion_ports.SourceSnapshot] = []

            for record in catalog.sources:
                if record.status != ingestion_ports.SourceStatus.ACTIVE:
                    updated_sources.append(record)
                    continue

                alias = record.alias
                metadata = {"alias": alias}
                with trace_section("application.reindex", metadata=metadata):
                    location_path = _resolve_location(record.location)
                    checksum = self._checksum_calculator(location_path)
                    size_bytes = _stat_size(location_path)
                    changed = checksum != (record.checksum or "")
                    stage = f"skipping:{alias}"
                    documents: Sequence[Document] = []
                    if changed:
                        documents = self._chunk_builder(
                            alias=alias,
                            checksum=checksum,
                            location=location_path,
                            source_type=record.type,
                        )
                        documents_processed += len(documents)
                        stage = f"ingesting:{alias}"

                    refreshed_record = ingestion_ports.SourceRecord(
                        alias=alias,
                        type=record.type,
                        location=str(location_path),
                        language=record.language,
                        size_bytes=size_bytes,
                        last_updated=self._clock(),
                        status=record.status,
                        checksum=checksum,
                        notes=record.notes,
                    )
                    updated_sources.append(refreshed_record)
                    new_snapshots.append(
                        ingestion_ports.SourceSnapshot(alias=alias, checksum=checksum)
                    )

                processed_sources += 1
                percent_complete = (
                    100.0
                    if total_sources == 0
                    else (processed_sources / total_sources) * 100.0
                )
                job = replace(
                    job,
                    documents_processed=documents_processed,
                    stage=stage,
                    percent_complete=percent_complete,
                )
                self._emit_progress(callbacks, job)

            updated_sources.sort(key=lambda record: record.alias)
            new_catalog = ingestion_ports.SourceCatalog(
                version=catalog.version + 1,
                updated_at=self._clock(),
                sources=updated_sources,
                snapshots=new_snapshots,
            )
            self._storage.save(new_catalog)

            built_at = self._clock()
            index_version = ContentIndexVersion(
                index_id=str(uuid.uuid4()),
                status=IndexStatus.READY,
                checksum=self._snapshot_checksum(new_snapshots),
                source_snapshot=new_snapshots,
                size_bytes=self._active_size_bytes(updated_sources),
                document_count=documents_processed,
                trigger_job_id=job.job_id,
                built_at=built_at,
                freshness_expires_at=built_at + dt.timedelta(days=30),
                retrieval_latency_ms=None,
                llm_latency_ms=None,
            )
            if self._index_writer:
                self._index_writer(index_version)

            final_job = replace(
                job,
                status=ingestion_ports.IngestionStatus.SUCCEEDED,
                completed_at=built_at,
                stage="completed",
                percent_complete=100.0,
            )
            self._emit_completion(callbacks, final_job)
            self._log_audit(
                status="success",
                job_id=final_job.job_id,
                details=None,
            )
            return final_job
        except Exception as exc:  # pragma: no cover - defensive guard
            failed_job = replace(
                job,
                status=ingestion_ports.IngestionStatus.FAILED,
                completed_at=self._clock(),
                stage="failed",
                error_message=str(exc),
            )
            self._emit_completion(callbacks, failed_job)
            self._log_audit(
                status="failure",
                job_id=failed_job.job_id,
                details=str(exc),
            )
            raise

    def _emit_progress(
        self,
        callbacks: ingestion_ports.ReindexCallbacks | None,
        job: ingestion_ports.IngestionJob,
    ) -> None:
        """Invoke the progress callback when provided.

        Args:
            callbacks: Callback container supplied by the transport layer.
            job: Latest ingestion job snapshot describing current progress.
        """

        if callbacks and callbacks.on_progress:
            callbacks.on_progress(job)

    def _emit_completion(
        self,
        callbacks: ingestion_ports.ReindexCallbacks | None,
        job: ingestion_ports.IngestionJob,
    ) -> None:
        """Invoke the completion callback when provided.

        Args:
            callbacks: Callback container supplied by the transport layer.
            job: Final ingestion job snapshot representing success or failure.
        """

        if callbacks and callbacks.on_complete:
            callbacks.on_complete(job)

    def _snapshot_checksum(
        self, snapshots: Sequence[ingestion_ports.SourceSnapshot]
    ) -> str:
        """Return a deterministic checksum for the snapshot collection.

        Args:
            snapshots: Sequence of source snapshots included in the index.

        Returns:
            Hex-encoded SHA256 checksum derived from alias/checksum pairs.
        """

        digest = hashlib.sha256()
        for snapshot in sorted(snapshots, key=lambda snap: snap.alias):
            digest.update(snapshot.alias.encode("utf-8"))
            digest.update(snapshot.checksum.encode("utf-8"))
        return digest.hexdigest()

    def _active_size_bytes(
        self, sources: Sequence[ingestion_ports.SourceRecord]
    ) -> int:
        """Return the aggregate size (bytes) of active catalog sources.

        Args:
            sources: Catalog sources evaluated during the reindex run.

        Returns:
            Integer sum of ``size_bytes`` for active sources.
        """

        return sum(
            record.size_bytes
            for record in sources
            if record.status == ingestion_ports.SourceStatus.ACTIVE
        )

    def _log_audit(self, *, status: str, job_id: str, details: str | None) -> None:
        """Record a reindex audit entry when an audit logger is configured.

        Args:
            status: Status string describing the lifecycle event.
            job_id: Unique identifier for the associated ingestion job.
            details: Optional error or context string to persist.
        """

        if not self._audit_logger:
            return
        entry = {
            "timestamp": self._clock().isoformat(),
            "actor": "rag-backend",
            "action": "admin_reindex",
            "status": status,
            "target": job_id,
        }
        if details:
            entry["details"] = details
        self._audit_logger.append(entry)


__all__ = ["ChunkBuilder", "ReindexService"]
