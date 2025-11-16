"""Latency metrics helpers for ragman query performance budgets."""


from collections.abc import Sequence
import datetime as dt
from typing import Any, Callable

from common.clock import utc_now

from telemetry import trace_call

DEFAULT_LATENCY_BUDGET_MS = 8000.0

Clock = Callable[[], dt.datetime]


def _normalise_history(history: Sequence[int | float]) -> list[float]:
    """Return sorted latency samples as floats.

    Args:
        history: Sequence of recorded latencies in milliseconds.

    Returns:
        Sorted list of latency samples.

    Raises:
        ValueError: If the sequence is empty or contains negative values.
    """

    if not history:
        raise ValueError("latency history must not be empty")
    normalised = []
    for value in history:
        sample = float(value)
        if sample < 0:
            raise ValueError("latency samples must be non-negative")
        normalised.append(sample)
    return sorted(normalised)


@trace_call
def compute_p95(history: Sequence[int | float]) -> float:
    """Compute the 95th percentile latency for a history of samples.

    Args:
        history: Sequence of latency samples in milliseconds.

    Returns:
        The 95th percentile latency as a float.

    Raises:
        ValueError: If the history is empty or contains negative values.

    Example:
        >>> compute_p95([120.0, 240.0, 180.0])
        234.0
    """

    samples = _normalise_history(history)
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
def within_latency_budget(
    *,
    history: Sequence[int | float],
    budget_ms: int | float = DEFAULT_LATENCY_BUDGET_MS,
) -> bool:
    """Return whether the latency profile satisfies the budget.

    Args:
        history: Recorded latency samples in milliseconds.
        budget_ms: Maximum allowable p95 latency.

    Returns:
        ``True`` when the p95 latency is less than or equal to ``budget_ms``.

    Raises:
        ValueError: If the history is empty or contains negative values.

    Example:
        >>> within_latency_budget(history=[5000, 6400, 7200], budget_ms=8000)
        True
    """

    percentile = compute_p95(history)
    return percentile <= float(budget_ms)


@trace_call
def describe(
    *,
    history: Sequence[int | float],
    budget_ms: int | float = DEFAULT_LATENCY_BUDGET_MS,
    clock: Clock | None = None,
) -> dict[str, Any]:
    """Summarise latency performance versus the configured budget.

    Args:
        history: Recorded latency samples in milliseconds.
        budget_ms: Maximum allowable p95 latency.
        clock: Optional callable returning the current UTC timestamp; used to
            timestamp the summary payload.

    Returns:
        Dictionary containing the computed p95 latency, budget, status, and
        additional metadata for observability dashboards.

    Raises:
        ValueError: If the history is empty or contains negative values.

    Example:
        >>> summary = describe(history=[5200, 6100, 4800], budget_ms=8000)
        >>> summary["status"]
        'pass'
    """

    percentile = compute_p95(history)
    threshold = float(budget_ms)
    status = "pass" if percentile <= threshold else "fail"
    timestamp = (clock or utc_now)()

    return {
        "status": status,
        "p95_ms": percentile,
        "budget_ms": threshold,
        "sample_count": len(history),
        "recorded_at": timestamp.isoformat(),
        "over_budget_ms": max(0.0, percentile - threshold),
    }


__all__ = [
    "DEFAULT_LATENCY_BUDGET_MS",
    "compute_p95",
    "within_latency_budget",
    "describe",
]
