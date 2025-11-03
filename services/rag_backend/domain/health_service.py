"""Health evaluation services coordinating component checks."""

from __future__ import annotations

import datetime as dt
from typing import Callable, Iterable, List

from services.rag_backend.ports.health import HealthCheck, HealthComponent, HealthPort, HealthReport, HealthStatus

CheckFactory = Callable[[], HealthCheck]
Clock = Callable[[], dt.datetime]


def _default_clock() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class HealthService(HealthPort):
    """Aggregate health check factories into a single :class:`HealthPort`.

    Args:
        check_factories: Iterable of callables that produce :class:`HealthCheck`
            instances when invoked.
        clock: Callable supplying the current UTC timestamp. Defaults to
            :func:`datetime.datetime.now` with a UTC timezone.
    """

    def __init__(self, check_factories: Iterable[CheckFactory], clock: Clock | None = None) -> None:
        self._check_factories: List[CheckFactory] = list(check_factories)
        self._clock = clock or _default_clock

    def register(self, factory: CheckFactory) -> None:
        """Register an additional health check factory.

        Args:
            factory: Callable that returns a :class:`HealthCheck`.
        """

        self._check_factories.append(factory)

    def evaluate(self) -> HealthReport:
        """Execute all registered health checks and return an aggregated report.

        Returns:
            A :class:`HealthReport` containing component checks and an overall
            status derived from the individual results.
        """

        checks = [factory() for factory in self._check_factories]
        status = self._aggregate_status(checks)
        return HealthReport(status=status, checks=checks, generated_at=self._clock())

    @staticmethod
    def _aggregate_status(checks: List[HealthCheck]) -> HealthStatus:
        if any(check.status is HealthStatus.FAIL for check in checks):
            return HealthStatus.FAIL
        if any(check.status is HealthStatus.WARN for check in checks):
            return HealthStatus.WARN
        return HealthStatus.PASS


__all__ = ["HealthService"]
