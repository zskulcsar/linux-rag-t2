"""Audit logging helpers."""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path
from typing import Any, Callable

from telemetry import trace_call
from .catalog import _default_data_dir

_LANGUAGE_PATTERN = re.compile(r"^[a-z]{2,8}(?:-[a-z0-9]{2,8})*$")
_ENGLISH = "en"
_MUTATION_ACTOR = "rag-backend"


class AuditLogger:
    """Append-only log writer emitting newline-delimited JSON entries.

    Example:
        >>> logger = AuditLogger()
        >>> logger.append({'action': 'source_add', 'status': 'success'})
    """

    @trace_call
    def __init__(
        self,
        *,
        log_path: Path | None = None,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        """Create a logger bound to the given path.

        Args:
            log_path: File path used for audit log writes. When ``None``, defaults
                to ``$XDG_DATA_HOME/ragcli/audit.log``.
            clock: Optional callable that returns the current timestamp. Primarily
                used to inject deterministic times during tests.
        """

        self._log_path = log_path or _default_data_dir() / "audit.log"
        self._clock = clock or (lambda: dt.datetime.now(dt.timezone.utc))

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

    @trace_call
    def log_mutation(
        self,
        *,
        action: str,
        alias: str,
        status: str,
        language: str,
        trace_id: str | None = None,
        details: str | None = None,
    ) -> None:
        """Record a catalog mutation with normalized language metadata.

        Args:
            action: Identifier describing the mutation (e.g. ``"source_add"``).
            alias: Target alias affected by the mutation.
            status: Outcome status (typically ``"success"`` or ``"failure"``).
            language: Declared ISO language code associated with the source.
            trace_id: Optional trace identifier propagated from the request.
            details: Optional free-form string describing additional context.

        Raises:
            ValueError: If ``language`` is blank or fails validation.
        """

        normalized_language = _normalize_language_code(language)
        entry: dict[str, Any] = {
            "timestamp": self._clock().isoformat(),
            "actor": _MUTATION_ACTOR,
            "action": action,
            "target": alias,
            "status": status,
            "language": normalized_language,
        }
        if trace_id:
            entry["trace_id"] = trace_id
        if details:
            entry["details"] = details
        if normalized_language != _ENGLISH:
            entry["warning"] = f"non_english_language:{normalized_language}"

        self.append(entry)


def _normalize_language_code(language: str) -> str:
    """Normalize and validate ISO language codes.

    Args:
        language: Input code provided by the caller.

    Returns:
        Lowercase ISO language string suitable for persistence.

    Raises:
        ValueError: If the value is empty or does not resemble an ISO code.
    """

    candidate = (language or "").strip().lower()
    if not candidate:
        raise ValueError("language must not be empty")
    if not _LANGUAGE_PATTERN.fullmatch(candidate):
        raise ValueError(f"language '{language}' is not a valid ISO code")
    return candidate


__all__ = ["AuditLogger"]
