"""Quarantine operations for corrupted knowledge sources."""

import datetime as dt
from dataclasses import replace
from typing import Callable

from common.clock import utc_now

from adapters.storage.catalog import CatalogStorage
from ports.ingestion import SourceStatus
from telemetry import trace_call, trace_section


class AuditSinkProtocol:
    """Protocol describing the logger dependency for quarantine events."""

    def append(
        self, entry: dict[str, str]
    ) -> None:  # pragma: no cover - structural protocol
        ...


class SourceQuarantineManager:
    """Helper orchestrating quarantine transitions and audit logging.

    Example:
        >>> manager = SourceQuarantineManager(catalog_storage=storage, audit_logger=audit_logger)
        >>> manager.quarantine(alias='man-pages', reason='Checksum mismatch')
    """

    @trace_call
    def __init__(
        self,
        *,
        catalog_storage: CatalogStorage,
        audit_logger: AuditSinkProtocol,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        """Initialize the manager.

        Args:
            catalog_storage: Storage helper for catalog persistence.
            audit_logger: Structured logger for audit events.
            clock: Optional clock injection for deterministic timestamps.
        """

        self._storage = catalog_storage
        self._audit = audit_logger
        self._clock = clock or utc_now

    @trace_call
    def quarantine(self, *, alias: str, reason: str) -> None:
        """Mark the specified source as quarantined and append an audit entry.

        Args:
            alias: Source alias to quarantine.
            reason: Human-readable explanation for the quarantine action.

        Raises:
            ValueError: If the alias does not exist in the catalog.

        Example:
            >>> manager.quarantine(alias='info-pages', reason='Checksum mismatch')
        """

        metadata = {"alias": alias}
        with trace_section("catalog.quarantine", metadata=metadata) as section:
            catalog = self._storage.load()
            try:
                record = next(
                    source for source in catalog.sources if source.alias == alias
                )
            except StopIteration as exc:
                section.debug("alias_not_found")
                raise ValueError(f"unknown source alias '{alias}'") from exc

            timestamp = self._clock()
            updated_record = replace(
                record,
                status=SourceStatus.QUARANTINED,
                last_updated=timestamp,
                notes=(f"{record.notes}\n{reason}" if record.notes else reason),
            )
            section.debug("record_updated", timestamp=timestamp.isoformat())

            updated_sources = [
                updated_record if source.alias == alias else source
                for source in catalog.sources
            ]
            updated_catalog = replace(
                catalog,
                version=catalog.version + 1,
                updated_at=timestamp,
                sources=updated_sources,
            )
            self._storage.save(updated_catalog)
            self._audit.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "action": "source_quarantine",
                    "target": alias,
                    "status": "failure",
                    "message": reason,
                }
            )
            section.debug("catalog_persisted", version=updated_catalog.version)


__all__ = ["SourceQuarantineManager"]
