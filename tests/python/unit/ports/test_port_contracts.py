"""Contract tests for backend port definitions.

These tests document the expected dataclass fields and protocol method
signatures for the query, ingestion, and health ports. Implementation
tasks must satisfy these contracts without altering the shapes asserted
below.
"""


import dataclasses
import importlib
import inspect
import types
import datetime as dt
import enum
from typing import Any, Protocol, Union, get_args, get_origin, get_type_hints


def _assert_list_of(annotation: Any, expected_inner: Any) -> None:
    """Validate that an annotation represents list[expected_inner]."""

    origin = get_origin(annotation)
    assert origin is list, f"expected list[...] annotation, got {annotation!r}"
    (inner,) = get_args(annotation)
    assert inner is expected_inner, (
        f"expected inner type {expected_inner!r}, got {inner!r}"
    )


def _assert_optional(annotation: Any, expected_inner: Any) -> None:
    """Validate that an annotation represents optional expected_inner."""

    if annotation == expected_inner | type(None):
        return

    origin = get_origin(annotation)
    assert origin in {Union, types.UnionType}, (
        f"expected optional {expected_inner!r}, got {annotation!r}"
    )
    args = set(get_args(annotation))
    assert expected_inner in args and type(None) in args, (
        f"expected optional {expected_inner!r}, got {annotation!r}"
    )


def test_query_port_contract_shapes() -> None:
    """Require the query port types and protocol to match the transport contract."""

    module = importlib.import_module("ports.query")

    query_request = getattr(module, "QueryRequest", None)
    query_response = getattr(module, "QueryResponse", None)
    reference = getattr(module, "Reference", None)
    citation = getattr(module, "Citation", None)
    query_port = getattr(module, "QueryPort", None)

    assert dataclasses.is_dataclass(reference), "Reference dataclass must be defined"
    ref_hints = get_type_hints(reference)
    assert ref_hints["label"] is str
    _assert_optional(ref_hints["url"], str)
    _assert_optional(ref_hints["notes"], str)

    assert dataclasses.is_dataclass(citation), "Citation dataclass must be defined"
    citation_hints = get_type_hints(citation)
    assert citation_hints["alias"] is str
    assert citation_hints["document_ref"] is str
    _assert_optional(citation_hints["excerpt"], str)

    assert dataclasses.is_dataclass(query_request), (
        "QueryRequest dataclass must be defined"
    )
    request_hints = get_type_hints(query_request)
    assert request_hints["question"] is str
    _assert_optional(request_hints["conversation_id"], str)
    assert request_hints["max_context_tokens"] is int
    _assert_optional(request_hints["trace_id"], str)

    assert dataclasses.is_dataclass(query_response), (
        "QueryResponse dataclass must be defined"
    )
    response_hints = get_type_hints(query_response)
    assert response_hints["summary"] is str
    _assert_list_of(response_hints["steps"], str)
    _assert_list_of(response_hints["references"], reference)
    _assert_list_of(response_hints["citations"], citation)
    assert response_hints["confidence"] is float
    assert response_hints["trace_id"] is str
    assert response_hints["latency_ms"] is int
    _assert_optional(response_hints["retrieval_latency_ms"], int)
    _assert_optional(response_hints["llm_latency_ms"], int)
    _assert_optional(response_hints["index_version"], str)
    _assert_optional(response_hints["answer"], str)
    assert response_hints["no_answer"] is bool

    assert inspect.isclass(query_port), "QueryPort protocol must exist"
    assert issubclass(query_port, Protocol), "QueryPort must extend typing.Protocol"
    method = getattr(query_port, "query", None)
    assert method is not None, "QueryPort.query method must be defined"
    signature = inspect.signature(method)
    params = list(signature.parameters.values())
    assert len(params) == 2 and params[0].name == "self", (
        "QueryPort.query must accept self and request"
    )

    method_hints = get_type_hints(method, module.__dict__)
    assert method_hints["request"] is query_request
    assert method_hints["return"] is query_response


