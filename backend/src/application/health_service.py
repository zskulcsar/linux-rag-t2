"""Aggregation helpers for ragadmin health diagnostics.

`HealthDiagnostics` coordinates disk probes, catalog inspections, and
dependency checks to produce a :class:`ports.health.HealthReport` that feeds
`/v1/admin/health` and the `ragadmin health` command.
"""

from collections.abc import Callable, Sequence
import datetime as dt
from dataclasses import dataclass
from typing import Any

from common.clock import utc_now

from ports import ingestion as ingestion_ports
from ports.health import (
    HealthCheck,
    HealthComponent,
    HealthReport,
    HealthStatus,
)
from telemetry import trace_call, trace_section

DiskProbe = Callable[[], Any]
CatalogLoader = Callable[[], ingestion_ports.SourceCatalog]
DependencyCheck = Callable[[], HealthCheck]
Clock = Callable[[], dt.datetime]

DEFAULT_DISK_WARN_RATIO = 0.10
DEFAULT_DISK_FAIL_RATIO = 0.08
DEFAULT_INDEX_WARN_AGE = dt.timedelta(days=30)


@dataclass(frozen=True, slots=True)
class DiskSnapshot:
    """Normalized disk statistics used for health scoring."""

    total_bytes: int
    available_bytes: int


