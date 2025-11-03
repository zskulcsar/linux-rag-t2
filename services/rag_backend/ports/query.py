"""Port definitions for executing query flows."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Reference:
    """Reference presented to CLI renderers."""

    label: str
    url: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class Citation:
    """Citation metadata supporting inline references."""

    alias: str
    document_ref: str
    excerpt: str | None = None


@dataclass(frozen=True, slots=True)
class QueryRequest:
    """Request payload accepted by the query application port."""

    question: str
    conversation_id: str | None = None
    max_context_tokens: int = 4096
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class QueryResponse:
    """Structured answer returned from the query port."""

    summary: str
    steps: list[str] = field(default_factory=list)
    references: list[Reference] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    confidence: float = 0.0
    trace_id: str = ""
    latency_ms: int = 0
    retrieval_latency_ms: int | None = None
    llm_latency_ms: int | None = None
    index_version: str | None = None
    answer: str | None = None
    no_answer: bool = False


class QueryPort(Protocol):
    """Protocol describing the query application entry point."""

    def query(self, request: QueryRequest) -> QueryResponse:
        """Execute a query request and return the structured response."""


__all__ = [
    "QueryPort",
    "QueryRequest",
    "QueryResponse",
    "Reference",
    "Citation",
]
