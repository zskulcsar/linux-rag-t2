"""Domain service contract tests for state transitions."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
import uuid

import pytest

from domain import health_service, models, query_service, source_service
from ports.health import HealthCheck, HealthComponent, HealthStatus


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


def test_health_service_registers_checks_and_aggregates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure HealthService uses the default clock and aggregates WARN status."""

    generated_at = _utc(dt.datetime(2025, 1, 5, 12, 0, 0))
    monkeypatch.setattr(
        health_service, "_default_clock", lambda: generated_at, raising=False
    )

    def make_check(status: HealthStatus, component: HealthComponent):
        def factory() -> HealthCheck:
            return HealthCheck(
                component=component,
                status=status,
                message=f"{component.value}:{status.value}",
            )

        return factory

    service = health_service.HealthService(
        check_factories=[make_check(HealthStatus.PASS, HealthComponent.DISK_CAPACITY)]
    )
    service.register(make_check(HealthStatus.WARN, HealthComponent.OLLAMA))

    report = service.evaluate()

    assert report.generated_at == generated_at
    assert report.status is HealthStatus.WARN
    assert {check.component for check in report.checks} == {
        HealthComponent.DISK_CAPACITY,
        HealthComponent.OLLAMA,
    }


def test_health_service_reports_fail_when_any_check_fails() -> None:
    """Ensure aggregate status escalates to FAIL whenever one check fails."""

    def failing_factory():
        return HealthCheck(
            component=HealthComponent.WEAVIATE,
            status=HealthStatus.FAIL,
            message="Weaviate unreachable",
        )

    service = health_service.HealthService(check_factories=[failing_factory])
    report = service.evaluate()
    assert report.status is HealthStatus.FAIL


def test_health_service_pass_status_when_all_checks_succeed() -> None:
    """Ensure aggregate status returns PASS when every check succeeds."""

    def healthy_factory():
        return HealthCheck(
            component=HealthComponent.DISK_CAPACITY,
            status=HealthStatus.PASS,
            message="All good",
        )

    report = health_service.HealthService(check_factories=[healthy_factory]).evaluate()
    assert report.status is HealthStatus.PASS


def test_mark_source_validated_rejects_non_pending_source() -> None:
    """Ensure only pending sources can be validated."""

    source = models.KnowledgeSource(
        alias="docs",
        type=models.SourceType.MAN,
        location="/docs",
        language="en",
        size_bytes=0,
        last_updated=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
        status=models.KnowledgeSourceStatus.ACTIVE,
        checksum=None,
        notes=None,
        created_at=_utc(dt.datetime(2024, 12, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
    )

    with pytest.raises(ValueError):
        source_service.SourceService().mark_source_validated(
            source=source, checksum="abc", size_bytes=10
        )


def test_mark_source_quarantined_rejects_pending_source() -> None:
    """Ensure quarantine only applies to active or errored sources."""

    pending = models.KnowledgeSource(
        alias="docs",
        type=models.SourceType.MAN,
        location="/docs",
        language="en",
        size_bytes=0,
        last_updated=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
        status=models.KnowledgeSourceStatus.PENDING_VALIDATION,
        checksum=None,
        notes=None,
        created_at=_utc(dt.datetime(2024, 12, 1, 0, 0, 0)),
        updated_at=_utc(dt.datetime(2025, 1, 1, 0, 0, 0)),
    )

    with pytest.raises(ValueError):
        source_service.SourceService().mark_source_quarantined(
            source=pending, reason="still validating"
        )


def test_mark_ingestion_running_requires_queued_job() -> None:
    """Ensure jobs must be queued before running."""

    running_job = models.IngestionJob(
        job_id=str(uuid.uuid4()),
        source_alias="docs",
        status=models.IngestionStatus.RUNNING,
        requested_at=_utc(dt.datetime(2025, 1, 3, 8, 0, 0)),
        started_at=_utc(dt.datetime(2025, 1, 3, 8, 5, 0)),
        completed_at=None,
        documents_processed=10,
        stage="vectorizing",
        percent_complete=50.0,
        error_message=None,
        trigger=models.IngestionTrigger.MANUAL,
    )

    with pytest.raises(ValueError):
        source_service.SourceService().mark_ingestion_running(
            job=running_job, stage="vectorizing"
        )


def test_mark_ingestion_succeeded_rejects_negative_documents() -> None:
    """Ensure negative document counts raise a ValueError."""

    running_job = models.IngestionJob(
        job_id=str(uuid.uuid4()),
        source_alias="docs",
        status=models.IngestionStatus.RUNNING,
        requested_at=_utc(dt.datetime(2025, 1, 3, 8, 0, 0)),
        started_at=_utc(dt.datetime(2025, 1, 3, 8, 5, 0)),
        completed_at=None,
        documents_processed=0,
        stage="vectorizing",
        percent_complete=50.0,
        error_message=None,
        trigger=models.IngestionTrigger.MANUAL,
    )

    with pytest.raises(ValueError):
        source_service.SourceService().mark_ingestion_succeeded(
            job=running_job, documents_processed=-1
        )


def test_query_service_default_clock_and_non_ready_freshness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure default clock path executes and non-ready indexes are returned untouched."""

    sentinel = _utc(dt.datetime(2025, 1, 6, 12, 0, 0))
    monkeypatch.setattr(query_service, "_default_clock", lambda: sentinel, raising=False)
    service = query_service.QueryService()

    version = models.ContentIndexVersion(
        index_id=str(uuid.uuid4()),
        status=models.IndexStatus.BUILDING,
        built_at=None,
        checksum="build-123",
        source_snapshot=[],
        size_bytes=0,
        document_count=0,
        freshness_expires_at=sentinel + dt.timedelta(days=1),
        trigger_job_id=str(uuid.uuid4()),
    )
    ready = service.mark_index_ready(version=version, document_count=1, size_bytes=1)
    assert ready.built_at == sentinel

    non_ready_version = replace(ready, status=models.IndexStatus.BUILDING)
    assert service.enforce_index_freshness(version=non_ready_version) is non_ready_version

    ready_without_expiry = replace(ready, freshness_expires_at=None)
    assert service.enforce_index_freshness(
        version=ready_without_expiry
    ) is ready_without_expiry

    still_fresh = service.enforce_index_freshness(
        version=ready, reference_time=sentinel + dt.timedelta(days=1)
    )
    assert still_fresh is ready


def test_query_service_rejects_mark_ready_for_non_building_version() -> None:
    """Ensure mark_index_ready raises the documented ValueError."""

    version = models.ContentIndexVersion(
        index_id=str(uuid.uuid4()),
        status=models.IndexStatus.READY,
        built_at=_utc(dt.datetime(2025, 1, 4, 12, 0, 0)),
        checksum="existing",
        source_snapshot=[],
        size_bytes=0,
        document_count=0,
        freshness_expires_at=None,
        trigger_job_id=str(uuid.uuid4()),
    )

    service = query_service.QueryService()
    with pytest.raises(ValueError):
        service.mark_index_ready(version=version, document_count=10, size_bytes=10)


def test_query_service_default_clock_returns_timezone_aware_timestamp() -> None:
    """Ensure the default clock helper yields a timezone-aware timestamp."""

    assert query_service._default_clock().tzinfo is not None


def test_source_service_default_clock_returns_timezone_aware_timestamp() -> None:
    """Ensure the source service default clock provides UTC timestamps."""

    assert source_service._default_clock().tzinfo is not None
