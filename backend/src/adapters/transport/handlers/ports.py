"""Port adapters exposed through the transport handlers."""

import asyncio
import datetime as dt
import functools
import uuid
from typing import Callable

from adapters.storage.catalog import CatalogStorage
from application.query_runner import QueryRunner
from application.reindex_service import ReindexService
from application.source_catalog import SourceCatalogService
from ports import QueryPort, QueryRequest, QueryResponse, SourceCatalog
from ports.ingestion import (
    IngestionJob,
    IngestionStatus,
    IngestionPort,
    IngestionTrigger,
    ReindexCallbacks,
    SourceCreateRequest,
    SourceMutationResult,
    SourceUpdateRequest,
)

from .common import LOGGER, _clock


class CatalogIngestionPort(IngestionPort):
    """Adapter implementing :class:`IngestionPort` via :class:`SourceCatalogService`."""

    def __init__(
        self,
        *,
        service: SourceCatalogService,
        storage: CatalogStorage,
        reindex_service: ReindexService | None = None,
        clock: Callable[[], dt.datetime] = _clock,
    ) -> None:
        """Create an ingestion adapter backed by catalog services.

        Args:
            service: Application service providing catalog mutations.
            storage: Storage helper used for read-only catalog snapshots.
            clock: Callable returning the current UTC timestamp.
        """
        self._service = service
        self._storage = storage
        self._reindex_service = reindex_service
        self._clock = clock

    def list_sources(self) -> SourceCatalog:
        """Return the persisted source catalog snapshot.

        Returns:
            Latest :class:`~ports.ingestion.SourceCatalog` record.
        """
        return self._service.list_sources()

    def create_source(self, request: SourceCreateRequest) -> SourceMutationResult:
        """Register a new source using the application service.

        Args:
            request: Source definition supplied by transport handlers.

        Returns:
            Result describing the newly-created record.
        """
        return self._service.create_source(request)

    def update_source(
        self, alias: str, request: SourceUpdateRequest
    ) -> SourceMutationResult:
        """Apply metadata updates to an existing source.

        Args:
            alias: Existing source alias to mutate.
            request: Partial update payload.

        Returns:
            Updated source mutation result.
        """
        return self._service.update_source(alias, request)

    def remove_source(self, alias: str) -> SourceMutationResult:
        """Remove a source from the catalog.

        Args:
            alias: Source identifier slated for deletion.

        Returns:
            Mutation result reflecting the removal.
        """
        return self._service.remove_source(alias)

    def start_reindex(
        self,
        trigger: IngestionTrigger,
        *,
        force_rebuild: bool = False,
        callbacks: ReindexCallbacks | None = None,
    ) -> IngestionJob:
        """Record a reindex request and schedule orchestration.

        Args:
            trigger: Event that initiated the reindex request.

        Returns:
            Ingestion job snapshot representing the running work.
        """
        catalog = self._storage.load()
        now = self._clock()
        job_id = f"reindex-{uuid.uuid4().hex}"
        LOGGER.info(
            "CatalogIngestionPort.start_reindex(trigger) :: scheduled",
            job_id=job_id,
            trigger=trigger.value,
            source_count=len(catalog.sources),
        )
        job = IngestionJob(
            job_id=job_id,
            source_alias="*",
            status=IngestionStatus.RUNNING,
            requested_at=now,
            started_at=now,
            completed_at=None,
            documents_processed=0,
            stage="preparing_index",
            percent_complete=0.0,
            error_message=None,
            trigger=trigger,
        )
        if callbacks and callbacks.on_progress:
            callbacks.on_progress(job)

        if self._reindex_service is None:
            return job

        loop = self._get_running_loop()
        if loop is None:
            return job

        loop.run_in_executor(
            None,
            functools.partial(
                self._reindex_service.run,
                trigger,
                job_id=job.job_id,
                force_rebuild=force_rebuild,
                callbacks=callbacks,
            ),
        )
        return job

    def _get_running_loop(self) -> asyncio.AbstractEventLoop | None:
        """Return the running event loop when available."""

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return None
        if not loop.is_running():
            return None
        return loop


class QueryRunnerPort(QueryPort):
    """Adapter that exposes QueryRunner through the QueryPort protocol."""

    def __init__(self, runner: QueryRunner) -> None:
        """Create a thin wrapper around :class:`QueryRunner`.

        Args:
            runner: Application-level query coordinator to delegate to.
        """
        self._runner = runner

    def query(self, request: QueryRequest) -> QueryResponse:
        """Execute a query by forwarding it to :class:`QueryRunner`.

        Args:
            request: Structured query request from the transport layer.

        Returns:
            Structured response emitted by :class:`QueryRunner`.
        """
        return self._runner.run(
            question=request.question,
            conversation_id=request.conversation_id,
            max_context_tokens=request.max_context_tokens,
            trace_id=request.trace_id,
        )


__all__ = ["CatalogIngestionPort", "QueryRunnerPort"]
