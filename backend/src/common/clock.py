"""UTC clock utilities shared across backend services."""

import datetime as dt


def utc_now() -> dt.datetime:
    """Return the current UTC timestamp."""

    return dt.datetime.now(dt.timezone.utc)


__all__ = ["utc_now"]
