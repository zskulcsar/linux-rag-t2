"""Integration tests for ingestion recovery planning."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import replace

import pytest

from domain import models
from domain.job_recovery import (
    Checkpoint,
    JobRecoveryService,
    ResumePlan,
)


def _utc(ts: dt.datetime) -> dt.datetime:
    return ts.replace(tzinfo=dt.timezone.utc)


def _job(
    status: models.IngestionStatus, *, started_at: dt.datetime | None
) -> models.IngestionJob:
    return models.IngestionJob(
        job_id=str(uuid.uuid4()),
        source_alias="man-pages",
        status=status,
        requested_at=_utc(dt.datetime(2025, 1, 2, 9, 0, 0)),
        started_at=started_at,
        completed_at=None,
        documents_processed=0,
        stage="vectorizing" if status is models.IngestionStatus.RUNNING else None,
        percent_complete=None,
        error_message=None,
        trigger=models.IngestionTrigger.MANUAL,
    )


def test_job_recovery_plans_remaining_chunks_after_mid_run_failure() -> None:
    """Ensure recovery computes remaining chunk IDs and updated progress."""

    started_at = _utc(dt.datetime(2025, 1, 2, 9, 5, 0))
    job = _job(models.IngestionStatus.RUNNING, started_at=started_at)
    clock_time = _utc(dt.datetime(2025, 1, 2, 9, 15, 0))
    service = JobRecoveryService(clock=lambda: clock_time)

    processed = {"man-pages:abc123:0", "man-pages:abc123:1"}
    document_ids = tuple(f"man-pages:abc123:{index}" for index in range(4))
    checkpoint = service.record_progress(
        job=job, processed_document_ids=processed, document_ids=document_ids
    )

    assert isinstance(checkpoint, Checkpoint)
    assert checkpoint.processed_document_ids == (
        "man-pages:abc123:0",
        "man-pages:abc123:1",
    )
    assert checkpoint.percent_complete == 50.0

    plan = service.plan_resume(
        job=job, checkpoint=checkpoint, document_ids=document_ids
    )

    assert isinstance(plan, ResumePlan)
    assert plan.resume_stage == "resuming_vectorizing"
    assert plan.remaining_document_ids == ("man-pages:abc123:2", "man-pages:abc123:3")
    assert plan.percent_complete == 50.0
    assert plan.recovery_started_at == clock_time


def test_job_recovery_requires_checkpoint_for_resume() -> None:
    """Ensure service guards against resume attempts without checkpoint state."""

    job = _job(
        models.IngestionStatus.RUNNING,
        started_at=_utc(dt.datetime(2025, 1, 2, 9, 5, 0)),
    )
    service = JobRecoveryService(clock=lambda: _utc(dt.datetime(2025, 1, 2, 9, 15, 0)))

    with pytest.raises(ValueError):
        service.plan_resume(
            job=job,
            checkpoint=None,  # type: ignore[arg-type]
            document_ids=tuple(f"man-pages:abc123:{index}" for index in range(4)),
        )


def test_resume_updates_job_and_returns_remaining_docs() -> None:
    """Ensure resume updates job state and retains outstanding document IDs."""

    clock_time = _utc(dt.datetime(2025, 1, 2, 9, 20, 0))
    running_job = _job(
        models.IngestionStatus.RUNNING,
        started_at=_utc(dt.datetime(2025, 1, 2, 9, 5, 0)),
    )
    service = JobRecoveryService(clock=lambda: clock_time)

    processed_ids = {"man-pages:abc123:0", "man-pages:abc123:1"}
    document_ids = tuple(f"man-pages:abc123:{index}" for index in range(4))
    checkpoint = service.record_progress(
        job=running_job, processed_document_ids=processed_ids, document_ids=document_ids
    )

    failed_job = replace(
        running_job, status=models.IngestionStatus.FAILED, stage="vectorizing"
    )

    resumed_job, plan = service.resume(
        job=failed_job, document_ids=document_ids, checkpoint=checkpoint
    )

    assert resumed_job.status is models.IngestionStatus.RUNNING
    assert resumed_job.stage == "resuming_vectorizing"
    assert resumed_job.started_at == failed_job.started_at
    assert resumed_job.percent_complete == checkpoint.percent_complete
    assert resumed_job.documents_processed == len(processed_ids)
    assert plan.remaining_document_ids == ("man-pages:abc123:2", "man-pages:abc123:3")


def test_resume_marks_job_complete_when_no_remaining_docs() -> None:
    """Ensure resume promotes job to success when nothing remains to process."""

    clock_time = _utc(dt.datetime(2025, 1, 2, 9, 30, 0))
    job = _job(
        models.IngestionStatus.FAILED, started_at=_utc(dt.datetime(2025, 1, 2, 9, 5, 0))
    )
    service = JobRecoveryService(clock=lambda: clock_time)

    document_ids = ("man-pages:abc123:0",)
    checkpoint = Checkpoint(
        processed_document_ids=document_ids,
        percent_complete=100.0,
        captured_at=clock_time,
    )

    resumed_job, plan = service.resume(
        job=job, document_ids=document_ids, checkpoint=checkpoint
    )

    assert resumed_job.status is models.IngestionStatus.SUCCEEDED
    assert resumed_job.completed_at is not None
    assert resumed_job.stage == "completed"
    assert resumed_job.percent_complete == 100.0
    assert plan.remaining_document_ids == ()


def test_resume_without_checkpoint_restarts_ingestion() -> None:
    """Ensure resume can restart ingestion when no checkpoint is available."""

    clock_time = _utc(dt.datetime(2025, 1, 2, 9, 40, 0))
    job = _job(models.IngestionStatus.FAILED, started_at=None)
    service = JobRecoveryService(clock=lambda: clock_time)

    document_ids = tuple(f"man-pages:abc123:{index}" for index in range(3))
    resumed_job, plan = service.resume(
        job=job, document_ids=document_ids, checkpoint=None
    )

    assert resumed_job.status is models.IngestionStatus.RUNNING
    assert resumed_job.started_at == clock_time
    assert resumed_job.percent_complete == 0.0
    assert plan.remaining_document_ids == document_ids
