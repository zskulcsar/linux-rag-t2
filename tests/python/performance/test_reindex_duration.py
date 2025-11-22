"""Performance contracts for reindex duration (SC-002)."""

import pytest


def _import_reindex_metrics():
    try:
        from application import reindex_metrics  # type: ignore import-not-found
    except ImportError as exc:  # pragma: no cover - explicit failure guidance
        raise AssertionError(
            "application.reindex_metrics must provide helpers for evaluating "
            "reindex duration against the SC-002 10-minute budget."
        ) from exc

    for attr in ("compute_p95", "within_budget", "describe"):
        if not hasattr(reindex_metrics, attr):
            raise AssertionError(
                f"application.reindex_metrics is missing required helper '{attr}'."
            )
    return reindex_metrics


def test_reindex_duration_meets_sc002_budget() -> None:
    """P95 reindex duration MUST remain under 10 minutes."""

    metrics = _import_reindex_metrics()
    history = [420_000, 480_000, 515_000, 498_000, 505_000, 530_000]

    p95 = metrics.compute_p95(history)
    assert p95 < 600_000

    summary = metrics.describe(history=history, budget_ms=600_000)
    assert summary["status"] == "pass"
    assert summary["p95_ms"] == p95
    assert summary["budget_ms"] == 600_000
    assert pytest.approx(summary["percent_utilization"], rel=0.01) == (
        (p95 / 600_000) * 100
    )
    assert metrics.within_budget(history=history, budget_ms=600_000) is True


def test_reindex_duration_exceeding_budget_reports_failure() -> None:
    """Durations exceeding 10 minutes MUST fail with actionable guidance."""

    metrics = _import_reindex_metrics()
    history = [420_000, 480_000, 515_000, 612_000, 655_000, 701_000]

    p95 = metrics.compute_p95(history)
    assert p95 >= 600_000

    summary = metrics.describe(history=history, budget_ms=600_000)
    assert summary["status"] == "fail"
    assert summary["p95_ms"] == p95
    assert "reindex" in summary.get("recommendation", "").lower()
    assert metrics.within_budget(history=history, budget_ms=600_000) is False
