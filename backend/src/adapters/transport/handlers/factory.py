"""Factory helpers that wire transport handlers to the real services."""

from adapters.observability import configure_phoenix, configure_structlog
from adapters.storage.audit_log import AuditLogger
from adapters.storage.catalog import CatalogStorage
from application.handler_settings import HandlerSettings, load_handler_settings_from_env
from application.source_catalog import SourceCatalogService
from ports import SourceCatalog
from ports.ingestion import (
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
)

from .builders import (
    _build_completion_adapter,
    _build_embedding_adapter,
    _build_query_runner,
    _build_weaviate_adapter,
    _calculate_checksum,
)
from .chunking import _chunk_builder_factory
from .common import LOGGER, _clock
from .health import _build_health_port
from .ports import CatalogIngestionPort, QueryRunnerPort
from .router import TransportHandlers

_OBSERVABILITY_READY = False


def create_default_handlers(
    settings: HandlerSettings | None = None,
) -> TransportHandlers:
    """Create transport handlers backed by catalog services and health diagnostics."""

    active_settings = settings or load_handler_settings_from_env()
    _configure_observability(active_settings)

    storage = CatalogStorage(base_dir=active_settings.data_dir)
    _seed_bootstrap_catalog(storage, disable=active_settings.disable_bootstrap)
    embedding_adapter = _build_embedding_adapter(active_settings)
    vector_adapter = _build_weaviate_adapter(active_settings)
    chunk_builder = _chunk_builder_factory(
        embedding_adapter=embedding_adapter,
        vector_adapter=vector_adapter,
    )
    completion_adapter = _build_completion_adapter(active_settings)
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
    health_port = _build_health_port(storage=storage, settings=active_settings)

    return TransportHandlers(
        query_port=query_port,
        ingestion_port=ingestion_port,
        health_port=health_port,
        audit_logger=audit_logger,
        _clock=_clock,
    )


def _configure_observability(settings: HandlerSettings) -> None:
    global _OBSERVABILITY_READY
    if _OBSERVABILITY_READY:
        return

    # TODO: review
    #configure_structlog(service_name="rag-backend")
    if settings.phoenix_url:
        try:
            configure_phoenix(
                service_name="rag-backend",
                endpoint=settings.phoenix_url,
            )
        except RuntimeError as exc:  # pragma: no cover - phoenix optional in tests
            LOGGER.warning(
                "factory.configure_observability(settings) :: phoenix_configuration_failed",
                error=str(exc),
            )
    _OBSERVABILITY_READY = True


def _seed_bootstrap_catalog(
    storage: CatalogStorage,
    *,
    disable: bool,
) -> None:
    """Populate a deterministic catalog snapshot for bootstrap behavior."""

    if disable:
        return

    catalog = storage.load()
    if catalog.version > 0 and catalog.snapshots:
        return

    now = _clock()
    sources = [
        SourceRecord(
            alias="man-pages",
            type=SourceType.MAN,
            location="/usr/share/man",
            language="en",
            size_bytes=1024 * 1024 * 350,
            last_updated=now,
            status=SourceStatus.ACTIVE,
            checksum="sha256:bootstrap-man",
        ),
        SourceRecord(
            alias="info-pages",
            type=SourceType.INFO,
            location="/usr/share/info",
            language="en",
            size_bytes=1024 * 1024 * 120,
            last_updated=now,
            status=SourceStatus.ACTIVE,
            checksum="sha256:bootstrap-info",
        ),
    ]
    snapshots = [
        SourceSnapshot(alias="man-pages", checksum="sha256:bootstrap-man"),
        SourceSnapshot(alias="info-pages", checksum="sha256:bootstrap-info"),
    ]
    storage.save(
        SourceCatalog(
            version=1,
            updated_at=now,
            sources=sources,
            snapshots=snapshots,
        )
    )


__all__ = ["create_default_handlers", "_chunk_builder_factory"]
