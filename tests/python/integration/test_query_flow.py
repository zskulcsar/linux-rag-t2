"""Contract tests for the ragman query orchestration pipeline."""

from __future__ import annotations

import datetime as dt

import pytest

from services.rag_backend.ports import query as query_ports


def _import_query_runner():
    try:
        from services.rag_backend.application import query_runner  # type: ignore import-not-found
    except ImportError as exc:
        raise AssertionError(
            "services.rag_backend.application.query_runner must define a QueryRunner orchestrator "
            "that coordinates retrieval, generation, and presentation for ragman queries."
        ) from exc
    return query_runner


class _RecordingQueryPort(query_ports.QueryPort):
    """Capture requests passed through the query port for assertions."""

    def __init__(self, response: query_ports.QueryResponse) -> None:
        self._response = response
        self.requests: list[query_ports.QueryRequest] = []

    def query(self, request: query_ports.QueryRequest) -> query_ports.QueryResponse:
        self.requests.append(request)
        return self._response


def test_query_runner_returns_structured_response() -> None:
    """Ensure the query runner surfaces summary, steps, references, citations, and latency metrics."""

    query_runner = _import_query_runner()
    response = query_ports.QueryResponse(
        summary="Use chmod to modify file permissions.",
        steps=[
            "Inspect existing permissions with ls -l.",
            "Run chmod with the desired mode (e.g., 755).",
            "Re-run ls -l to confirm the change.",
        ],
        references=[
            query_ports.Reference(
                label="chmod(1)", url="man:chmod", notes="POSIX manual"
            ),
            query_ports.Reference(label="stat(1)"),
        ],
        citations=[
            query_ports.Citation(
                alias="man-pages",
                document_ref="chmod(1)",
                excerpt="chmod changes file mode bits.",
            ),
            query_ports.Citation(
                alias="man-pages",
                document_ref="stat(1)",
                excerpt="stat inspects file metadata.",
            ),
        ],
        confidence=0.81,
        trace_id="trace-query-runner",
        latency_ms=612,
        retrieval_latency_ms=220,
        llm_latency_ms=392,
        index_version="catalog/v1",
        answer="Detailed answer body",
        no_answer=False,
    )
    port = _RecordingQueryPort(response=response)
    runner = query_runner.QueryRunner(
        query_port=port,
        clock=lambda: dt.datetime(2025, 1, 2, 9, 15, tzinfo=dt.timezone.utc),
        confidence_threshold=0.35,
    )

    result = runner.run(
        question="How do I change file permissions?",
        conversation_id="session-123",
        max_context_tokens=4096,
        trace_id="cli-trace",
    )

    assert result.summary == response.summary
    assert result.steps == response.steps
    assert result.references == response.references
    assert result.citations == response.citations
    assert result.confidence == pytest.approx(0.81)
    assert result.latency_ms == 612
    assert result.retrieval_latency_ms == 220
    assert result.llm_latency_ms == 392
    assert result.index_version == "catalog/v1"
    assert result.answer == "Detailed answer body"
    assert result.no_answer is False
    assert port.requests, "expected the runner to invoke the query port"
    request = port.requests[0]
    assert request.question == "How do I change file permissions?"
    assert request.conversation_id == "session-123"
    assert request.max_context_tokens == 4096
    assert request.trace_id == "cli-trace"


def test_query_runner_promotes_low_confidence_to_no_answer() -> None:
    """Ensure answers below the confidence threshold trigger the fallback guidance."""

    query_runner = _import_query_runner()
    response = query_ports.QueryResponse(
        summary="This answer did not meet the confidence threshold.",
        steps=[],
        references=[],
        citations=[],
        confidence=0.12,
        trace_id="trace-low-confidence",
        latency_ms=480,
        index_version="catalog/v1",
        no_answer=True,
    )
    port = _RecordingQueryPort(response=response)
    runner = query_runner.QueryRunner(
        query_port=port,
        clock=lambda: dt.datetime(2025, 1, 2, 9, 30, tzinfo=dt.timezone.utc),
        confidence_threshold=0.35,
    )

    result = runner.run(
        question="How do I boot Windows with ragman?",
        conversation_id=None,
        max_context_tokens=4096,
        trace_id="cli-trace-low",
    )

    assert result.no_answer is True
    assert "confidence threshold" in result.summary.lower()
    assert result.confidence == pytest.approx(0.12)
    assert result.references == []
    assert result.citations == []
    assert port.requests[0].question == "How do I boot Windows with ragman?"
