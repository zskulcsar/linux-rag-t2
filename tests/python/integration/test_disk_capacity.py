"""Disk-capacity specific tests for the health diagnostics service."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

import pytest

from ports import ingestion as ingestion_ports
from ports.health import HealthComponent, HealthStatus


def _import_health_service_module():
    try:
        from application import health_service  # type: ignore import-not-found
    except ImportError as exc:
        raise AssertionError(
            "application.health_service must define HealthDiagnostics to score disk checks."
        ) from exc
    if not hasattr(health_service, "HealthDiagnostics"):
        raise AssertionError(
            "application.health_service must expose a HealthDiagnostics class."
        )
    return health_service


def _utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


@dataclass
class _DiskStats:
    total_bytes: int
    available_bytes: int


def _find_check(report, component: HealthComponent):
    for check in getattr(report, "checks", []):
        if check.component is component:
            return check
    raise AssertionError(f"missing {component.value} check in health report")


@dataclass
class _CatalogFactory:
    version: int = 9

    def fresh(self) -> ingestion_ports.SourceCatalog:
        return ingestion_ports.SourceCatalog(
            version=self.version,
            updated_at=_utc(2025, 1, 3, 9, 0),
            sources=[
                ingestion_ports.SourceRecord(
                    alias="man-pages",
                    type=ingestion_ports.SourceType.MAN,
                    location="/usr/share/man",
                    language="en",
                    size_bytes=1024,
                    last_updated=_utc(2025, 1, 3, 8, 30),
                    status=ingestion_ports.SourceStatus.ACTIVE,
                    checksum="sha256:man",
                )
            ],
            snapshots=[ingestion_ports.SourceSnapshot(alias="man-pages", checksum="sha256:man")],
        )


@pytest.mark.parametrize(
    ("available_ratio", "expected"),
    [
        (0.11, HealthStatus.PASS),
        (0.09, HealthStatus.WARN),
        (0.07, HealthStatus.FAIL),
    ],
)
def test_disk_capacity_thresholds(available_ratio: float, expected: HealthStatus) -> None:
    """Health diagnostics MUST warn/fail when disk free space dips below documented thresholds."""

    health_service = _import_health_service_module()
    catalog = _CatalogFactory().fresh()
    total_bytes = 1_000_000_000
    available_bytes = int(total_bytes * available_ratio)

    diagnostics = health_service.HealthDiagnostics(
        catalog_loader=lambda: catalog,
        disk_probe=lambda: _DiskStats(total_bytes=total_bytes, available_bytes=available_bytes),
        dependency_checks=[],
        clock=lambda: _utc(2025, 1, 5, 12, 0),
    )

    report = diagnostics.evaluate()
    disk_check = _find_check(report, HealthComponent.DISK_CAPACITY)
    assert disk_check.status is expected
