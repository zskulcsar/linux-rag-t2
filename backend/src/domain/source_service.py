"""Domain services for managing knowledge sources and ingestion jobs."""

import datetime as dt
from dataclasses import replace
from typing import Callable

from common.clock import utc_now

from . import models

Clock = Callable[[], dt.datetime]


class SourceService:
    """Encapsulate catalog and ingestion lifecycle operations.

    Args:
        clock: Callable supplying the current UTC timestamp. Defaults to
            :func:`common.clock.utc_now`.
    """

    def __init__(self, clock: Clock | None = None) -> None:
        """Initialize the service with an optional clock override.

        Args:
            clock: Callable returning the current UTC time. When ``None``, the
                service uses :func:`common.clock.utc_now`.
        """

        self._clock = clock or utc_now

    def mark_source_validated(
        self,
        *,
        source: models.KnowledgeSource,
        checksum: str,
        size_bytes: int,
    ) -> models.KnowledgeSource:
        """Promote a pending source to active after validation and ingestion.

        Args:
            source: Source currently awaiting validation.
            checksum: Content checksum recorded for the source.
            size_bytes: Size of the validated content on disk.

        Returns:
            An updated :class:`KnowledgeSource` marked active.

        Raises:
            ValueError: If the source is not pending validation.
        """

        if source.status is not models.KnowledgeSourceStatus.PENDING_VALIDATION:
            raise ValueError("source must be pending validation")

        now = self._clock()
        return replace(
            source,
            status=models.KnowledgeSourceStatus.ACTIVE,
            checksum=checksum,
            size_bytes=size_bytes,
            last_updated=now,
            updated_at=now,
        )

    def mark_source_quarantined(
        self,
        *,
        source: models.KnowledgeSource,
        reason: str,
    ) -> models.KnowledgeSource:
        """Move an active source into quarantine with contextual notes.

        Args:
            source: Source to quarantine.
            reason: Human-readable explanation recorded in the notes field.

        Returns:
            An updated :class:`KnowledgeSource` in the ``QUARANTINED`` state.

        Raises:
            ValueError: If the source is not active or in error.
        """

        if source.status not in (
            models.KnowledgeSourceStatus.ACTIVE,
            models.KnowledgeSourceStatus.ERROR,
        ):
            raise ValueError("only active or errored sources can be quarantined")

        now = self._clock()
        notes = reason if not source.notes else f"{source.notes}\n{reason}"
        return replace(
            source,
            status=models.KnowledgeSourceStatus.QUARANTINED,
            notes=notes,
            updated_at=now,
        )

    def mark_source_error(
        self,
        *,
        source: models.KnowledgeSource,
        reason: str,
    ) -> models.KnowledgeSource:
        """Mark a source as errored due to ingestion failures.

        Args:
            source: Source whose ingestion failed.
            reason: Human-readable explanation appended to the notes field.

        Returns:
            Updated :class:`KnowledgeSource` in the ``ERROR`` state.

        Raises:
            ValueError: If the source is already quarantined or errored.
        """

        if source.status in (
            models.KnowledgeSourceStatus.QUARANTINED,
            models.KnowledgeSourceStatus.ERROR,
        ):
            raise ValueError(
                "cannot mark an already quarantined or errored source as errored"
            )

        now = self._clock()
        notes = reason if not source.notes else f"{source.notes}\n{reason}"
        return replace(
            source,
            status=models.KnowledgeSourceStatus.ERROR,
            notes=notes,
            updated_at=now,
        )

    def restore_quarantined_source(
        self,
        *,
        source: models.KnowledgeSource,
        checksum: str | None,
        size_bytes: int,
        notes: str | None = None,
    ) -> models.KnowledgeSource:
        """Restore a quarantined source back to the active state.

        Args:
            source: Source currently in the ``QUARANTINED`` state.
            checksum: Optional checksum recorded during remediation.
            size_bytes: Size of the remediated content on disk.
            notes: Optional replacement notes; when omitted existing notes remain.

        Returns:
            Updated :class:`KnowledgeSource` in the ``ACTIVE`` state.

        Raises:
            ValueError: If the source is not quarantined.
        """

        if source.status is not models.KnowledgeSourceStatus.QUARANTINED:
            raise ValueError("only quarantined sources can be restored to active")

        now = self._clock()
        merged_notes = notes if notes is not None else source.notes
        return replace(
            source,
            status=models.KnowledgeSourceStatus.ACTIVE,
            checksum=checksum if checksum is not None else source.checksum,
            size_bytes=size_bytes,
            last_updated=now,
            updated_at=now,
            notes=merged_notes,
        )

    def mark_ingestion_running(
        self,
        *,
        job: models.IngestionJob,
        stage: str,
    ) -> models.IngestionJob:
        """Mark a queued ingestion job as running.

        Args:
            job: Job currently in the ``QUEUED`` state.
            stage: Descriptive label for the current ingestion stage.

        Returns:
            An updated :class:`IngestionJob` in the ``RUNNING`` state.

        Raises:
            ValueError: If the job is not queued.
        """

        if job.status is not models.IngestionStatus.QUEUED:
            raise ValueError("job must be queued before it can run")

        now = self._clock()
        return replace(
            job,
            status=models.IngestionStatus.RUNNING,
            stage=stage,
            started_at=job.started_at or now,
            percent_complete=0.0,
        )

    def mark_ingestion_succeeded(
        self,
        *,
        job: models.IngestionJob,
        documents_processed: int,
    ) -> models.IngestionJob:
        """Complete a running ingestion job successfully.

        Args:
            job: Job currently in the ``RUNNING`` state.
            documents_processed: Total number of documents processed.

        Returns:
            An updated :class:`IngestionJob` in the ``SUCCEEDED`` state.

        Raises:
            ValueError: If the job is not running or ``documents_processed`` is
            negative.
        """

        if job.status is not models.IngestionStatus.RUNNING:
            raise ValueError("job must be running to complete successfully")

        if documents_processed < 0:
            raise ValueError("documents_processed must be non-negative")

        now = self._clock()
        return replace(
            job,
            status=models.IngestionStatus.SUCCEEDED,
            completed_at=now,
            documents_processed=documents_processed,
            stage="completed",
            percent_complete=100.0,
        )


__all__ = ["SourceService"]
