"""Reindex duration performance helpers for SC-002 budgets."""

from collections.abc import Sequence
import datetime as dt
from typing import Any, Callable

from common.clock import utc_now
from common.helpers import normalise_metrics_history

from telemetry import trace_call

DEFAULT_REINDEX_BUDGET_MS = 600_000.0

Clock = Callable[[], dt.datetime]


def _recommendation(status: str, *, over_budget_ms: float) -> str:
    """Return remediation guidance based on the budget outcome."""

    if status == "pass":
        return "Reindex duration meets the SC-002 10-minute budget."

    minutes_over = over_budget_ms / 60_000 if over_budget_ms > 0 else 0.0
    return (
        "Reindex duration exceeds the SC-002 10-minute budget. "
        f"Reduce ingest batch sizes or parallelism (over by {over_budget_ms:.0f} ms / "
        f"{minutes_over:.2f} min)."
    )


@trace_call
def compute_p95(history: Sequence[int | float]) -> float:
    """Compute the P95 reindex duration for a set of samples.

    Args:
        history: Sequence of recorded reindex durations in milliseconds.

    Returns:
        Floating-point latency representing the 95th percentile duration.

    Raises:
        ValueError: If ``history`` is empty or contains negative samples.

    Example:
        >>> compute_p95([420_000, 480_000, 515_000])
        504999.99999999994
    """

    samples = normalise_metrics_history("reindex duration", history)
    if len(samples) == 1:
        return samples[0]

    rank = 0.95 * (len(samples) - 1)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(samples) - 1)
    fraction = rank - lower_index

    lower = samples[lower_index]
    upper = samples[upper_index]
    return lower + (upper - lower) * fraction


@trace_call
def within_budget(
    *,
    history: Sequence[int | float],
    budget_ms: int | float = DEFAULT_REINDEX_BUDGET_MS,
) -> bool:
    """Return whether the P95 reindex duration stays under the budget.

    Args:
        history: Recorded reindex durations in milliseconds.
        budget_ms: Budget threshold in milliseconds (default: 10 minutes).

    Returns:
        ``True`` when the computed P95 duration is less than or equal to the
        provided budget, otherwise ``False``.

    Raises:
        ValueError: If ``history`` is empty or contains negative samples.

    Example:
        >>> within_budget(history=[420_000, 515_000], budget_ms=600_000)
        True
    """

    percentile = compute_p95(history)
    return percentile <= float(budget_ms)


@trace_call
def describe(
    *,
    history: Sequence[int | float],
    budget_ms: int | float = DEFAULT_REINDEX_BUDGET_MS,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Summarise reindex performance relative to the SC-002 budget.

    Args:
        history: Recorded reindex durations in milliseconds.
        budget_ms: Budget threshold in milliseconds (default: 10 minutes).
        clock: Optional callable that returns the current timestamp, used to
            populate the ``recorded_at`` field for observability.

    Returns:
        Dictionary containing the computed p95 duration, budget, percent
        utilisation, recommendation text, and snapshot metadata.

    Raises:
        ValueError: If ``history`` is empty or contains negative samples.

    Example:
        >>> summary = describe(history=[420_000, 515_000], budget_ms=600_000)
        >>> summary["status"]
        'pass'
    """

    percentile = compute_p95(history)
    threshold = float(budget_ms)
    status = "pass" if percentile <= threshold else "fail"
    over_budget = max(0.0, percentile - threshold)
    percent_util = (percentile / threshold * 100.0) if threshold > 0 else 0.0
    timestamp = (clock or utc_now)()

    return {
        "status": status,
        "p95_ms": percentile,
        "budget_ms": threshold,
        "sample_count": len(history),
        "percent_utilization": percent_util,
        "over_budget_ms": over_budget,
        "recorded_at": timestamp.isoformat(),
        "recommendation": _recommendation(status, over_budget_ms=over_budget),
    }


__all__ = [
    "DEFAULT_REINDEX_BUDGET_MS",
    "compute_p95",
    "within_budget",
    "describe",
]
