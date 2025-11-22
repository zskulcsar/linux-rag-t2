"""Port definitions for health evaluation flows."""

import datetime as dt
import enum
from dataclasses import dataclass, field
from typing import Protocol


class HealthStatus(str, enum.Enum):
    """Aggregate health status for a component or overall system."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


class HealthComponent(str, enum.Enum):
    """Enumerated health components monitored by the backend."""

    INDEX_FRESHNESS = "index_freshness"
    SOURCE_ACCESS = "source_access"
    DISK_CAPACITY = "disk_capacity"
    OLLAMA = "ollama"
    WEAVIATE = "weaviate"
    PHOENIX = "phoenix"


@dataclass(frozen=True, slots=True)
class HealthCheck:
    """Component-level health check result."""

    component: HealthComponent
    status: HealthStatus
    message: str
    remediation: str | None = None
    timestamp: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    metrics: dict[str, int | float] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Aggregated health snapshot for the system."""

    status: HealthStatus
    checks: list[HealthCheck] = field(default_factory=list)
    generated_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class HealthPort(Protocol):
    """Protocol describing health evaluation operations."""

    def evaluate(self) -> HealthReport:
        """Return the current health snapshot."""


__all__ = [
    "HealthPort",
    "HealthStatus",
    "HealthComponent",
    "HealthCheck",
    "HealthReport",
]
