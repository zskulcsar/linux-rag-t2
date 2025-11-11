"""Application orchestration for ragman query execution."""

from collections.abc import Callable
import dataclasses
import datetime as dt
import os
from pathlib import Path
from typing import Any

from services.rag_backend.ports import query as query_ports
from services.rag_backend.telemetry import trace_call, trace_section

DEFAULT_CONFIDENCE_THRESHOLD = 0.35
LOW_CONFIDENCE_GUIDANCE = (
    "Answer is below the confidence threshold. Please rephrase your query or refresh sources via ragadmin."
)
CONTEXT_TRUNCATION_MESSAGE = (
    "The retrieved context exceeded the configured token budget and was truncated. "
    "Please narrow your question or increase the --context-tokens limit."
)
_FATAL_CONTEXT_OVERFLOW_FACTOR = 2


def _default_clock() -> dt.datetime:
    """Return the current UTC time."""

    return dt.datetime.now(dt.timezone.utc)


def _default_config_path() -> Path:
    """Return the default ragcli presentation config path."""

    config_home = os.environ.get("XDG_CONFIG_HOME")
    if config_home:
        return Path(config_home) / "ragcli" / "config.yaml"
    return Path.home() / ".config" / "ragcli" / "config.yaml"


def _validate_confidence_threshold(candidate: float | None, *, default: float) -> float:
    """Validate a confidence threshold, falling back to the default when invalid."""

    if candidate is None:
        return default
    if 0.0 <= candidate <= 1.0:
        return candidate
    return default


def _parse_confidence_threshold(text: str, *, default: float) -> float:
    """Extract the configured confidence threshold from YAML-like text."""

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "confidence_threshold" not in stripped:
            continue
        parts = stripped.split(":", 1)
        if len(parts) != 2:
            continue
        value_text = parts[1].strip()
        try:
            candidate = float(value_text)
        except ValueError:
            continue
        return _validate_confidence_threshold(candidate, default=default)
    return default


def _load_confidence_threshold(config_path: Path, *, default: float) -> float:
    """Load the confidence threshold from the ragcli presentation config file."""

    if not config_path.exists():
        return default
    try:
        content = config_path.read_text(encoding="utf-8")
    except OSError:
        return default
    return _parse_confidence_threshold(content, default=default)


def _filtered_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    """Remove falsey values from a metadata mapping."""

    filtered = {key: value for key, value in metadata.items() if value not in {None, ""}}
    return filtered or None


class ContextBudgetExceeded(RuntimeError):
    """Raised when the retrieved context size cannot be reduced within limits."""


class QueryRunner:
    """Coordinate query execution across the application layer.

    Args:
        query_port: Port implementation responsible for retrieving and generating
            answers.
        clock: Callable returning the current UTC timestamp, used for telemetry
            metadata. Defaults to :func:`datetime.datetime.now`.
        confidence_threshold: Optional override for the minimum confidence. When
            omitted, the runner attempts to load the value from the ragcli
            presentation config and falls back to ``0.35`` if unavailable.
        presentation_config_path: Optional explicit path to the presentation
            config. Defaults to the XDG config location.
    """

    def __init__(
        self,
        *,
        query_port: query_ports.QueryPort,
        clock: Callable[[], dt.datetime] | None = None,
        confidence_threshold: float | None = None,
        presentation_config_path: Path | None = None,
    ) -> None:
        self._query_port = query_port
        self._clock = clock or _default_clock
        self._presentation_config_path = presentation_config_path or _default_config_path()
        resolved_threshold = _validate_confidence_threshold(
            confidence_threshold,
            default=DEFAULT_CONFIDENCE_THRESHOLD,
        )
        if confidence_threshold is None:
            resolved_threshold = _load_confidence_threshold(
                self._presentation_config_path,
                default=DEFAULT_CONFIDENCE_THRESHOLD,
            )
        self._confidence_threshold = resolved_threshold

    @property
    def confidence_threshold(self) -> float:
        """Return the effective confidence threshold."""

        return self._confidence_threshold

    @trace_call
    def run(
        self,
        *,
        question: str,
        conversation_id: str | None = None,
        max_context_tokens: int = 4096,
        retrieved_context_tokens: int | None = None,
        trace_id: str | None = None,
    ) -> query_ports.QueryResponse:
        """Execute the query flow and return the structured response.

        Args:
            question: Human-readable query text from the CLI.
            conversation_id: Optional identifier for conversational context.
            max_context_tokens: Maximum context tokens allowed for retrieval.
            retrieved_context_tokens: Tokens required by the retrieved context
                before truncation.
            trace_id: Correlation identifier propagated from the CLI transport.

        Returns:
            Structured :class:`QueryResponse` payload ready for transport.

        Raises:
            ContextBudgetExceeded: When the retrieved context cannot be truncated
                without exceeding the configured budget.
        """

        metadata = {
            "trace_id": trace_id,
            "question_preview": question[:120],
            "max_context_tokens": max_context_tokens,
            "retrieved_context_tokens": retrieved_context_tokens,
        }
        with trace_section("application.query.run", metadata=_filtered_metadata(metadata)) as section:
            context_truncated = False
            if (
                retrieved_context_tokens is not None
                and retrieved_context_tokens > max_context_tokens
            ):
                overflow = retrieved_context_tokens - max_context_tokens
                if overflow >= max_context_tokens * (_FATAL_CONTEXT_OVERFLOW_FACTOR - 1):
                    section.debug(
                        "context_budget_exceeded",
                        overflow_tokens=overflow,
                        retrieved_context_tokens=retrieved_context_tokens,
                        max_context_tokens=max_context_tokens,
                    )
                    raise ContextBudgetExceeded(
                        "retrieved context exceeds the allowed token budget; "
                        "reduce the question scope or increase --context-tokens"
                    )
                context_truncated = True
                section.debug(
                    "context_truncated",
                    overflow_tokens=overflow,
                    retrieved_context_tokens=retrieved_context_tokens,
                )

            request = query_ports.QueryRequest(
                question=question,
                conversation_id=conversation_id,
                max_context_tokens=max_context_tokens,
                trace_id=trace_id,
            )
            response = self._query_port.query(request)
            adjusted = dataclasses.replace(
                response,
                context_truncated=context_truncated,
                confidence_threshold=self._confidence_threshold,
            )

            if context_truncated:
                adjusted = dataclasses.replace(
                    adjusted,
                    summary=CONTEXT_TRUNCATION_MESSAGE,
                    steps=[],
                    references=[],
                    citations=[],
                    no_answer=True,
                    answer=None,
                )
            elif adjusted.confidence < self._confidence_threshold:
                adjusted = dataclasses.replace(
                    adjusted,
                    summary=LOW_CONFIDENCE_GUIDANCE,
                    steps=[],
                    references=[],
                    citations=[],
                    no_answer=True,
                    answer=None,
                )

            return adjusted


__all__ = [
    "ContextBudgetExceeded",
    "QueryRunner",
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "LOW_CONFIDENCE_GUIDANCE",
    "CONTEXT_TRUNCATION_MESSAGE",
]
