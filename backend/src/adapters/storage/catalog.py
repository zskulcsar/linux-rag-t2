"""Filesystem-backed storage for the source catalog."""

import json
import os
from dataclasses import asdict
import datetime as dt
from pathlib import Path
from typing import Any

from ports.ingestion import (
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
)
from telemetry import trace_call, trace_section


def _encode_datetime(value: dt.datetime) -> str:
    """Encode a timezone-aware datetime to ISO format.

    Args:
        value: UTC-aware datetime to encode.

    Returns:
        ISO 8601 formatted string representing ``value``.

    Example:
        >>> _encode_datetime(dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc))
        '2025-01-01T00:00:00+00:00'
    """

    return value.astimezone(dt.timezone.utc).isoformat()


def _decode_datetime(value: str) -> dt.datetime:
    """Decode an ISO formatted string into a UTC datetime.

    Args:
        value: ISO 8601 formatted string.

    Returns:
        Timezone-aware datetime instance parsed from ``value``.

    Example:
        >>> _decode_datetime('2025-01-01T00:00:00+00:00').tzinfo is not None
        True
    """

    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _encode_record(record: SourceRecord) -> dict[str, Any]:
    """Encode a :class:`SourceRecord` into a JSON-serializable mapping.

    Args:
        record: Source record to serialise.

    Returns:
        Dictionary representation suitable for JSON encoding.
    """

    payload = asdict(record)
    payload["type"] = record.type.value
    payload["status"] = record.status.value
    payload["last_updated"] = _encode_datetime(record.last_updated)
    return payload


def _decode_record(payload: dict[str, Any]) -> SourceRecord:
    """Decode a JSON mapping into a :class:`SourceRecord` instance.

    Args:
        payload: Mapping obtained from serialised catalog data.

    Returns:
        A :class:`SourceRecord` created from ``payload``.
    """

    return SourceRecord(
        alias=payload["alias"],
        type=SourceType(payload["type"]),
        location=payload["location"],
        language=payload["language"],
        size_bytes=int(payload["size_bytes"]),
        last_updated=_decode_datetime(payload["last_updated"]),
        status=SourceStatus(payload["status"]),
        checksum=payload.get("checksum"),
        notes=payload.get("notes"),
    )


def _encode_snapshot(snapshot: SourceSnapshot) -> dict[str, Any]:
    """Encode a snapshot entry for JSON persistence.

    Args:
        snapshot: Snapshot instance to serialise.

    Returns:
        Dictionary containing serialised snapshot fields.
    """

    return {"alias": snapshot.alias, "checksum": snapshot.checksum}


def _decode_snapshot(payload: dict[str, Any]) -> SourceSnapshot:
    """Decode a snapshot entry from JSON.

    Args:
        payload: Mapping representing a snapshot entry.

    Returns:
        :class:`SourceSnapshot` reconstructed from ``payload``.
    """

    return SourceSnapshot(alias=payload["alias"], checksum=payload["checksum"])


def _encode_catalog(catalog: SourceCatalog) -> dict[str, Any]:
    """Encode the catalog and nested entries for disk persistence.

    Args:
        catalog: Source catalog instance to serialise.

    Returns:
        Dictionary representing the full catalog structure.
    """

    return {
        "version": catalog.version,
        "updated_at": _encode_datetime(catalog.updated_at),
        "sources": [_encode_record(record) for record in catalog.sources],
        "snapshots": [_encode_snapshot(snapshot) for snapshot in catalog.snapshots],
    }


def _decode_catalog(payload: dict[str, Any]) -> SourceCatalog:
    """Decode catalog payload into a :class:`SourceCatalog` instance.

    Args:
        payload: Mapping produced from serialised catalog JSON.

    Returns:
        :class:`SourceCatalog` reconstructed from ``payload``.
    """

    return SourceCatalog(
        version=int(payload["version"]),
        updated_at=_decode_datetime(payload["updated_at"]),
        sources=[_decode_record(data) for data in payload.get("sources", [])],
        snapshots=[_decode_snapshot(data) for data in payload.get("snapshots", [])],
    )


class CatalogStorage:
    """Persist the source catalog to disk.

    Example:
        >>> storage = CatalogStorage(base_dir=Path('/tmp/ragcli'))
        >>> storage.save(SourceCatalog(version=1, updated_at=dt.datetime.now(dt.timezone.utc)))
    """

    def __init__(
        self, *, base_dir: Path | None = None, filename: str = "catalog.json"
    ) -> None:
        """Create a new storage helper.

        Args:
            base_dir: Directory where catalog artifacts are stored. When ``None``,
                defaults to ``$XDG_DATA_HOME/ragcli`` with sensible fallbacks.
            filename: File name to persist catalog JSON under.
        """

        self._base_dir = base_dir or _default_data_dir()
        self._filename = filename
        self._path = self._base_dir / self._filename

    @trace_call
    def load(self) -> SourceCatalog:
        """Load the catalog from disk.

        Returns:
            Loaded :class:`SourceCatalog`, or an empty catalog when absent.

        Example:
            >>> catalog = storage.load()
        """

        if not self._path.exists():
            now = dt.datetime.now(dt.timezone.utc)
            return SourceCatalog(version=0, updated_at=now, sources=[], snapshots=[])

        payload = json.loads(self._path.read_text(encoding="utf-8"))
        return _decode_catalog(payload)

    @trace_call
    def save(self, catalog: SourceCatalog) -> None:
        """Persist the given catalog using an atomic write.

        Args:
            catalog: Catalog snapshot to write to disk.

        Example:
            >>> storage.save(catalog)
        """

        metadata = {"path": str(self._path), "version": catalog.version}
        with trace_section("catalog.save", metadata=metadata):
            self._base_dir.mkdir(parents=True, exist_ok=True)

            payload = _encode_catalog(catalog)
            temp_path = self._base_dir / f".{self._filename}.tmp"
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(self._path)


__all__ = ["CatalogStorage"]


def _default_data_dir() -> Path:
    """Return the default XDG data directory for ragcli.

    Returns:
        Path inside ``$XDG_DATA_HOME`` (or a fallback) dedicated to ragcli data.
    """

    data_home_env = os.environ.get("XDG_DATA_HOME")
    base_dir = (
        Path(data_home_env) if data_home_env else Path.home() / ".local" / "share"
    )
    return base_dir / "ragcli"
