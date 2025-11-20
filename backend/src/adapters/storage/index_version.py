"""Persistence helpers for content index versions."""

import json
import datetime as dt
from pathlib import Path
from typing import Any

from domain.models import ContentIndexVersion, IndexStatus
from ports.ingestion import SourceSnapshot
from telemetry import trace_call, trace_section

from .catalog import _default_data_dir


def _encode_datetime(value: dt.datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(dt.timezone.utc).isoformat()


def _encode_snapshot(snapshot: SourceSnapshot) -> dict[str, Any]:
    return {"alias": snapshot.alias, "checksum": snapshot.checksum}


def _encode_index_version(version: ContentIndexVersion) -> dict[str, Any]:
    return {
        "index_id": version.index_id,
        "status": version.status.value
        if isinstance(version.status, IndexStatus)
        else str(version.status),
        "checksum": version.checksum,
        "source_snapshot": [_encode_snapshot(snapshot) for snapshot in version.source_snapshot],
        "size_bytes": version.size_bytes,
        "document_count": version.document_count,
        "trigger_job_id": version.trigger_job_id,
        "built_at": _encode_datetime(version.built_at),
        "freshness_expires_at": _encode_datetime(version.freshness_expires_at),
        "retrieval_latency_ms": version.retrieval_latency_ms,
        "llm_latency_ms": version.llm_latency_ms,
    }


class ContentIndexStorage:
    """Persist :class:`ContentIndexVersion` snapshots to disk."""

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        filename: str = "index_version.json",
    ) -> None:
        self._base_dir = base_dir or _default_data_dir()
        self._path = self._base_dir / filename

    @trace_call
    def save(self, version: ContentIndexVersion) -> None:
        """Persist a content index version alongside the catalog metadata."""

        metadata = {"path": str(self._path), "index_id": version.index_id}
        with trace_section("catalog.index_version.save", metadata=metadata):
            self._base_dir.mkdir(parents=True, exist_ok=True)
            payload = _encode_index_version(version)
            temp_path = self._base_dir / f".{self._path.name}.tmp"
            temp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            temp_path.replace(self._path)


__all__ = ["ContentIndexStorage"]
