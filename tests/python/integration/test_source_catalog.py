"""Integration tests for the source catalog application service."""

import datetime as dt
from pathlib import Path

import pytest

from adapters.weaviate.client import Document
from ports import ingestion as ingestion_ports


def _import_source_catalog_module():
    try:
        from application import source_catalog  # type: ignore import-not-found
    except ImportError as exc:  # pragma: no cover - explicit failure message
        raise AssertionError(
            "application.source_catalog must define SourceCatalogService to manage "
            "catalog lifecycle, alias collisions, checksum persistence, and "
            "ingestion planning."
        ) from exc

    if not hasattr(source_catalog, "SourceCatalogService"):
        raise AssertionError(
            "application.source_catalog must expose a SourceCatalogService class."
        )
    return source_catalog


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


class _RecordingStorage:
    def __init__(
        self,
        *,
        initial_catalog: ingestion_ports.SourceCatalog | None = None,
    ) -> None:
        now = _utc(2025, 1, 1, 9, 0)
        self._catalog = initial_catalog or ingestion_ports.SourceCatalog(
            version=1,
            updated_at=now,
            sources=[],
            snapshots=[],
        )
        self.saved_catalogs: list[ingestion_ports.SourceCatalog] = []

    def load(self) -> ingestion_ports.SourceCatalog:
        return self._catalog

    def save(self, catalog: ingestion_ports.SourceCatalog) -> None:
        self.saved_catalogs.append(catalog)
        self._catalog = catalog


class _DeterministicHasher:
    def __init__(self, digest: str) -> None:
        self._digest = digest
        self.paths: list[Path] = []

    def __call__(self, path: Path) -> str:
        self.paths.append(path)
        return self._digest


class _RecordingChunkBuilder:
    def __init__(self, source_type: ingestion_ports.SourceType) -> None:
        self.source_type = source_type
        self.calls: list[tuple[str, str, Path]] = []
        self.generated_ids: list[str] = []

    def __call__(self, *, alias: str, checksum: str, location: Path) -> list[Document]:
        self.calls.append((alias, checksum, location))
        documents: list[Document] = []
        for chunk_id in range(2):
            document = Document(
                alias=alias,
                checksum=checksum,
                chunk_id=chunk_id,
                text=f"chunk-{chunk_id}",
                source_type=self.source_type,
                language="en",
            )
            self.generated_ids.append(document.document_id)
            documents.append(document)
        return documents


def test_catalog_service_adds_source_and_persists_checksum(tmp_path: Path) -> None:
    """Source additions MUST persist checksum and snapshots while planning ingestion."""

    module = _import_source_catalog_module()
    storage = _RecordingStorage()
    hasher = _DeterministicHasher("abc123deadbeefabc123deadbeefabc123deadbeefabc123deadbeef")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    clock = lambda: _utc(2025, 1, 2, 9, 0)
    service = module.SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=clock,
    )

    artifact = tmp_path / "linuxwiki_en.zim"
    artifact.write_bytes(b"offline-linuxwiki")
    request = ingestion_ports.SourceCreateRequest(
        type=ingestion_ports.SourceType.KIWIX,
        location=str(artifact),
        language="en",
        notes="Offline Linux wiki snapshot",
    )

    result = service.create_source(request=request)

    assert isinstance(result, ingestion_ports.SourceMutationResult)
    assert storage.saved_catalogs, "expected catalog save after source creation"
    catalog = storage.saved_catalogs[-1]
    saved_source = catalog.sources[-1]
    assert saved_source.alias == result.source.alias
    assert saved_source.checksum == "abc123deadbeefabc123deadbeefabc123deadbeefabc123deadbeef"
    assert catalog.snapshots[-1].checksum == saved_source.checksum
    assert saved_source.status is ingestion_ports.SourceStatus.PENDING_VALIDATION
    assert saved_source.size_bytes == artifact.stat().st_size
    assert hasher.paths and hasher.paths[-1] == artifact

    listed = service.list_sources()
    assert any(src.alias == saved_source.alias for src in listed.sources)
    assert chunk_builder.calls, "expected chunk builder to prepare ingestion documents"
    assert chunk_builder.generated_ids == [
        f"{saved_source.alias}:{saved_source.checksum}:0",
        f"{saved_source.alias}:{saved_source.checksum}:1",
    ], "document identifiers must follow <alias>:<checksum>:<chunk_id>"


def test_catalog_service_appends_suffix_for_alias_collisions(tmp_path: Path) -> None:
    """Alias collisions MUST append incremental numeric suffixes."""

    existing_catalog = ingestion_ports.SourceCatalog(
        version=2,
        updated_at=_utc(2025, 1, 3, 8, 30),
        sources=[
            ingestion_ports.SourceRecord(
                alias="linuxwiki",
                type=ingestion_ports.SourceType.KIWIX,
                location="/data/linuxwiki_en.zim",
                language="en",
                size_bytes=1024,
                last_updated=_utc(2025, 1, 3, 8, 0),
                status=ingestion_ports.SourceStatus.ACTIVE,
                checksum="abc123",
                notes=None,
            )
        ],
        snapshots=[
            ingestion_ports.SourceSnapshot(alias="linuxwiki", checksum="abc123"),
        ],
    )

    module = _import_source_catalog_module()
    storage = _RecordingStorage(initial_catalog=existing_catalog)
    hasher = _DeterministicHasher("def4567890abcdefdef4567890abcdefdef4567890abcdefdef4567890abcd")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    service = module.SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=lambda: _utc(2025, 1, 4, 7, 45),
    )

    artifact = tmp_path / "linuxwiki.zim"
    artifact.write_bytes(b"linuxwiki-v2")
    request = ingestion_ports.SourceCreateRequest(
        type=ingestion_ports.SourceType.KIWIX,
        location=str(artifact),
        language="en",
    )

    result = service.create_source(request=request)

    assert result.source.alias == "linuxwiki-2"
    assert any(
        src.alias == "linuxwiki-2" for src in storage.saved_catalogs[-1].sources
    ), "new alias must be persisted in catalog"
    assert storage.saved_catalogs[-1].snapshots[-1].alias == "linuxwiki-2"
    assert chunk_builder.generated_ids == [
        f"linuxwiki-2:{result.source.checksum}:0",
        f"linuxwiki-2:{result.source.checksum}:1",
    ]
    assert result.source.size_bytes == artifact.stat().st_size
