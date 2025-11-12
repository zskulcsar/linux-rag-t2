"""Performance contracts for ragman query latency (SC-001)."""

from __future__ import annotations


def _import_query_metrics():
    try:
        from application import query_metrics  # type: ignore import-not-found
    except ImportError as exc:
        raise AssertionError(
            "application.query_metrics must provide latency tracking and SLO helpers."
        ) from exc
    return query_metrics


def test_latency_profile_meets_sc001_budget() -> None:
    """P95 latency must remain within the 8s budget for typical workloads."""

    query_metrics = _import_query_metrics()
    history = [5200, 6100, 4800, 7300, 5400, 6200, 5900, 5600, 6000, 7800]

    p95 = query_metrics.compute_p95(history)
    assert p95 <= 8000

    summary = query_metrics.describe(history=history, budget_ms=8000)
    assert summary["p95_ms"] == p95
    assert summary["budget_ms"] == 8000
    assert summary["status"] == "pass"
    assert query_metrics.within_latency_budget(history=history, budget_ms=8000) is True


def test_latency_exceeding_budget_reports_failure() -> None:
    """Exceeding the latency budget must trigger a failure recommendation."""

    query_metrics = _import_query_metrics()
    history = [5200, 6100, 4800, 9300, 10400, 8900, 8700]

    p95 = query_metrics.compute_p95(history)
    assert p95 > 8000

    summary = query_metrics.describe(history=history, budget_ms=8000)
    assert summary["status"] == "fail"
    assert summary["p95_ms"] == p95
    assert query_metrics.within_latency_budget(history=history, budget_ms=8000) is False
