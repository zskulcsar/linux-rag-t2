from __future__ import annotations

import pytest

from telemetry.sections import TraceSection


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


def test_trace_section_records_lifecycle() -> None:
    logger = CaptureLogger()

    with TraceSection(
        name="ingest", logger=logger, metadata={"alias": "docs"}
    ) as section:
        section.debug("chunk_loaded", chunk_id=1)

    assert logger.records[0]["message"] == "ingest :: start"
    assert logger.records[0]["kwargs"]["metadata"]["alias"] == "docs"
    assert logger.records[1]["level"] == "debug"
    assert "chunk_loaded" in logger.records[1]["message"]
    assert logger.records[1]["kwargs"]["metadata"]["chunk_id"] == 1
    assert logger.records[2]["message"] == "ingest :: complete"
    assert "duration_ms" in logger.records[2]["kwargs"]


def test_trace_section_records_errors() -> None:
    logger = CaptureLogger()

    with pytest.raises(RuntimeError):
        with TraceSection(name="ingest", logger=logger):
            raise RuntimeError("failure")

    assert logger.records[0]["message"] == "ingest :: start"
    assert logger.records[1]["level"] == "error"
    assert logger.records[1]["kwargs"]["error"] == "failure"
