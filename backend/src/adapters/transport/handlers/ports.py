"""Port adapters exposed through the transport handlers."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Callable

from adapters.storage.catalog import CatalogStorage
from application.query_runner import QueryRunner
from application.source_catalog import SourceCatalogService
from ports import QueryPort, QueryRequest, QueryResponse, SourceCatalog
from ports.ingestion import (
    IngestionJob,
    IngestionStatus,
    IngestionPort,
    IngestionTrigger,
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
        clock: Callable[[], dt.datetime] = _clock,
    ) -> None:
        self._service = service
        self._storage = storage
        self._clock = clock

    def list_sources(self) -> SourceCatalog:
        return self._service.list_sources()

    def create_source(self, request: SourceCreateRequest) -> SourceMutationResult:
        return self._service.create_source(request)

    def update_source(
        self, alias: str, request: SourceUpdateRequest
    ) -> SourceMutationResult:
        return self._service.update_source(alias, request)

    def remove_source(self, alias: str) -> SourceMutationResult:
        return self._service.remove_source(alias)

    def start_reindex(self, trigger: IngestionTrigger) -> IngestionJob:
        catalog = self._storage.load()
        now = self._clock()
        job_id = f"reindex-{uuid.uuid4().hex}"
        LOGGER.info(
            "CatalogIngestionPort.start_reindex(trigger) :: queued",
            job_id=job_id,
            trigger=trigger.value,
            source_count=len(catalog.sources),
        )
        return IngestionJob(
            job_id=job_id,
            source_alias="*",
            status=IngestionStatus.QUEUED,
            requested_at=now,
            started_at=None,
            completed_at=None,
            documents_processed=0,
            stage="preparing_index",
            percent_complete=0.0,
            error_message=None,
            trigger=trigger,
        )


class QueryRunnerPort(QueryPort):
    """Adapter that exposes QueryRunner through the QueryPort protocol."""

    def __init__(self, runner: QueryRunner) -> None:
        self._runner = runner

    def query(self, request: QueryRequest) -> QueryResponse:
        return self._runner.run(
            question=request.question,
            conversation_id=request.conversation_id,
            max_context_tokens=request.max_context_tokens,
            trace_id=request.trace_id,
        )


__all__ = ["CatalogIngestionPort", "QueryRunnerPort"]
