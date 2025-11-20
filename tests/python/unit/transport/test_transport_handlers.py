"""Unit tests for TransportHandlers shutdown semantics."""

from __future__ import annotations

from adapters.transport.handlers.router import TransportHandlers


class _StubQueryPort:
    def query(self, request):
        raise NotImplementedError


class _StubIngestionPort:
    def list_sources(self):
        raise NotImplementedError

    def start_reindex(self, trigger, callbacks=None):
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
