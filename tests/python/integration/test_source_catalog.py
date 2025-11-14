"""Integration tests for the source catalog application service."""

import datetime as dt
from pathlib import Path
from typing import Any

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


class _AuditRecorder:
    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def log_mutation(
        self,
        *,
        action: str,
        alias: str,
        status: str,
        language: str,
        trace_id: str | None = None,
        details: str | None = None,
    ) -> None:
        self.entries.append(
            {
                "action": action,
                "alias": alias,
                "status": status,
                "language": language,
                "trace_id": trace_id,
                "details": details,
            }
        )


def test_catalog_service_adds_source_and_persists_checksum(tmp_path: Path) -> None:
    """Source additions MUST persist checksum and snapshots while planning ingestion."""

    module = _import_source_catalog_module()
    storage = _RecordingStorage()
    hasher = _DeterministicHasher("abc123deadbeefabc123deadbeefabc123deadbeefabc123deadbeef")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    def clock(): _utc(2025, 1, 2, 9, 0)
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


def test_catalog_service_updates_metadata_and_replans_chunks(tmp_path: Path) -> None:
    """Updates MUST refresh checksums, size, and snapshots when location changes."""

    existing_record = ingestion_ports.SourceRecord(
        alias="linuxwiki",
        type=ingestion_ports.SourceType.KIWIX,
        location="/data/linuxwiki_v1.zim",
        language="en",
        size_bytes=1024,
        last_updated=_utc(2025, 1, 3, 9, 0),
        status=ingestion_ports.SourceStatus.QUARANTINED,
        checksum="oldsum",
        notes="Corrupted archive",
    )
    existing_catalog = ingestion_ports.SourceCatalog(
        version=5,
        updated_at=_utc(2025, 1, 3, 9, 0),
        sources=[existing_record],
        snapshots=[ingestion_ports.SourceSnapshot(alias="linuxwiki", checksum="oldsum")],
    )

    storage = _RecordingStorage(initial_catalog=existing_catalog)
    hasher = _DeterministicHasher("newchecksumabcd")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    def clock(): _utc(2025, 1, 4, 10, 30)
    service = _import_source_catalog_module().SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=clock,
    )

    artifact = tmp_path / "linuxwiki_v2.zim"
    artifact.write_bytes(b"linuxwiki v2 payload")

    result = service.update_source(
        "linuxwiki",
        ingestion_ports.SourceUpdateRequest(
            location=str(artifact),
            language="en",
            status=ingestion_ports.SourceStatus.ACTIVE,
            notes="Remediated archive",
        ),
    )

    assert result.source.location == str(artifact)
    assert result.source.status is ingestion_ports.SourceStatus.ACTIVE
    assert result.source.checksum == "newchecksumabcd"
    assert result.source.size_bytes == artifact.stat().st_size
    assert result.source.last_updated == clock()
    assert result.source.notes == "Remediated archive"
    assert storage.saved_catalogs, "expected catalog save after update"
    saved_catalog = storage.saved_catalogs[-1]
    assert saved_catalog.version == existing_catalog.version + 1
    snapshot = next(
        snap for snap in saved_catalog.snapshots if snap.alias == "linuxwiki"
    )
    assert snapshot.checksum == "newchecksumabcd"
    assert chunk_builder.calls and chunk_builder.calls[-1][0] == "linuxwiki"
    assert chunk_builder.generated_ids == [
        "linuxwiki:newchecksumabcd:0",
        "linuxwiki:newchecksumabcd:1",
    ]


def test_catalog_service_update_without_location_preserves_checksum() -> None:
    """Metadata-only updates MUST avoid recomputing checksums or chunk plans."""

    existing_record = ingestion_ports.SourceRecord(
        alias="man-pages",
        type=ingestion_ports.SourceType.MAN,
        location="/usr/share/man",
        language="en",
        size_bytes=2048,
        last_updated=_utc(2025, 1, 2, 12, 0),
        status=ingestion_ports.SourceStatus.ACTIVE,
        checksum="mansum",
        notes="baseline",
    )
    existing_catalog = ingestion_ports.SourceCatalog(
        version=7,
        updated_at=_utc(2025, 1, 2, 12, 0),
        sources=[existing_record],
        snapshots=[ingestion_ports.SourceSnapshot(alias="man-pages", checksum="mansum")],
    )

    storage = _RecordingStorage(initial_catalog=existing_catalog)
    hasher = _DeterministicHasher("mansum-updated")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.MAN)
    def clock(): _utc(2025, 1, 5, 8, 45)
    service = _import_source_catalog_module().SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=clock,
    )

    result = service.update_source(
        "man-pages",
        ingestion_ports.SourceUpdateRequest(
            language="en",
            status=ingestion_ports.SourceStatus.QUARANTINED,
            notes="Path missing on disk",
        ),
    )

    assert result.source.location == existing_record.location
    assert result.source.checksum == "mansum"
    assert result.source.size_bytes == existing_record.size_bytes
    assert result.source.status is ingestion_ports.SourceStatus.QUARANTINED
    assert result.source.notes == "Path missing on disk"
    assert not hasher.paths, "checksum recalculation should not occur"
    assert not chunk_builder.calls, "chunk builder should not run without new location"


