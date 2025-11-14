"""Unit tests for JobRecoveryService checkpoint and resume helpers."""


import datetime as dt
import uuid

import pytest

from domain import job_recovery, models


def _utc(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.timezone.utc)


def _job(
    *,
    status: models.IngestionStatus,
    stage: str | None = None,
) -> models.IngestionJob:
    return models.IngestionJob(
        job_id=str(uuid.uuid4()),
        source_alias="man-pages",
        status=status,
        requested_at=_utc(2025, 1, 2, 9, 0, 0),
        started_at=_utc(2025, 1, 2, 9, 1, 0) if stage else None,
        completed_at=None,
        documents_processed=0,
        stage=stage,
        percent_complete=None,
        error_message=None,
        trigger=models.IngestionTrigger.MANUAL,
    )


def test_record_progress_orders_processed_documents_and_percent() -> None:
    job = _job(status=models.IngestionStatus.RUNNING, stage="vectorizing")
    document_ids = tuple(f"doc-{index}" for index in range(4))
    processed = {"doc-3", "doc-1"}

    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 5))
    checkpoint = service.record_progress(
        job=job, processed_document_ids=processed, document_ids=document_ids
    )

    assert checkpoint.processed_document_ids == ("doc-1", "doc-3")
    assert checkpoint.percent_complete == 50.0


def test_record_progress_requires_running_job() -> None:
    job = _job(status=models.IngestionStatus.QUEUED)
    service = job_recovery.JobRecoveryService()
    with pytest.raises(ValueError):
        service.record_progress(
            job=job, processed_document_ids=set(), document_ids=("doc-1",)
        )


def test_record_progress_handles_empty_documents() -> None:
    job = _job(status=models.IngestionStatus.RUNNING)
    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 10))
    checkpoint = service.record_progress(
        job=job, processed_document_ids=set(), document_ids=()
    )
    assert checkpoint.processed_document_ids == ()
    assert checkpoint.percent_complete == 0.0


def test_plan_resume_requires_checkpoint_and_valid_status() -> None:
    job = _job(status=models.IngestionStatus.RUNNING)
    service = job_recovery.JobRecoveryService()
    with pytest.raises(ValueError):
        service.plan_resume(job=job, checkpoint=None, document_ids=("doc-1",))

    cancelled_job = _job(status=models.IngestionStatus.CANCELLED)
    checkpoint = job_recovery.Checkpoint(
        processed_document_ids=(),
        percent_complete=0.0,
        captured_at=_utc(2025, 1, 2, 9, 0),
    )
    with pytest.raises(ValueError):
        service.plan_resume(
            job=cancelled_job, checkpoint=checkpoint, document_ids=("doc-1",)
        )


def test_plan_resume_builds_remaining_document_plan() -> None:
    checkpoint = job_recovery.Checkpoint(
        processed_document_ids=("doc-1", "doc-2"),
        percent_complete=50.0,
        captured_at=_utc(2025, 1, 2, 9, 15),
    )
    job = _job(status=models.IngestionStatus.FAILED, stage="vectorizing")
    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 20))

    plan = service.plan_resume(
        job=job,
        checkpoint=checkpoint,
        document_ids=("doc-1", "doc-2", "doc-3"),
    )

    assert plan.remaining_document_ids == ("doc-3",)
    assert plan.resume_stage == "resuming_vectorizing"
    assert plan.percent_complete == 50.0


def test_resume_requires_document_ids() -> None:
    job = _job(status=models.IngestionStatus.RUNNING)
    service = job_recovery.JobRecoveryService()
    with pytest.raises(ValueError):
        service.resume(job=job, document_ids=(), checkpoint=None)


def test_resume_without_checkpoint_starts_over() -> None:
    job = _job(status=models.IngestionStatus.RUNNING, stage="vectorizing")
    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 25))
    updated, plan = service.resume(
        job=job,
        document_ids=("doc-1", "doc-2"),
        checkpoint=None,
    )

    assert updated.stage == "resuming_vectorizing"
    assert plan.remaining_document_ids == ("doc-1", "doc-2")
    assert plan.percent_complete == 0.0


def test_resume_marks_job_succeeded_when_no_remaining() -> None:
    checkpoint = job_recovery.Checkpoint(
        processed_document_ids=("doc-1",),
        percent_complete=100.0,
        captured_at=_utc(2025, 1, 2, 9, 30),
    )
    job = _job(status=models.IngestionStatus.RUNNING, stage="vectorizing")
    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 35))

    updated, plan = service.resume(
        job=job,
        document_ids=("doc-1",),
        checkpoint=checkpoint,
    )

    assert updated.status is models.IngestionStatus.SUCCEEDED
    assert updated.percent_complete == 100.0
    assert plan.remaining_document_ids == ()


def test_resume_with_checkpoint_updates_documents_processed() -> None:
    checkpoint = job_recovery.Checkpoint(
        processed_document_ids=("doc-1",),
        percent_complete=50.0,
        captured_at=_utc(2025, 1, 2, 9, 40),
    )
    job = _job(status=models.IngestionStatus.RUNNING, stage="vectorizing")
    service = job_recovery.JobRecoveryService(clock=lambda: _utc(2025, 1, 2, 9, 45))

    updated, plan = service.resume(
        job=job,
        document_ids=("doc-1", "doc-2"),
        checkpoint=checkpoint,
    )

    assert updated.documents_processed == 1
    assert plan.remaining_document_ids == ("doc-2",)


def test_default_clock_returns_timezone_aware_timestamp() -> None:
    assert job_recovery._default_clock().tzinfo is not None
