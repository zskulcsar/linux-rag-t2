"""Factory helpers that wire transport handlers to the real services."""

from adapters.storage.audit_log import AuditLogger
from adapters.storage.catalog import CatalogStorage
from application.source_catalog import SourceCatalogService

from .builders import (
    _build_completion_adapter,
    _build_embedding_adapter,
    _build_query_runner,
    _build_weaviate_adapter,
    _calculate_checksum,
)
from .chunking import _chunk_builder_factory
from .common import _clock
from .config import (
    _configure_observability,
    _load_backend_settings,
    _resolve_data_dir,
    _seed_bootstrap_catalog,
)
from .health import _build_health_port
from .ports import CatalogIngestionPort, QueryRunnerPort
from .router import TransportHandlers


def create_default_handlers() -> TransportHandlers:
    """Create transport handlers backed by catalog services and health diagnostics."""

    settings = _load_backend_settings()
    _configure_observability(settings)

    storage = CatalogStorage(base_dir=_resolve_data_dir())
    _seed_bootstrap_catalog(storage)
    embedding_adapter = _build_embedding_adapter(settings)
    vector_adapter = _build_weaviate_adapter(settings)
    chunk_builder = _chunk_builder_factory(
        embedding_adapter=embedding_adapter,
        vector_adapter=vector_adapter,
    )
    completion_adapter = _build_completion_adapter(settings)
    query_runner = _build_query_runner(
        catalog_loader=storage.load,
        vector_adapter=vector_adapter,
        llm_adapter=completion_adapter,
    )
    audit_logger = AuditLogger()
    catalog_service = SourceCatalogService(
        storage=storage,
        checksum_calculator=_calculate_checksum,
        chunk_builder=chunk_builder,
        audit_logger=audit_logger,
    )

    ingestion_port = CatalogIngestionPort(service=catalog_service, storage=storage)
    query_port = QueryRunnerPort(query_runner)
    health_port = _build_health_port(storage=storage, settings=settings)

    return TransportHandlers(
        query_port=query_port,
        ingestion_port=ingestion_port,
        health_port=health_port,
        _clock=_clock,
    )


__all__ = ["create_default_handlers", "_chunk_builder_factory"]