def test_catalog_service_emits_audit_entries_for_mutations(tmp_path: Path) -> None:
    """Ensure catalog mutations emit audit entries with language metadata."""

    module = _import_source_catalog_module()
    storage = _RecordingStorage()
    hasher = _DeterministicHasher("abc123")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    audit = _AuditRecorder()
    def clock(): _utc(2025, 1, 5, 7, 45)
    service = module.SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=clock,
        audit_logger=audit,
    )

    artifact = tmp_path / "linuxwiki_fr.zim"
    artifact.write_bytes(b"content")
    request = ingestion_ports.SourceCreateRequest(
        type=ingestion_ports.SourceType.KIWIX,
        location=str(artifact),
        language="fr",
        notes=None,
    )

    service.create_source(request=request)
    assert audit.entries, "expected audit entry for source creation"
    saved_alias = storage.saved_catalogs[-1].sources[-1].alias
    entry = audit.entries[-1]
    assert entry["action"] == "source_add"
    assert entry["alias"] == saved_alias
    assert entry["language"] == "fr"

def test_catalog_service_remove_source_marks_quarantine() -> None:
    """Removal MUST mark the source as quarantined and drop snapshots."""

    existing_record = ingestion_ports.SourceRecord(
        alias="linuxwiki",
        type=ingestion_ports.SourceType.KIWIX,
        location="/data/linuxwiki.zim",
        language="en",
        size_bytes=4096,
        last_updated=_utc(2025, 1, 3, 8, 0),
        status=ingestion_ports.SourceStatus.ACTIVE,
        checksum="checksum-linuxwiki",
        notes="Trusted snapshot",
    )
    existing_catalog = ingestion_ports.SourceCatalog(
        version=10,
        updated_at=_utc(2025, 1, 3, 8, 0),
        sources=[existing_record],
        snapshots=[
            ingestion_ports.SourceSnapshot(
                alias="linuxwiki", checksum="checksum-linuxwiki"
            )
        ],
    )

    storage = _RecordingStorage(initial_catalog=existing_catalog)
    hasher = _DeterministicHasher("unused-checksum")
    chunk_builder = _RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX)
    def clock(): _utc(2025, 1, 6, 14, 0)
    service = _import_source_catalog_module().SourceCatalogService(
        storage=storage,
        checksum_calculator=hasher,
        chunk_builder=chunk_builder,
        clock=clock,
    )

    result = service.remove_source(
        "linuxwiki", reason="Duplicate content detected in upload"
    )

    assert result.source.status is ingestion_ports.SourceStatus.QUARANTINED
    assert "Duplicate content detected" in (result.source.notes or "")
    assert result.source.last_updated == clock()
    assert storage.saved_catalogs, "expected removal to persist catalog"
    saved_catalog = storage.saved_catalogs[-1]
    assert saved_catalog.version == existing_catalog.version + 1
    assert not any(
        snapshot.alias == "linuxwiki" for snapshot in saved_catalog.snapshots
    ), "quarantined sources must be removed from active snapshots"
    assert chunk_builder.calls == [], "removal should not enqueue chunk planning"
    assert not hasher.paths, "removal should not recompute checksums"


def test_catalog_service_remove_source_missing_alias_raises() -> None:
    """Removal MUST raise ValueError when alias is unknown."""

    empty_catalog = ingestion_ports.SourceCatalog(
        version=1,
        updated_at=_utc(2025, 1, 1, 0, 0),
        sources=[],
        snapshots=[],
    )
    storage = _RecordingStorage(initial_catalog=empty_catalog)
    service = _import_source_catalog_module().SourceCatalogService(
        storage=storage,
        checksum_calculator=_DeterministicHasher("unused"),
        chunk_builder=_RecordingChunkBuilder(ingestion_ports.SourceType.KIWIX),
    )

    with pytest.raises(ValueError):
        service.remove_source("unknown-alias", reason="Clean up missing entry")
