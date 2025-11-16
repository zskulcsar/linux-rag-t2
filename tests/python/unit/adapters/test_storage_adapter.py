"""Unit tests safeguarding catalog storage and audit logging adapters."""

import datetime as dt
import json
from pathlib import Path

import pytest

from adapters.storage.audit_log import AuditLogger
from adapters.storage.catalog import CatalogStorage
from ports.ingestion import (
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
)


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, second, tzinfo=dt.timezone.utc)


def _sample_catalog() -> SourceCatalog:
    sources = [
        SourceRecord(
            alias="man-pages",
            type=SourceType.MAN,
            location="/usr/share/man",
            language="en",
            size_bytes=1024,
            last_updated=_utc(2025, 1, 1, 12, 0, 0),
            status=SourceStatus.ACTIVE,
            checksum="abc123",
            notes=None,
        ),
        SourceRecord(
            alias="info-pages",
            type=SourceType.INFO,
            location="/usr/share/info",
            language="en",
            size_bytes=2048,
            last_updated=_utc(2025, 1, 2, 9, 30, 0),
            status=SourceStatus.PENDING_VALIDATION,
            checksum=None,
            notes="Initial import pending checksum verification.",
        ),
    ]
    snapshots = [
        SourceSnapshot(alias="man-pages", checksum="abc123"),
        SourceSnapshot(alias="info-pages", checksum="pending"),
    ]
    return SourceCatalog(
        version=3,
        updated_at=_utc(2025, 1, 2, 10, 0, 0),
        sources=sources,
        snapshots=snapshots,
    )


def test_catalog_storage_round_trip(
    tmp_path: Path, catalog_storage: CatalogStorage
) -> None:
    """Ensure catalog save/load preserves metadata without mutation."""

    data_dir = tmp_path / "xdg-data" / "ragcli"

    storage = catalog_storage
    catalog = _sample_catalog()

    storage.save(catalog)
    loaded = storage.load()

    assert loaded.version == catalog.version
    assert loaded.updated_at == catalog.updated_at
    assert loaded.snapshots == catalog.snapshots
    assert loaded.sources == catalog.sources
    assert (data_dir / "catalog.json").exists()


def test_catalog_storage_uses_atomic_write(
    tmp_path: Path, catalog_storage: CatalogStorage
) -> None:
    """Verify save writes via temporary file and cleans up after renaming."""

    data_dir = tmp_path / "xdg-data" / "ragcli"

    storage = catalog_storage
    catalog = _sample_catalog()

    storage.save(catalog)

    files = {path.name for path in data_dir.iterdir()}
    assert "catalog.json" in files
    assert not any(name.startswith(".catalog.json") for name in files), (
        "temporary file should be cleaned up"
    )


def test_audit_logger_appends_json_lines(tmp_path: Path) -> None:
    """Ensure audit logger writes newline-delimited JSON entries."""

    data_dir = tmp_path / "xdg-data" / "ragcli"
    logger = AuditLogger()

    entry = {
        "timestamp": "2025-01-02T10:00:00Z",
        "action": "source_quarantine",
        "target": "man-pages",
        "status": "failure",
        "trace_id": "trace-123",
        "message": "Checksum mismatch",
    }
    logger.append(entry)
    logger.append({**entry, "trace_id": "trace-456"})

    log_path = data_dir / "audit.log"
    contents = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 2
    for line in contents:
        payload = json.loads(line)
        assert payload["action"] == "source_quarantine"
        assert "trace_id" in payload


def test_audit_logger_adds_language_warning_for_non_english_mutations(
    tmp_path: Path,
) -> None:
    """Ensure audit logger annotates non-English mutations with warnings."""

    logger = AuditLogger()

    logger.log_mutation(
        action="source_add",
        alias="linuxwiki",
        status="success",
        language="fr",
        trace_id="trace-789",
        details="location=/data/linuxwiki_fr.zim",
    )

    log_path = tmp_path / "xdg-data" / "ragcli" / "audit.log"
    contents = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1
    entry = json.loads(contents[0])
    assert entry["action"] == "source_add"
    assert entry["target"] == "linuxwiki"
    assert entry["language"] == "fr"
    assert entry["warning"] == "non_english_language:fr"
    assert entry["status"] == "success"


def test_audit_logger_rejects_malformed_language_codes(tmp_path: Path) -> None:
    """Ensure invalid language codes are rejected during mutation logging."""

    logger = AuditLogger()

    with pytest.raises(ValueError):
        logger.log_mutation(
            action="source_add",
            alias="linuxwiki",
            status="success",
            language="123-invalid",
        )


def test_audit_logger_records_admin_init_entries(tmp_path: Path) -> None:
    """Ensure admin init events capture trace IDs and metadata."""

    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path, clock=lambda: _utc(2025, 1, 5, 8, 0, 0))

    logger.log_admin_init(
        status="success",
        trace_id="trace-init-123",
        created_directories=["/tmp/ragcli/config", "/tmp/ragcli/data"],
        seeded_sources=["man-pages", "info-pages"],
        dependency_checks=[{"component": "ollama", "status": "pass"}],
    )

    contents = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(contents) == 1
    entry = json.loads(contents[0])
    assert entry["action"] == "admin_init"
    assert entry["trace_id"] == "trace-init-123"
    assert entry["created_directories"] == [
        "/tmp/ragcli/config",
        "/tmp/ragcli/data",
    ]
    assert entry["seeded_sources"] == ["man-pages", "info-pages"]
    assert entry["dependency_checks"][0]["component"] == "ollama"


def test_audit_logger_records_health_entries_with_results(tmp_path: Path) -> None:
    """Ensure admin health events persist per-component data."""

    log_path = tmp_path / "audit.log"
    logger = AuditLogger(log_path=log_path, clock=lambda: _utc(2025, 1, 5, 9, 30, 0))

    logger.log_admin_health(
        overall_status="warn",
        trace_id="trace-health-abc",
        results=[
            {
                "component": "disk_capacity",
                "status": "warn",
                "message": "9% free space remaining",
                "remediation": "Delete temporary files.",
            }
        ],
    )

    entry = json.loads(log_path.read_text(encoding="utf-8"))
    assert entry["action"] == "admin_health"
    assert entry["overall_status"] == "warn"
    assert entry["trace_id"] == "trace-health-abc"
    assert entry["results"][0]["component"] == "disk_capacity"


def test_audit_logger_requires_trace_ids_for_admin_entries(tmp_path: Path) -> None:
    """Ensure admin logs reject missing trace identifiers."""

    logger = AuditLogger(log_path=tmp_path / "audit.log")

    with pytest.raises(ValueError):
        logger.log_admin_init(
            status="success",
            trace_id="",
            created_directories=[],
            seeded_sources=[],
            dependency_checks=None,
        )

    with pytest.raises(ValueError):
        logger.log_admin_health(
            overall_status="pass",
            trace_id=None,
            results=[],
        )


def test_catalog_storage_returns_empty_when_missing_file(
    tmp_path: Path, catalog_storage: CatalogStorage
) -> None:
    """Ensure load() returns an empty catalog when no file exists yet."""

    storage = catalog_storage
    catalog = storage.load()

    assert catalog.version == 0
    assert catalog.sources == []
    assert catalog.snapshots == []