def test_ingestion_port_contract_shapes() -> None:
    """Require the ingestion port types to reflect catalog, job, and adapter contracts."""

    module = importlib.import_module("ports.ingestion")

    source_type = getattr(module, "SourceType", None)
    source_status = getattr(module, "SourceStatus", None)
    ingestion_status = getattr(module, "IngestionStatus", None)
    ingestion_trigger = getattr(module, "IngestionTrigger", None)
    source_create = getattr(module, "SourceCreateRequest", None)
    source_update = getattr(module, "SourceUpdateRequest", None)
    source_record = getattr(module, "SourceRecord", None)
    source_catalog = getattr(module, "SourceCatalog", None)
    source_mutation = getattr(module, "SourceMutationResult", None)
    ingestion_job = getattr(module, "IngestionJob", None)
    snapshot_entry = getattr(module, "SourceSnapshot", None)
    ingestion_port = getattr(module, "IngestionPort", None)

    assert issubclass(source_type, enum.Enum)
    assert {member.value for member in source_type} == {"man", "kiwix", "info"}

    assert issubclass(source_status, enum.Enum)
    assert {member.value for member in source_status} == {
        "pending_validation",
        "active",
        "quarantined",
        "error",
    }

    assert issubclass(ingestion_status, enum.Enum)
    assert {member.value for member in ingestion_status} == {
        "queued",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    }

    assert issubclass(ingestion_trigger, enum.Enum)
    assert {member.value for member in ingestion_trigger} == {
        "init",
        "manual",
        "scheduled",
    }

    assert dataclasses.is_dataclass(snapshot_entry)
    snapshot_hints = get_type_hints(snapshot_entry)
    assert snapshot_hints["alias"] is str
    assert snapshot_hints["checksum"] is str

    assert dataclasses.is_dataclass(source_create)
    create_hints = get_type_hints(source_create)
    assert create_hints["type"] is source_type
    assert create_hints["location"] is str
    _assert_optional(create_hints["language"], str)
    _assert_optional(create_hints["notes"], str)

    assert dataclasses.is_dataclass(source_update)
    update_hints = get_type_hints(source_update)
    _assert_optional(update_hints["location"], str)
    _assert_optional(update_hints["notes"], str)
    _assert_optional(update_hints["language"], str)
    _assert_optional(update_hints["status"], source_status)

    assert dataclasses.is_dataclass(source_record)
    record_hints = get_type_hints(source_record)
    assert record_hints["alias"] is str
    assert record_hints["type"] is source_type
    assert record_hints["location"] is str
    assert record_hints["language"] is str
    assert record_hints["size_bytes"] is int
    assert record_hints["last_updated"] is dt.datetime
    assert record_hints["status"] is source_status
    _assert_optional(record_hints["checksum"], str)
    _assert_optional(record_hints["notes"], str)

    assert dataclasses.is_dataclass(source_catalog)
    catalog_hints = get_type_hints(source_catalog)
    assert catalog_hints["version"] is int
    assert catalog_hints["updated_at"] is dt.datetime
    _assert_list_of(catalog_hints["sources"], source_record)
    _assert_list_of(catalog_hints["snapshots"], snapshot_entry)

    assert dataclasses.is_dataclass(ingestion_job)
    job_hints = get_type_hints(ingestion_job)
    assert job_hints["job_id"] is str
    assert job_hints["source_alias"] is str
    assert job_hints["status"] is ingestion_status
    assert job_hints["requested_at"] is dt.datetime
    _assert_optional(job_hints["started_at"], dt.datetime)
    _assert_optional(job_hints["completed_at"], dt.datetime)
    assert job_hints["documents_processed"] is int
    _assert_optional(job_hints["stage"], str)
    _assert_optional(job_hints["percent_complete"], float)
    _assert_optional(job_hints["error_message"], str)
    assert job_hints["trigger"] is ingestion_trigger

    assert dataclasses.is_dataclass(source_mutation)
    mutation_hints = get_type_hints(source_mutation)
    assert mutation_hints["source"] is source_record
    _assert_optional(mutation_hints["job"], ingestion_job)

    assert inspect.isclass(ingestion_port)
    assert issubclass(ingestion_port, Protocol)

    list_sig = inspect.signature(ingestion_port.list_sources)
    assert list_sig.return_annotation is source_catalog

    create_sig = inspect.signature(ingestion_port.create_source)
    params = list(create_sig.parameters.values())
    assert len(params) == 2 and params[1].annotation is source_create
    assert create_sig.return_annotation is source_mutation

    update_sig = inspect.signature(ingestion_port.update_source)
    update_params = list(update_sig.parameters.values())
    assert len(update_params) == 3
    assert update_params[1].annotation is str
    assert update_params[2].annotation is source_update
    assert update_sig.return_annotation is source_mutation

    remove_sig = inspect.signature(ingestion_port.remove_source)
    remove_params = list(remove_sig.parameters.values())
    assert len(remove_params) == 2 and remove_params[1].annotation is str
    assert remove_sig.return_annotation in {type(None), inspect._empty}

    reindex_sig = inspect.signature(ingestion_port.start_reindex)
    reindex_params = list(reindex_sig.parameters.values())
    assert (
        len(reindex_params) == 2 and reindex_params[1].annotation is ingestion_trigger
    )
    assert reindex_sig.return_annotation is ingestion_job


def test_health_port_contract_shapes() -> None:
    """Require the health port types to expose consistent telemetry and status enums."""

    module = importlib.import_module("ports.health")

    health_status = getattr(module, "HealthStatus", None)
    health_component = getattr(module, "HealthComponent", None)
    health_check = getattr(module, "HealthCheck", None)
    health_report = getattr(module, "HealthReport", None)
    health_port = getattr(module, "HealthPort", None)

    assert issubclass(health_status, enum.Enum)
    assert {member.value for member in health_status} == {"pass", "warn", "fail"}

    assert issubclass(health_component, enum.Enum)
    assert {member.value for member in health_component} == {
        "index_freshness",
        "source_access",
        "disk_capacity",
        "ollama",
        "weaviate",
        "phoenix",
    }

    assert dataclasses.is_dataclass(health_check)
    check_hints = get_type_hints(health_check)
    assert check_hints["component"] is health_component
    assert check_hints["status"] is health_status
    assert check_hints["message"] is str
    _assert_optional(check_hints["remediation"], str)
    assert check_hints["timestamp"] is dt.datetime
    metrics_hint = check_hints["metrics"]
    assert get_origin(metrics_hint) is dict
    key_type, value_type = get_args(metrics_hint)
    assert key_type is str
    if get_origin(value_type) is Union:
        assert set(get_args(value_type)) == {int, float}
    else:
        assert value_type in {int, float}

    assert dataclasses.is_dataclass(health_report)
    report_hints = get_type_hints(health_report)
    assert report_hints["status"] is health_status
    _assert_list_of(report_hints["checks"], health_check)
    assert report_hints["generated_at"] is dt.datetime

    assert inspect.isclass(health_port)
    assert issubclass(health_port, Protocol)
    evaluate_sig = inspect.signature(health_port.evaluate)
    assert evaluate_sig.return_annotation is health_report
