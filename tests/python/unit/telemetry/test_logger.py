
import importlib
import logging
import sys
from typing import Any

import pytest

import telemetry.logger as logger_module


class DummyStdLogger:
    def __init__(self, name: str) -> None:
        self.name = name
        self.records: list[tuple[int, str]] = []

    def log(self, level: int, message: str, *args: Any, **kwargs: Any) -> None:
        self.records.append((level, message))

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        self.log(logging.DEBUG, message, *args, **kwargs)


def test_get_logger_falls_back_when_structlog_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure get_logger returns the fallback implementation when structlog is unavailable."""

    monkeypatch.setitem(sys.modules, "structlog", None)
    module = importlib.reload(logger_module)

    fallback_logger = DummyStdLogger("rag_backend.telemetry.example")
    root_logger = DummyStdLogger("rag_backend.telemetry.logger")
    original_get_logger = logging.getLogger

    def fake_get_logger(name: str | None = None):
        if name == "rag_backend.telemetry.logger":
            return root_logger
        if name == "rag_backend.telemetry.example":
            return fallback_logger
        return original_get_logger(name)

    monkeypatch.setattr(logging, "getLogger", fake_get_logger)

    logger = module.get_logger("rag_backend.telemetry.example")
    assert isinstance(logger, module._FallbackLogger)

    logger = logger.bind(request_id="abc123")
    logger.info("Test message", extra="payload")
    logger.debug("Debugging")
    logger.warning("Heads up")
    logger.error("Boom", code=500)

    info_records = [
        record for record in fallback_logger.records if record[0] == logging.INFO
    ]
    assert info_records, "expected INFO logs to be recorded"
    assert "context={'request_id': 'abc123', 'extra': 'payload'}" in info_records[0][1]
    # Ensure other convenience methods also execute without error.
    assert any("Heads up" in msg for _, msg in fallback_logger.records)
