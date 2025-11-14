from __future__ import annotations

import pytest

from telemetry.decorators import trace_call


class CaptureLogger:
    def __init__(self) -> None:
        self.records: list[dict[str, object]] = []

    def _log(self, level: str, msg: str, *args, **kwargs) -> None:
        message = msg % args if args else msg
        self.records.append({"level": level, "message": message, "kwargs": kwargs})

    def info(self, msg: str, *args, **kwargs) -> None:
        self._log("info", msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        self._log("debug", msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        self._log("error", msg, *args, **kwargs)


def test_trace_call_records_entry_and_exit() -> None:
    logger = CaptureLogger()

    @trace_call(logger=logger)
    def sample_function(a, b=2):
        return a + b

    assert sample_function(1, b=3) == 4

    assert len(logger.records) == 2
    entry, exit_record = logger.records
    assert entry["level"] == "info"
    assert "sample_function :: enter" in entry["message"]
    assert entry["kwargs"]["arguments"]["a"] == "1"
    assert exit_record["message"].endswith(":: exit")


def test_trace_call_records_errors() -> None:
    logger = CaptureLogger()

    @trace_call(logger=logger)
    def explode() -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError):
        explode()

    assert logger.records[0]["message"].endswith(":: enter")
    assert logger.records[1]["level"] == "error"
    assert logger.records[1]["kwargs"]["error"] == "boom"


@pytest.mark.asyncio
async def test_trace_call_wraps_async_functions() -> None:
    """Ensure async callables log entry and exit when wrapped."""

    logger = CaptureLogger()

    @trace_call(logger=logger)
    async def sample_async(a: int) -> int:
        return a + 1

    result = await sample_async(2)
    assert result == 3

    entry, exit_record = logger.records
    assert entry["message"].endswith("sample_async :: enter")
    assert exit_record["message"].endswith("sample_async :: exit")


@pytest.mark.asyncio
async def test_trace_call_async_records_errors() -> None:
    """Ensure async wrapper logs error entries when exceptions bubble."""

    logger = CaptureLogger()

    @trace_call(logger=logger)
    async def boom() -> None:
        raise RuntimeError("kaboom")

    with pytest.raises(RuntimeError):
        await boom()

    assert logger.records[1]["level"] == "error"
    assert logger.records[1]["kwargs"]["error"] == "kaboom"
