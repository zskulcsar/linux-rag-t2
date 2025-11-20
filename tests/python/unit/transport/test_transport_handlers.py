"""Unit tests for TransportHandlers shutdown semantics."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

from adapters.transport.handlers import router as handlers_router
from adapters.transport.handlers.router import TransportHandlers
from ports.ingestion import IngestionJob, IngestionStatus, IngestionTrigger


class _StubQueryPort:
    def query(self, request):
        raise NotImplementedError


class _StubIngestionPort:
    def list_sources(self):
        raise NotImplementedError

    def start_reindex(
        self, trigger, *, force_rebuild: bool = False, callbacks=None
    ):
        raise NotImplementedError


class _StubHealthPort:
    def evaluate(self):
        raise NotImplementedError


def test_transport_handlers_runs_shutdown_hooks(monkeypatch):
    """register_shutdown_hook should run hooks once close() is invoked."""

    query_port = _StubQueryPort()
    ingestion_port = _StubIngestionPort()
    health_port = _StubHealthPort()

    handlers = TransportHandlers(
        query_port=query_port,
        ingestion_port=ingestion_port,
        health_port=health_port,
    )

    calls: list[str] = []

    handlers.register_shutdown_hook(lambda: calls.append("first"))
    handlers.register_shutdown_hook(lambda: calls.append("second"))

    handlers.close()

    assert calls == ["first", "second"], "all registered hooks must run on close()"

    handlers.close()
    assert calls == ["first", "second"], "close() should be idempotent"


def test_transport_handlers_passes_force_flag(monkeypatch):
    """_handle_reindex should forward force flag to ingestion port."""

    class _IngestionRecorder(_StubIngestionPort):
        def __init__(self):
            self.force_flags: list[bool] = []

        def start_reindex(self, trigger, *, force_rebuild: bool = False, callbacks=None):
            self.force_flags.append(force_rebuild)
            now = dt.datetime.now(dt.timezone.utc)
            return IngestionJob(
                job_id="job-1",
                source_alias="*",
                status=IngestionStatus.RUNNING,
                requested_at=now,
                started_at=now,
                completed_at=None,
                documents_processed=0,
                stage="preparing_index",
                percent_complete=0.0,
                error_message=None,
                trigger=IngestionTrigger.MANUAL,
            )

    ingestion = _IngestionRecorder()
    monkeypatch.setattr(
        handlers_router,
        "asyncio",
        SimpleNamespace(get_running_loop=lambda: SimpleNamespace()),
    )

    class _StreamStub:
        def __init__(self, loop):
            self.callbacks = None

    monkeypatch.setattr(handlers_router, "_JobStream", lambda loop: _StreamStub(loop))

    handlers = TransportHandlers(
        query_port=_StubQueryPort(),
        ingestion_port=ingestion,
        health_port=_StubHealthPort(),
    )

    response = handlers._handle_reindex({"trigger": "manual", "force": True})

    assert ingestion.force_flags == [True]
    assert response.initial_status == 202
