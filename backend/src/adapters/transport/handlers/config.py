"""Configuration helpers for the transport handlers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from adapters.observability import configure_phoenix, configure_structlog
from adapters.storage.catalog import CatalogStorage
from ports import SourceCatalog
from ports.ingestion import (
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
)

from .common import LOGGER, _clock

_OBSERVABILITY_READY = False


@dataclass(frozen=True)
class _BackendSettings:
    """Minimal runtime configuration for backend adapters."""

    weaviate_url: str
    ollama_url: str
    phoenix_url: str | None
    embedding_model: str
    completion_model: str


def _load_backend_settings() -> _BackendSettings:
    return _BackendSettings(
        weaviate_url=os.environ.get("RAG_BACKEND_WEAVIATE_URL", "http://127.0.0.1:8080"),
        ollama_url=os.environ.get("RAG_BACKEND_OLLAMA_URL", "http://127.0.0.1:11434"),
        phoenix_url=os.environ.get("RAG_BACKEND_PHOENIX_URL"),
        embedding_model=os.environ.get(
            "RAG_BACKEND_EMBED_MODEL", "embeddinggemma:latest"
        ),
        completion_model=os.environ.get("RAG_BACKEND_COMPLETION_MODEL", "gemma3:1b"),
    )


def _resolve_data_dir() -> Path:
    """Return the writable data directory for catalog artifacts."""

    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        return Path(data_home) / "ragcli"
    configured = os.environ.get("RAG_BACKEND_DATA_HOME")
    if configured:
        return Path(configured)
    return Path.cwd() / ".ragcli"


def _configure_observability(settings: _BackendSettings) -> None:
    global _OBSERVABILITY_READY
    if _OBSERVABILITY_READY:
        return

    configure_structlog(service_name="rag-backend")
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


def _seed_bootstrap_catalog(storage: CatalogStorage) -> None:
    """Populate a deterministic catalog snapshot for bootstrap behavior."""

    if os.environ.get("RAG_BACKEND_DISABLE_BOOTSTRAP") == "1":
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


__all__ = [
    "_BackendSettings",
    "_configure_observability",
    "_load_backend_settings",
    "_resolve_data_dir",
    "_seed_bootstrap_catalog",
]
