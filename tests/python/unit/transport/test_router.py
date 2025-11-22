"""Unit tests for the transport router handlers."""

from __future__ import annotations

from typing import Any, cast

import pytest

from adapters.transport.handlers.router import TransportHandlers
from adapters.transport.handlers.errors import TransportError
from ports import (
    HealthCheck,
    HealthComponent,
    HealthPort,
    HealthReport,
    HealthStatus,
    IngestionPort,
    QueryPort,
)


class _StubHealthPort(HealthPort):
    def __init__(self, report: HealthReport) -> None:
        self._report = report

    def evaluate(self) -> HealthReport:
        return self._report


class _RecordingAuditLogger:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def log_admin_health(
        self,
        *,
        overall_status: str,
        trace_id: str | None,
        results: list[dict[str, Any]] | None = None,
    ) -> None:
        self.calls.append(
            {
                "overall_status": overall_status,
                "trace_id": trace_id,
                "results": results or [],
            }
        )


def test_admin_health_dispatch_serializes_report_and_logs() -> None:
    """Admin health dispatch should serialize results and emit audit logs."""

    report = HealthReport(
        status=HealthStatus.WARN,
        checks=[
            HealthCheck(
                component=HealthComponent.DISK_CAPACITY,
                status=HealthStatus.WARN,
                message="9% free space remaining",
                remediation="Delete temporary files.",
                metrics={"percent_free": 9},
            )
        ],
    )
    handlers = TransportHandlers(
        query_port=cast(QueryPort, object()),
        ingestion_port=cast(IngestionPort, object()),
        health_port=_StubHealthPort(report),
    )
    logger = _RecordingAuditLogger()
    handlers.audit_logger = logger

    status, payload = handlers.dispatch(
        "/v1/admin/health",
        {"trace_id": "unit-trace"},
    )

    assert status == 200
    assert payload["overall_status"] == "warn"
    assert payload["trace_id"] == "unit-trace"
    assert payload["results"][0]["component"] == "disk_capacity"
    assert logger.calls == [
        {
            "overall_status": "warn",
            "trace_id": "unit-trace",
            "results": payload["results"],
        }
    ]


def test_admin_health_dispatch_requires_health_port() -> None:
    """Admin health dispatch should raise when no health port exists."""

    handlers = TransportHandlers(
        query_port=cast(QueryPort, object()),
        ingestion_port=cast(IngestionPort, object()),
        health_port=None,
    )

    with pytest.raises(TransportError) as excinfo:
        handlers.dispatch("/v1/admin/health", {"trace_id": "missing-port"})

    assert excinfo.value.status == 503
