"""Unit tests for observability telemetry helpers."""

from __future__ import annotations

import logging
import sys
from types import SimpleNamespace
from typing import Any, List

import pytest

from adapters.observability import telemetry


class _StubStructlog:
    """Collect configuration calls performed by configure_structlog."""

    def __init__(self) -> None:
        self.configure_calls: List[dict[str, Any]] = []
        self.bound_context: dict[str, Any] | None = None

        class _Processors:
            @staticmethod
            def add_log_level(event_dict):
                return event_dict

            @staticmethod
            def TimeStamper(fmt: str):
                return lambda event_dict: event_dict

            @staticmethod
            def add_logger_name(event_dict):
                return event_dict

            @staticmethod
            def add_service_name(event_dict):
                event_dict["service"] = "test"
                return event_dict

            @staticmethod
            def JSONRenderer():
                return lambda event_dict: event_dict

        class _ContextVars:
            def __init__(self, outer: "_StubStructlog") -> None:
                self._outer = outer

            @staticmethod
            def merge_contextvars(event_dict):
                return event_dict

            def bind_contextvars(self, **kwargs: Any) -> None:
                self._outer.bound_context = kwargs

        class _Common:
            @staticmethod
            def EventRenamer(new_key: str):
                return lambda event_dict: event_dict

        self.processors = _Processors()
        self.contextvars = _ContextVars(self)
        self.common = _Common()

    def configure(self, **kwargs: Any) -> None:
        self.configure_calls.append(kwargs)

    @staticmethod
    def make_filtering_bound_logger(log_level: int):
        return SimpleNamespace(log_level=log_level)

    @staticmethod
    def PrintLoggerFactory():
        return SimpleNamespace()


def test_configure_structlog_with_structlog(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure structlog configuration is performed when the library is available."""

    stub = _StubStructlog()
    monkeypatch.setitem(sys.modules, "structlog", stub)  # type: ignore[arg-type]
    configure_args: list[tuple[Any, ...]] = []

    def fake_basic_config(*args: Any, **kwargs: Any) -> None:
        configure_args.append((args, kwargs))

    monkeypatch.setattr(logging, "basicConfig", fake_basic_config)

    telemetry.configure_structlog(service_name="rag-backend", log_level=logging.DEBUG)

    assert configure_args, "logging.basicConfig must be invoked"
    assert stub.configure_calls, "structlog.configure must be invoked"
    call = stub.configure_calls[0]
    assert call["processors"], "processors should be populated"
    assert stub.bound_context == {"service": "rag-backend"}


def test_configure_structlog_without_structlog(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Ensure configure_structlog degrades gracefully when structlog is missing."""

    monkeypatch.delitem(sys.modules, "structlog", raising=False)
    import builtins

    original_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "structlog":
            raise ModuleNotFoundError
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with caplog.at_level(logging.WARNING):
        telemetry.configure_structlog(service_name="rag-backend")

    assert any("structlog_missing" in record.message for record in caplog.records)


class _StubPhoenix:
    """Track calls to phoenix.otel.register."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

        class _Otel:
            def __init__(self, parent: "_StubPhoenix") -> None:
                self._parent = parent

            def register(self, **kwargs: Any) -> None:
                self._parent.calls.append(kwargs)

        self.otel = _Otel(self)


def test_configure_phoenix_invokes_register(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure Phoenix register is called with the expected arguments."""

    stub = _StubPhoenix()
    monkeypatch.setitem(sys.modules, "phoenix", stub)  # type: ignore[arg-type]

    telemetry.configure_phoenix(
        service_name="rag-backend",
        endpoint="http://localhost:6006",
        instrumentors=("fastapi",),
    )

    assert stub.calls
    call = stub.calls[0]
    assert call["service_name"] == "rag-backend"
    assert call["endpoint"] == "http://localhost:6006"
    assert call["instrumentors"] == ("fastapi",)
    assert call["auto_instrument"] is True


def test_configure_phoenix_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure configure_phoenix raises when the phoenix package is missing."""

    monkeypatch.setitem(sys.modules, "phoenix", None)
    with pytest.raises(RuntimeError):
        telemetry.configure_phoenix(service_name="rag-backend")


def test_configure_phoenix_missing_otel_attribute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure a phoenix module without otel attribute raises a RuntimeError."""

    monkeypatch.setitem(sys.modules, "phoenix", SimpleNamespace())
    with pytest.raises(RuntimeError):
        telemetry.configure_phoenix(service_name="rag-backend")
