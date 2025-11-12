"""Ingestion recovery helpers for resuming interrupted jobs."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Sequence

from services.rag_backend.domain import models
from services.rag_backend.telemetry import trace_call, trace_section


def _default_clock() -> dt.datetime:
    """Return the current UTC timestamp.

    Returns:
        A timezone-aware datetime representing now in UTC.
    """

    return dt.datetime.now(dt.timezone.utc)


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """Captured ingestion progress.

    Attributes:
        processed_document_ids: Ordered identifiers already processed.
        percent_complete: Completion percentage based on processed IDs.
        captured_at: Timestamp of the checkpoint capture.

    Example:
        >>> Checkpoint(processed_document_ids=('a:1',), percent_complete=25.0, captured_at=dt.datetime.now(dt.timezone.utc))
    """

    processed_document_ids: tuple[str, ...]
    percent_complete: float
    captured_at: dt.datetime


@dataclass(frozen=True, slots=True)
class ResumePlan:
    """Plan describing how to resume ingestion after failure.

    Attributes:
        remaining_document_ids: Identifiers still awaiting ingestion.
        percent_complete: Completion percentage carried from checkpoint.
        resume_stage: Label describing the resumed stage.
        recovery_started_at: Timestamp when recovery planning began.

    Example:
        >>> ResumePlan(remaining_document_ids=('a:2',), percent_complete=50.0, resume_stage='resuming_vectorizing', recovery_started_at=dt.datetime.now(dt.timezone.utc))
    """

    remaining_document_ids: tuple[str, ...]
    percent_complete: float
    resume_stage: str
    recovery_started_at: dt.datetime


class JobRecoveryService:
    """Service building recovery checkpoints and resume plans.

    Example:
        >>> service = JobRecoveryService()
        >>> checkpoint = service.record_progress(job=job, processed_document_ids={'id-1'}, document_ids=['id-1', 'id-2'])
    """

    @trace_call
    def __init__(self, *, clock: Callable[[], dt.datetime] | None = None) -> None:
        """Create the recovery service.

        Args:
            clock: Optional callable returning the current UTC time.
        """

        self._clock = clock or _default_clock

    @trace_call
    def record_progress(
        self,
        *,
        job: models.IngestionJob,
        processed_document_ids: Iterable[str],
        document_ids: Sequence[str],
    ) -> Checkpoint:
        """Capture current ingestion progress for later resumption.

        Args:
            job: Job currently undergoing ingestion.
            processed_document_ids: Identifiers already processed.
            document_ids: Ordered identifiers representing the workload.

        Returns:
            A :class:`Checkpoint` describing current progress.

        Raises:
            ValueError: If the job is not in the running state.

        Example:
            >>> service.record_progress(job=job, processed_document_ids={'id-1'}, document_ids=['id-1', 'id-2'])
        """

        metadata = {
            "job_id": job.job_id,
            "status": job.status.value,
            "processed_count": len(set(processed_document_ids)),
            "total_count": len(document_ids),
        }
        with trace_section(
            "job_recovery.record_progress", metadata=metadata
        ) as section:
            if job.status is not models.IngestionStatus.RUNNING:
                raise ValueError("only running jobs can be checkpointed")

            ordered_processed: list[str] = []
            processed_set = set(processed_document_ids)
            for identifier in document_ids:
                if identifier in processed_set:
                    ordered_processed.append(identifier)
                    section.debug("processed_detected", document_id=identifier)

            if not document_ids:
                return Checkpoint(
                    processed_document_ids=tuple(),
                    percent_complete=0.0,
                    captured_at=self._clock(),
                )

            percent_complete = (len(ordered_processed) / len(document_ids)) * 100.0
            section.debug("percent_complete", value=percent_complete)
            return Checkpoint(
                processed_document_ids=tuple(ordered_processed),
                percent_complete=percent_complete,
                captured_at=self._clock(),
            )

    @trace_call
    def plan_resume(
        self,
        *,
        job: models.IngestionJob,
        checkpoint: Checkpoint | None,
        document_ids: Sequence[str],
    ) -> ResumePlan:
        """Build a plan for resuming ingestion given a checkpoint.

        Args:
            job: Job being resumed.
            checkpoint: Prior progress checkpoint.
            document_ids: Ordered document identifiers to process.

        Returns:
            :class:`ResumePlan` describing work that remains.

        Raises:
            ValueError: If the job status does not permit resumption or the checkpoint is missing.

        Example:
            >>> service.plan_resume(job=job, checkpoint=checkpoint, document_ids=['id-1', 'id-2'])
        """

        metadata = {
            "job_id": job.job_id,
            "status": job.status.value,
            "has_checkpoint": checkpoint is not None,
            "total_count": len(document_ids),
        }
        with trace_section("job_recovery.plan_resume", metadata=metadata) as section:
            if checkpoint is None:
                raise ValueError("checkpoint state is required to resume ingestion")

            if job.status not in (
                models.IngestionStatus.RUNNING,
                models.IngestionStatus.FAILED,
            ):
                raise ValueError("only running or failed jobs can be resumed")

            processed_set = set(checkpoint.processed_document_ids)
            remaining = tuple(
                identifier
                for identifier in document_ids
                if identifier not in processed_set
            )
            section.debug("remaining_identified", remaining=remaining)

            resume_stage = "resuming_ingestion"
            if job.stage:
                resume_stage = f"resuming_{job.stage}"

            plan = ResumePlan(
                remaining_document_ids=remaining,
                percent_complete=checkpoint.percent_complete,
                resume_stage=resume_stage,
                recovery_started_at=self._clock(),
            )
            section.debug(
                "plan_created",
                resume_stage=resume_stage,
                remaining_count=len(remaining),
            )
            return plan

    @trace_call
    def resume(
        self,
        *,
        job: models.IngestionJob,
        document_ids: Sequence[str],
        checkpoint: Checkpoint | None,
    ) -> tuple[models.IngestionJob, ResumePlan]:
        """Prepare a job to resume ingestion after an interruption.

        Args:
            job: Original ingestion job requiring recovery.
            document_ids: Ordered identifiers for the full ingestion workload.
            checkpoint: Previously recorded checkpoint, if available.

        Returns:
            Updated :class:`IngestionJob` ready to resume and the computed
            :class:`ResumePlan` describing the outstanding work.

        Raises:
            ValueError: If ``document_ids`` is empty or the job status cannot be
            resumed from the provided state.
        """

        if not document_ids:
            raise ValueError("document_ids must contain at least one entry")

        plan = (
            self.plan_resume(job=job, checkpoint=checkpoint, document_ids=document_ids)
            if checkpoint is not None
            else ResumePlan(
                remaining_document_ids=tuple(document_ids),
                percent_complete=0.0,
                resume_stage=f"resuming_{job.stage or 'ingestion'}",
                recovery_started_at=self._clock(),
            )
        )

        remaining = plan.remaining_document_ids
        if not remaining:
            completed_job = replace(
                job,
                status=models.IngestionStatus.SUCCEEDED,
                completed_at=self._clock(),
                documents_processed=len(document_ids),
                stage="completed",
                percent_complete=100.0,
                error_message=None,
            )
            return completed_job, plan

        resume_started_at = job.started_at or plan.recovery_started_at
        updated_job = replace(
            job,
            status=models.IngestionStatus.RUNNING,
            stage=plan.resume_stage,
            started_at=resume_started_at,
            completed_at=None,
            percent_complete=plan.percent_complete,
            error_message=None,
        )

        if checkpoint:
            updated_job = replace(
                updated_job,
                documents_processed=len(checkpoint.processed_document_ids),
            )

        return updated_job, plan


__all__ = ["Checkpoint", "JobRecoveryService", "ResumePlan"]
