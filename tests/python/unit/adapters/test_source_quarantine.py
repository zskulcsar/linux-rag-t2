"""Unit tests for the source quarantine adapter."""

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

import pytest

from adapters.storage import quarantine as quarantine_module
from adapters.storage.catalog import CatalogStorage
from adapters.storage.quarantine import SourceQuarantineManager
from ports.ingestion import (
    SourceCatalog,
    SourceRecord,
    SourceStatus,
    SourceType,
)


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


@dataclass
class _AuditRecorder:
    """Capture audit entries passed to the manager."""

    entries: list[dict[str, Any]] = field(default_factory=list)

    def append(self, entry: dict[str, Any]) -> None:
        self.entries.append(entry)


def _catalog(updated_at: dt.datetime) -> SourceCatalog:
    sources = [
        SourceRecord(
            alias="man-pages",
            type=SourceType.MAN,
            location="/usr/share/man",
            language="en",
            size_bytes=1024,
            last_updated=_utc(2025, 1, 1, 12, 0),
            status=SourceStatus.ACTIVE,
            checksum="abc123",
            notes=None,
        ),
        SourceRecord(
            alias="info-pages",
            type=SourceType.INFO,
            location="/usr/share/info",
            language="en",
            size_bytes=512,
            last_updated=_utc(2025, 1, 1, 13, 0),
            status=SourceStatus.ACTIVE,
            checksum="def456",
            notes="Initial validation succeeded.",
        ),
    ]

    return SourceCatalog(
        version=5, updated_at=updated_at, sources=sources, snapshots=[]
    )


def test_quarantine_manager_updates_catalog_and_audit_log(
    catalog_storage: CatalogStorage,
) -> None:
    """Ensure manager marks the source as quarantined and records audit metadata."""

    storage = catalog_storage
    catalog = _catalog(updated_at=_utc(2025, 1, 2, 9, 0))
    storage.save(catalog)

    audit = _AuditRecorder()
    quarantine_time = _utc(2025, 1, 2, 10, 30)
    manager = SourceQuarantineManager(
        catalog_storage=storage,
        audit_logger=audit,
        clock=lambda: quarantine_time,
    )

    manager.quarantine(alias="info-pages", reason="Checksum mismatch detected.")

    updated = storage.load()
    assert updated.version == catalog.version + 1
    assert updated.updated_at == quarantine_time

    record = next(entry for entry in updated.sources if entry.alias == "info-pages")
    assert record.status is SourceStatus.QUARANTINED
    assert "Checksum mismatch" in (record.notes or "")
    assert record.last_updated == quarantine_time

    assert audit.entries
    audit_entry = audit.entries[0]
    assert audit_entry["action"] == "source_quarantine"
    assert audit_entry["status"] == "failure"
    assert audit_entry["target"] == "info-pages"


def test_quarantine_manager_rejects_unknown_alias(
    catalog_storage: CatalogStorage,
) -> None:
    """Ensure attempting to quarantine a missing alias raises a ValueError."""

    storage = catalog_storage
    storage.save(_catalog(updated_at=_utc(2025, 1, 2, 9, 0)))

    manager = SourceQuarantineManager(
        catalog_storage=storage,
        audit_logger=_AuditRecorder(),
        clock=lambda: _utc(2025, 1, 2, 10, 30),
    )

    with pytest.raises(ValueError):
        manager.quarantine(alias="missing", reason="not found")


def test_quarantine_manager_uses_default_clock(
    catalog_storage: CatalogStorage, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure default clock injection supplies timestamps when no override provided."""

    sentinel = _utc(2025, 1, 2, 12, 0)
    monkeypatch.setattr("adapters.storage.quarantine.utc_now", lambda: sentinel)
    storage = catalog_storage
    catalog = _catalog(updated_at=_utc(2025, 1, 2, 9, 0))
    storage.save(catalog)

    audit = _AuditRecorder()
    manager = SourceQuarantineManager(
        catalog_storage=storage,
        audit_logger=audit,
    )
    manager.quarantine(alias="man-pages", reason="Automated remediation")

    updated = storage.load()
    record = next(entry for entry in updated.sources if entry.alias == "man-pages")
    assert record.last_updated == sentinel
    assert audit.entries[0]["timestamp"] == sentinel.isoformat()


def test_quarantine_default_clock_returns_aware_timestamp() -> None:
    """Ensure the fallback clock helper returns a timezone-aware timestamp."""

    timestamp = quarantine_module.utc_now()
    assert timestamp.tzinfo is not None
