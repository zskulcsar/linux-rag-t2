"""Serialization helpers for transport payloads."""

import dataclasses
from typing import Any

from ports import (
    HealthCheck,
    HealthComponent,
    HealthReport,
    HealthStatus,
    IngestionJob,
    QueryResponse,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
)
from ports.ingestion import IngestionStatus, IngestionTrigger


def serialize_query_response(response: QueryResponse) -> dict[str, Any]:
    """Convert a :class:`QueryResponse` into a JSON-serializable mapping."""

    payload = dataclasses.asdict(response)
    payload["citations"] = [
        dataclasses.asdict(citation) for citation in response.citations
    ]
    payload["references"] = [
        dataclasses.asdict(reference) for reference in response.references
    ]
    return payload


def serialize_catalog(catalog: SourceCatalog) -> dict[str, Any]:
    """Serialize the source catalog to the transport schema."""

    return {
        "catalog_version": catalog.version,
        "updated_at": catalog.updated_at.isoformat(),
        "sources": [serialize_source_record(source) for source in catalog.sources],
        "snapshots": [_serialize_snapshot(snapshot) for snapshot in catalog.snapshots],
    }


def serialize_source_record(record: SourceRecord) -> dict[str, Any]:
    """Serialize a single :class:`SourceRecord` to transport format."""

    status = record.status.value if hasattr(record.status, "value") else record.status
    return {
        "alias": record.alias,
        "type": record.type.value if hasattr(record.type, "value") else record.type,
        "location": record.location,
        "language": record.language,
        "size_bytes": record.size_bytes,
        "last_updated": record.last_updated.isoformat(),
        "status": status,
        "checksum": record.checksum,
    }


def serialize_ingestion_job(job: IngestionJob) -> dict[str, Any]:
    """Return the transport representation of an ingestion job."""

    return {
        "job_id": job.job_id,
        "source_alias": job.source_alias,
        "status": job.status.value
        if isinstance(job.status, IngestionStatus)
        else str(job.status),
        "requested_at": job.requested_at.isoformat(),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "documents_processed": job.documents_processed,
        "stage": job.stage,
        "percent_complete": job.percent_complete,
        "error_message": job.error_message,
        "trigger": job.trigger.value
        if isinstance(job.trigger, IngestionTrigger)
        else str(job.trigger),
    }


def _serialize_snapshot(snapshot: SourceSnapshot) -> dict[str, Any]:
    return {"alias": snapshot.alias, "checksum": snapshot.checksum}


def serialize_health_report(report: HealthReport) -> dict[str, Any]:
    """Serialize a :class:`HealthReport` into the transport payload schema.

    Args:
        report: Aggregated health report produced by :class:`HealthPort`.

    Returns:
        Mapping describing the overall status, generation timestamp, and per
        component results that clients can render.

    Example:
        >>> summary = serialize_health_report(  # doctest: +SKIP
        ...     HealthReport(
        ...         status=HealthStatus.PASS,
        ...         checks=[
        ...             HealthCheck(
        ...                 component="disk_capacity",
        ...                 status=HealthStatus.PASS,
        ...                 message="Healthy",
        ...             )
        ...         ],
        ...     )
        ... )
        >>> summary["overall_status"]  # doctest: +SKIP
        'pass'
    """

    return {
        "overall_status": _status_string(report.status),
        "generated_at": report.generated_at.isoformat(),
        "results": [_serialize_health_check(check) for check in report.checks],
    }


def _serialize_health_check(check: HealthCheck) -> dict[str, Any]:
    component = check.component
    if isinstance(component, HealthComponent):
        component_name = component.value
    else:
        component_name = str(component)
    payload: dict[str, Any] = {
        "component": component_name,
        "status": _status_string(check.status),
        "message": check.message,
        "timestamp": check.timestamp.isoformat(),
    }
    if check.remediation:
        payload["remediation"] = check.remediation
    if check.metrics:
        payload["metrics"] = dict(check.metrics)
    return payload


def _status_string(value: HealthStatus | str) -> str:
    return value.value if hasattr(value, "value") else str(value)


__all__ = [
    "serialize_catalog",
    "serialize_health_report",
    "serialize_ingestion_job",
    "serialize_query_response",
    "serialize_source_record",
]