class HealthDiagnostics:
    """Evaluate system health by composing catalog, disk, and dependency checks.

    Args:
        catalog_loader: Callable returning the current source catalog snapshot.
        disk_probe: Callable returning an object with ``total_bytes`` and
            ``available_bytes`` attributes (or dict keys).
        dependency_checks: Sequence of callables that return pre-built
            :class:`HealthCheck` instances for Ollama/Weaviate or other
            external dependencies.
        clock: Optional callable returning the current UTC timestamp.
        disk_warn_ratio: Free-space ratio that triggers a WARN status (default
            10%).
        disk_fail_ratio: Free-space ratio that triggers a FAIL status (default
            8%).
        index_warn_age: Maximum allowed age for the active index before a WARN
            is emitted (default 30 days).

    Example:
        >>> diagnostics = HealthDiagnostics(
        ...     catalog_loader=lambda: ingestion_ports.SourceCatalog(
        ...         version=1,
        ...         updated_at=dt.datetime.now(dt.timezone.utc),
        ...         sources=[],
        ...         snapshots=[],
        ...     ),
        ...     disk_probe=lambda: DiskSnapshot(total_bytes=100, available_bytes=50),
        ...     dependency_checks=[],
        ... )
        >>> isinstance(diagnostics.evaluate(), HealthReport)
        True
    """

    def __init__(
        self,
        *,
        catalog_loader: CatalogLoader,
        disk_probe: DiskProbe,
        dependency_checks: Sequence[DependencyCheck] | None = None,
        clock: Clock | None = None,
        disk_warn_ratio: float = DEFAULT_DISK_WARN_RATIO,
        disk_fail_ratio: float = DEFAULT_DISK_FAIL_RATIO,
        index_warn_age: dt.timedelta = DEFAULT_INDEX_WARN_AGE,
    ) -> None:
        self._catalog_loader = catalog_loader
        self._disk_probe = disk_probe
        self._dependency_checks = list(dependency_checks or [])
        self._clock = clock or utc_now
        self._disk_warn_ratio = max(0.0, min(1.0, disk_warn_ratio))
        self._disk_fail_ratio = max(0.0, min(self._disk_warn_ratio, disk_fail_ratio))
        self._index_warn_age = max(dt.timedelta(), index_warn_age)

    @trace_call
    def evaluate(self) -> HealthReport:
        """Return a consolidated health report."""

        catalog = self._catalog_loader()
        disk_stats = self._normalise_disk_stats(self._disk_probe())
        metadata = {
            "catalog_version": catalog.version,
            "source_count": len(catalog.sources),
            "snapshot_count": len(catalog.snapshots),
            "dependency_check_count": len(self._dependency_checks),
        }
        with trace_section("application.health.evaluate", metadata=metadata):
            checks: list[HealthCheck] = [
                self._score_disk_capacity(disk_stats),
                self._score_index_freshness(catalog),
                self._score_source_access(catalog),
            ]
            checks.extend(self._run_dependency_checks())
            status = self._aggregate_status(checks)
            return HealthReport(status=status, checks=checks, generated_at=self._clock())

    def _run_dependency_checks(self) -> list[HealthCheck]:
        results: list[HealthCheck] = []
        for check in self._dependency_checks:
            result = check()
            if not isinstance(result, HealthCheck):
                raise TypeError("dependency check must return a HealthCheck instance")
            results.append(result)
        return results

    def _score_disk_capacity(self, stats: DiskSnapshot) -> HealthCheck:
        if stats.total_bytes <= 0:
            message = "Unable to determine disk capacity; total bytes reported as zero."
            return HealthCheck(
                component=HealthComponent.DISK_CAPACITY,
                status=HealthStatus.FAIL,
                message=message,
                remediation="Verify mount points and ensure the ragcli data volume is accessible.",
                metrics={"total_bytes": stats.total_bytes, "available_bytes": stats.available_bytes},
            )

        available = min(stats.available_bytes, stats.total_bytes)
        ratio = available / stats.total_bytes
        percent_free = ratio * 100
        metrics: dict[str, int | float] = {
            "total_bytes": stats.total_bytes,
            "available_bytes": available,
            "percent_free": percent_free,
        }

        if ratio <= self._disk_fail_ratio:
            status = HealthStatus.FAIL
            remediation = "Delete temporary files or expand the partition."
        elif ratio <= self._disk_warn_ratio:
            status = HealthStatus.WARN
            remediation = "Delete temporary files or expand the partition."
        else:
            status = HealthStatus.PASS
            remediation = None

        message = f"{percent_free:.0f}% free space remaining"
        return HealthCheck(
            component=HealthComponent.DISK_CAPACITY,
            status=status,
            message=message,
            remediation=remediation,
            metrics=metrics,
        )

    def _score_index_freshness(
        self, catalog: ingestion_ports.SourceCatalog
    ) -> HealthCheck:
        now = self._clock()
        updated_at = catalog.updated_at
        age = now - updated_at
        if age < dt.timedelta():
            age = dt.timedelta()

        if age >= self._index_warn_age:
            status = HealthStatus.WARN
            remediation = "Run ragadmin reindex to refresh the knowledge index."
            message = (
                f"Active index is {int(age.days)} days old; refresh recommended."
            )
        else:
            status = HealthStatus.PASS
            remediation = None
            if age.days:
                message = f"Index updated {age.days} days ago."
            else:
                message = "Index recently updated."

        metrics: dict[str, int | float] = {
            "catalog_version": catalog.version,
            "age_seconds": int(age.total_seconds()),
            "snapshot_count": len(catalog.snapshots),
        }

        return HealthCheck(
            component=HealthComponent.INDEX_FRESHNESS,
            status=status,
            message=message,
            remediation=remediation,
            metrics=metrics,
        )

    def _score_source_access(
        self, catalog: ingestion_ports.SourceCatalog
    ) -> HealthCheck:
        failing_aliases: list[str] = []
        pending_aliases: list[str] = []
        for record in catalog.sources:
            record_status = self._normalise_source_status(record.status)
            if record_status in {
                ingestion_ports.SourceStatus.QUARANTINED,
                ingestion_ports.SourceStatus.ERROR,
            }:
                failing_aliases.append(record.alias)
            elif record_status is ingestion_ports.SourceStatus.PENDING_VALIDATION:
                pending_aliases.append(record.alias)

        metrics: dict[str, int | float] = {
            "active_sources": len(catalog.sources) - len(failing_aliases),
            "failing_sources": len(failing_aliases),
            "pending_sources": len(pending_aliases),
        }

        health_status: HealthStatus

        if failing_aliases:
            health_status = HealthStatus.FAIL
            message = (
                "Sources require remediation: "
                + ", ".join(sorted(failing_aliases))
            )
            remediation = "Inspect ragadmin sources list/update/remove to resolve quarantined entries."
        elif pending_aliases:
            health_status = HealthStatus.WARN
            message = (
                "Sources pending validation: "
                + ", ".join(sorted(pending_aliases))
            )
            remediation = "Run ragadmin reindex or complete validation for pending sources."
        elif not catalog.sources:
            health_status = HealthStatus.FAIL
            message = "No sources registered; ingestion must succeed before querying."
            remediation = "Use ragadmin init/sources add to register knowledge sources."
        else:
            health_status = HealthStatus.PASS
            message = "All sources accessible."
            remediation = None

        return HealthCheck(
            component=HealthComponent.SOURCE_ACCESS,
            status=health_status,
            message=message,
            remediation=remediation,
            metrics=metrics,
        )

    def _aggregate_status(self, checks: Sequence[HealthCheck]) -> HealthStatus:
        if any(check.status is HealthStatus.FAIL for check in checks):
            return HealthStatus.FAIL
        if any(check.status is HealthStatus.WARN for check in checks):
            return HealthStatus.WARN
        return HealthStatus.PASS

    def _normalise_disk_stats(self, payload: Any) -> DiskSnapshot:
        if payload is None:
            raise ValueError("disk probe returned no data")

        if isinstance(payload, DiskSnapshot):
            return payload

        total = self._extract_field(payload, "total_bytes")
        available = self._extract_field(payload, "available_bytes")
        total_bytes = int(total)
        available_bytes = int(available)
        if total_bytes < 0 or available_bytes < 0:
            raise ValueError("disk statistics must be non-negative")
        return DiskSnapshot(total_bytes=total_bytes, available_bytes=available_bytes)

    @staticmethod
    def _extract_field(payload: Any, field: str) -> Any:
        if hasattr(payload, field):
            return getattr(payload, field)
        if isinstance(payload, dict) and field in payload:
            return payload[field]
        raise AttributeError(f"disk probe payload missing {field}")

    @staticmethod
    def _normalise_source_status(
        status: ingestion_ports.SourceStatus | str,
    ) -> ingestion_ports.SourceStatus:
        if isinstance(status, ingestion_ports.SourceStatus):
            return status
        return ingestion_ports.SourceStatus(str(status))


__all__ = ["HealthDiagnostics", "DiskSnapshot"]
