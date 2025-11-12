"""Domain service contract tests for state transitions."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from domain import models, query_service, source_service


def _utc(ts: dt.datetime) -> dt.datetime:
    """Ensure timestamps are timezone-aware UTC values."""

    return ts.replace(tzinfo=dt.timezone.utc)


def test_mark_source_validated_promotes_pending_source() -> None:
    """Ensure pending sources transition to active with checksum and size updates."""

    now = _utc(dt.datetime(2025, 1, 1, 12, 0, 0))
    source = models.KnowledgeSource(
        alias="man-pages",
        type=models.SourceType.MAN,
        location="/usr/share/man",
        language="en",
        size_bytes=0,
        last_updated=_utc(dt.datetime(2024, 12, 1, 0, 0, 0)),
        status=models.KnowledgeSourceStatus.PENDING_VALIDATION,
        checksum=None,
        notes=None,
        created_at=_utc(dt.datetime(2024, 11, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2024, 12, 1, 0, 0, 0)),
    )

    service = source_service.SourceService(clock=lambda: now)
    activated = service.mark_source_validated(
        source=source,
        checksum="abc123",
        size_bytes=4096,
    )

    assert activated.status is models.KnowledgeSourceStatus.ACTIVE
    assert activated.checksum == "abc123"
    assert activated.size_bytes == 4096
    assert activated.updated_at == now
    assert activated.last_updated == now


def test_mark_source_quarantined_records_reason_and_timestamp() -> None:
    """Ensure active sources move to quarantined with remediation notes and timestamps."""

    base_time = _utc(dt.datetime(2025, 1, 2, 9, 30, 0))
    active_source = models.KnowledgeSource(
        alias="info-pages",
        type=models.SourceType.INFO,
        location="/usr/share/info",
        language="en",
        size_bytes=2048,
        last_updated=base_time,
        status=models.KnowledgeSourceStatus.ACTIVE,
        checksum="xyz789",
        notes=None,
        created_at=_utc(dt.datetime(2024, 10, 1, 0, 0, 0)),
        updated_at=base_time,
    )

    later = base_time + dt.timedelta(minutes=5)
    reason = "Path missing during validation"
    quarantine = source_service.SourceService(
        clock=lambda: later
    ).mark_source_quarantined(source=active_source, reason=reason)

    assert quarantine.status is models.KnowledgeSourceStatus.QUARANTINED
    assert reason in (quarantine.notes or "")
    assert quarantine.updated_at == later


def test_mark_source_error_appends_reason_and_timestamp() -> None:
    """Ensure sources move to error with appended remediation notes."""

    base_time = _utc(dt.datetime(2025, 1, 2, 10, 0, 0))
    active_source = models.KnowledgeSource(
        alias="info-pages",
        type=models.SourceType.INFO,
        location="/usr/share/info",
        language="en",
        size_bytes=2048,
        last_updated=_utc(dt.datetime(2025, 1, 1, 9, 0, 0)),
        status=models.KnowledgeSourceStatus.ACTIVE,
        checksum="xyz789",
        notes="Initial import succeeded",
        created_at=_utc(dt.datetime(2024, 10, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2025, 1, 1, 9, 0, 0)),
    )

    later = base_time + dt.timedelta(minutes=10)
    reason = "Ingestion failed due to missing chunks"
    errored = source_service.SourceService(clock=lambda: later).mark_source_error(
        source=active_source,
        reason=reason,
    )

    assert errored.status is models.KnowledgeSourceStatus.ERROR
    assert reason in (errored.notes or "")
    assert errored.updated_at == later
    assert errored.last_updated == active_source.last_updated

    with pytest.raises(ValueError):
        source_service.SourceService(clock=lambda: later).mark_source_error(
            source=errored, reason="second failure"
        )


def test_restore_quarantined_source_promotes_to_active() -> None:
    """Ensure quarantined sources return to active with updated metadata."""

    base_time = _utc(dt.datetime(2025, 1, 3, 8, 0, 0))
    quarantined = models.KnowledgeSource(
        alias="info-pages",
        type=models.SourceType.INFO,
        location="/usr/share/info",
        language="en",
        size_bytes=1024,
        last_updated=_utc(dt.datetime(2024, 12, 25, 0, 0, 0)),
        status=models.KnowledgeSourceStatus.QUARANTINED,
        checksum="old",
        notes="Corruption detected",
        created_at=_utc(dt.datetime(2024, 10, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2025, 1, 2, 9, 0, 0)),
    )

    restored = source_service.SourceService(
        clock=lambda: base_time
    ).restore_quarantined_source(
        source=quarantined,
        checksum="new",
        size_bytes=2048,
        notes="Remediated and revalidated",
    )

    assert restored.status is models.KnowledgeSourceStatus.ACTIVE
    assert restored.checksum == "new"
    assert restored.size_bytes == 2048
    assert restored.notes == "Remediated and revalidated"
    assert restored.last_updated == base_time
    assert restored.updated_at == base_time

    active_source = models.KnowledgeSource(
        alias="man-pages",
        type=models.SourceType.MAN,
        location="/usr/share/man",
        language="en",
        size_bytes=1024,
        last_updated=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
        status=models.KnowledgeSourceStatus.ACTIVE,
        checksum="abc",
        notes=None,
        created_at=_utc(dt.datetime(2024, 10, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
    )

    with pytest.raises(ValueError):
        source_service.SourceService(
            clock=lambda: base_time
        ).restore_quarantined_source(
            source=active_source,
            checksum="abc",
            size_bytes=1024,
        )


def test_ingestion_state_machine_enforces_valid_transitions() -> None:
    """Ensure ingestion jobs progress queued→running→succeeded and reject invalid jumps."""

    requested_at = _utc(dt.datetime(2025, 1, 3, 8, 0, 0))
    job = models.IngestionJob(
        job_id=str(uuid.uuid4()),
        source_alias="man-pages",
        status=models.IngestionStatus.QUEUED,
        requested_at=requested_at,
        started_at=None,
        completed_at=None,
        documents_processed=0,
        stage=None,
        percent_complete=None,
        error_message=None,
        trigger=models.IngestionTrigger.MANUAL,
    )

    running = source_service.SourceService(
        clock=lambda: requested_at
    ).mark_ingestion_running(job=job, stage="vectorizing")
    assert running.status is models.IngestionStatus.RUNNING
    assert running.stage == "vectorizing"
    assert running.started_at == requested_at

    completed_at = requested_at + dt.timedelta(minutes=15)
    succeeded = source_service.SourceService(
        clock=lambda: completed_at
    ).mark_ingestion_succeeded(job=running, documents_processed=128)
    assert succeeded.status is models.IngestionStatus.SUCCEEDED
    assert succeeded.completed_at == completed_at
    assert succeeded.documents_processed == 128

    with pytest.raises(ValueError):
        source_service.SourceService(
            clock=lambda: completed_at
        ).mark_ingestion_succeeded(job=job, documents_processed=1)


def test_index_service_marks_ready_and_detects_staleness() -> None:
    """Ensure index versions mark ready with counts and later degrade to stale when expired."""

    snapshot = [
        models.SourceSnapshot(alias="man-pages", checksum="abc123"),
        models.SourceSnapshot(alias="info-pages", checksum="def456"),
    ]
    building = models.ContentIndexVersion(
        index_id=str(uuid.uuid4()),
        status=models.IndexStatus.BUILDING,
        built_at=None,
        checksum="build-001",
        source_snapshot=snapshot,
        size_bytes=0,
        document_count=0,
        freshness_expires_at=_utc(dt.datetime(2025, 1, 10, 0, 0, 0)),
        trigger_job_id=str(uuid.uuid4()),
    )

    ready_time = _utc(dt.datetime(2025, 1, 4, 12, 0, 0))
    service = query_service.QueryService(clock=lambda: ready_time)

    ready = service.mark_index_ready(
        version=building,
        document_count=256,
        size_bytes=1_024_000,
    )
    assert ready.status is models.IndexStatus.READY
    assert ready.built_at == ready_time
    assert ready.document_count == 256
    assert ready.size_bytes == 1_024_000
    assert isinstance(ready.freshness_expires_at, dt.datetime)
    assert ready.freshness_expires_at >= ready_time

    future = ready_time + dt.timedelta(days=8)
    stale = service.enforce_index_freshness(version=ready, reference_time=future)
    assert stale.status is models.IndexStatus.STALE

    with pytest.raises(ValueError):
        service.mark_index_ready(version=ready, document_count=1, size_bytes=1)
