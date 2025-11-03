"""Integration tests for ingestion recovery planning."""

from __future__ import annotations

import datetime as dt
import uuid

import pytest

from services.rag_backend.domain import models
from services.rag_backend.domain.job_recovery import (
    Checkpoint,
    JobRecoveryService,
    ResumePlan,
)


def _utc(ts: dt.datetime) -> dt.datetime:
    return ts.replace(tzinfo=dt.timezone.utc)


def _job(status: models.IngestionStatus, *, started_at: dt.datetime | None) -> models.IngestionJob:
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

    plan = service.plan_resume(job=job, checkpoint=checkpoint, document_ids=document_ids)

    assert isinstance(plan, ResumePlan)
    assert plan.resume_stage == "resuming_vectorizing"
    assert plan.remaining_document_ids == ("man-pages:abc123:2", "man-pages:abc123:3")
    assert plan.percent_complete == 50.0
    assert plan.recovery_started_at == clock_time


def test_job_recovery_requires_checkpoint_for_resume() -> None:
    """Ensure service guards against resume attempts without checkpoint state."""

    job = _job(models.IngestionStatus.RUNNING, started_at=_utc(dt.datetime(2025, 1, 2, 9, 5, 0)))
    service = JobRecoveryService(clock=lambda: _utc(dt.datetime(2025, 1, 2, 9, 15, 0)))

    with pytest.raises(ValueError):
        service.plan_resume(
            job=job,
            checkpoint=None,  # type: ignore[arg-type]
            document_ids=tuple(f"man-pages:abc123:{index}" for index in range(4)),
        )
