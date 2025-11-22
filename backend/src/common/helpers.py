"""Helper functions"""

from collections.abc import Sequence


def normalise_metrics_history(metric: str, history: Sequence[int | float]) -> list[float]:
    """Return sorted metric samples as floats.

    Args:
        metric: The name of the metric to be normalised.
        history: Sequence of recorded metrics in milliseconds.

    Returns:
        Sorted list of metric samples.

    Raises:
        ValueError: If the sequence is empty or contains negative values.
    """

    if not history:
        raise ValueError(f"{metric} history must not be empty")
    normalised = []
    for value in history:
        sample = float(value)
        if sample < 0:
            raise ValueError(f"{metric} samples must be non-negative")
        normalised.append(sample)
    return sorted(normalised)


__all__ = ["normalise_metrics_history"]