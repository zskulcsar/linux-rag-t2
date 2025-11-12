"""Audit logging helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from telemetry import trace_call
from .catalog import _default_data_dir


class AuditLogger:
    """Append-only log writer emitting newline-delimited JSON entries.

    Example:
        >>> logger = AuditLogger()
        >>> logger.append({'action': 'source_add', 'status': 'success'})
    """

    @trace_call
    def __init__(self, *, log_path: Path | None = None) -> None:
        """Create a logger bound to the given path.

        Args:
            log_path: File path used for audit log writes. When ``None``, defaults
                to ``$XDG_DATA_HOME/ragcli/audit.log``.
        """

        self._log_path = log_path or _default_data_dir() / "audit.log"

    @trace_call
    def append(self, entry: dict[str, Any]) -> None:
        """Append a structured audit entry.

        Args:
            entry: JSON-serializable payload describing the event.

        Example:
            >>> audit_logger.append({'action': 'init', 'status': 'success'})
        """

        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False))
            handle.write("\n")


__all__ = ["AuditLogger"]
