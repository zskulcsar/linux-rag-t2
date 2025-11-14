"""Source accessibility failure scenarios for health diagnostics."""

from __future__ import annotations

import datetime as dt

from ports import ingestion as ingestion_ports
from ports.health import HealthComponent, HealthStatus


def _import_health_service_module():
    try:
        from application import health_service  # type: ignore import-not-found
    except ImportError as exc:
        raise AssertionError(
            "application.health_service must define HealthDiagnostics so missing sources are detected."
        ) from exc
    if not hasattr(health_service, "HealthDiagnostics"):
        raise AssertionError(
            "application.health_service must expose a HealthDiagnostics class."
        )
    return health_service


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


def _find_check(report, component: HealthComponent):
    for check in getattr(report, "checks", []):
        if check.component is component:
            return check
    raise AssertionError(f"missing {component.value} check")


def _healthy_catalog() -> ingestion_ports.SourceCatalog:
    return ingestion_ports.SourceCatalog(
        version=3,
        updated_at=_utc(2025, 1, 3, 12, 0),
        sources=[
            ingestion_ports.SourceRecord(
                alias="man-pages",
                type=ingestion_ports.SourceType.MAN,
                location="/usr/share/man",
                language="en",
                size_bytes=1024,
                last_updated=_utc(2025, 1, 3, 11, 0),
                status=ingestion_ports.SourceStatus.ACTIVE,
                checksum="sha256:man",
            )
        ],
        snapshots=[ingestion_ports.SourceSnapshot(alias="man-pages", checksum="sha256:man")],
    )


def test_health_diagnostics_flags_quarantined_sources() -> None:
    """Any quarantined or error sources MUST surface as SOURCE_ACCESS failures."""

    health_service = _import_health_service_module()
    catalog = _healthy_catalog()
    catalog.sources.append(
        ingestion_ports.SourceRecord(
            alias="linuxwiki",
            type=ingestion_ports.SourceType.KIWIX,
            location="/data/linuxwiki_en.zim",
            language="en",
            size_bytes=4096,
            last_updated=_utc(2025, 1, 2, 8, 0),
            status=ingestion_ports.SourceStatus.QUARANTINED,
            checksum=None,
            notes="Checksum mismatch",
        )
    )

    diagnostics = health_service.HealthDiagnostics(
        catalog_loader=lambda: catalog,
        disk_probe=lambda: type("Disk", (), {"total_bytes": 1_000_000, "available_bytes": 900_000})(),
        dependency_checks=[],
        clock=lambda: _utc(2025, 1, 5, 9, 0),
    )

    report = diagnostics.evaluate()
    source_check = _find_check(report, HealthComponent.SOURCE_ACCESS)
    assert source_check.status is HealthStatus.FAIL
    assert "linuxwiki" in source_check.message
