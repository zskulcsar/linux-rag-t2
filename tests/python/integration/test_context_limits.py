"""Context budget and truncation behaviour for query execution."""

import datetime as dt

import pytest

from ports import query as query_ports


def _import_query_runner():
    try:
        from application import query_runner  # type: ignore import-not-found
    except ImportError as exc:
        raise AssertionError(
            "application.query_runner must expose context budget enforcement "
            "for ragman queries."
        ) from exc
    return query_runner


class _PassthroughQueryPort(query_ports.QueryPort):
    """Echo the request into a low-confidence response for truncation tests."""

    def query(self, request: query_ports.QueryRequest) -> query_ports.QueryResponse:
        return query_ports.QueryResponse(
            summary="Context truncated response placeholder.",
            confidence=0.05,
            trace_id=request.trace_id or "",
            no_answer=True,
        )


def test_query_runner_raises_when_context_budget_exceeded() -> None:
    """Query execution must refuse to run when retrieved context exceeds the configured limit."""

    query_runner = _import_query_runner()
    budget_error = getattr(query_runner, "ContextBudgetExceeded", None)
    if budget_error is None:
        pytest.fail(
            "QueryRunner must define a ContextBudgetExceeded exception when context budget is exceeded."
        )

    runner = query_runner.QueryRunner(
        query_port=_PassthroughQueryPort(),
        clock=lambda: dt.datetime(2025, 1, 2, 10, 0, tzinfo=dt.timezone.utc),
        confidence_threshold=0.35,
    )

    with pytest.raises(budget_error):
        runner.run(
            question="List every POSIX command with usage examples.",
            conversation_id=None,
            max_context_tokens=2048,
            retrieved_context_tokens=8192,
            trace_id="context-budget-check",
        )


def test_query_runner_truncates_context_and_annotations() -> None:
    """Queries should report truncation metadata when forced to shrink the context."""

    query_runner = _import_query_runner()
    runner = query_runner.QueryRunner(
        query_port=_PassthroughQueryPort(),
        clock=lambda: dt.datetime(2025, 1, 2, 10, 15, tzinfo=dt.timezone.utc),
        confidence_threshold=0.35,
    )

    result = runner.run(
        question="Summarise systemd unit options in detail.",
        conversation_id="systemd",
        max_context_tokens=4096,
        retrieved_context_tokens=4500,
        trace_id="context-truncation",
    )

    assert result.no_answer is True
    assert "truncated" in result.summary.lower()
    assert result.confidence <= 0.35
