"""Domain services for query-related operations."""

from __future__ import annotations

import datetime as dt
from dataclasses import replace
from typing import Callable

from . import models

Clock = Callable[[], dt.datetime]


def _default_clock() -> dt.datetime:
    """Return the current UTC timestamp.

    Returns:
        A timezone-aware datetime representing now in UTC.
    """

    return dt.datetime.now(dt.timezone.utc)


class QueryService:
    """Coordinate index lifecycle and freshness rules for query flows.

    Args:
        clock: Callable that returns the current UTC timestamp. Defaults to
            :func:`datetime.datetime.now` with a UTC timezone.
        freshness_ttl: Duration that a built index remains fresh before being
            marked stale. Defaults to seven days.
    """

    def __init__(
        self, clock: Clock | None = None, freshness_ttl: dt.timedelta | None = None
    ) -> None:
        """Create a query service with optional clock and freshness override.

        Args:
            clock: Callable returning the current UTC time. When ``None``, the
                service uses :func:`_default_clock`.
            freshness_ttl: Duration that an index remains fresh. Defaults to a
                seven-day interval when unspecified.
        """

        self._clock = clock or _default_clock
        self._freshness_ttl = freshness_ttl or dt.timedelta(days=7)

    def mark_index_ready(
        self,
        *,
        version: models.ContentIndexVersion,
        document_count: int,
        size_bytes: int,
    ) -> models.ContentIndexVersion:
        """Transition a building index version to ready.

        Args:
            version: Index version currently in the ``BUILDING`` state.
            document_count: Total documents included in the index.
            size_bytes: Serialized size of the index on disk.

        Returns:
            An updated :class:`ContentIndexVersion` in the ``READY`` state.

        Raises:
            ValueError: If ``version`` is not in the ``BUILDING`` state.
        """

        if version.status is not models.IndexStatus.BUILDING:
            raise ValueError("index version must be in BUILDING state")

        now = self._clock()
        expires_at = now + self._freshness_ttl
        return replace(
            version,
            status=models.IndexStatus.READY,
            built_at=now,
            document_count=document_count,
            size_bytes=size_bytes,
            freshness_expires_at=expires_at,
        )

    def enforce_index_freshness(
        self,
        *,
        version: models.ContentIndexVersion,
        reference_time: dt.datetime | None = None,
    ) -> models.ContentIndexVersion:
        """Downgrade a ready index to stale when the freshness window expires.

        Args:
            version: Index version to evaluate.
            reference_time: Optional timestamp to compare against the freshness
                expiry. Defaults to the injected clock.

        Returns:
            Either the original ``version`` or a replacement with status set to
            :attr:`IndexStatus.STALE`.
        """

        if version.status is not models.IndexStatus.READY:
            return version

        if version.freshness_expires_at is None:
            return version

        pivot = reference_time or self._clock()
        if pivot >= version.freshness_expires_at:
            return replace(version, status=models.IndexStatus.STALE)
        return version


__all__ = ["QueryService"]
