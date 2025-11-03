from __future__ import annotations

import pytest

from services.rag_backend.telemetry.decorators import trace_call


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
