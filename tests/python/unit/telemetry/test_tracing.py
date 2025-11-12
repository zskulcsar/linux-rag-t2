from __future__ import annotations

import inspect
import sys
import threading


from telemetry.tracing import TraceController


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


def test_trace_controller_enable_disable(monkeypatch) -> None:
    logger = CaptureLogger()
    settrace_calls: list[object] = []
    thread_settrace_calls: list[object] = []

    monkeypatch.setattr(sys, "gettrace", lambda: "previous-hook")
    monkeypatch.setattr(sys, "settrace", lambda func: settrace_calls.append(func))
    monkeypatch.setattr(
        threading, "settrace", lambda func: thread_settrace_calls.append(func)
    )

    controller = TraceController(logger=logger, include_modules=("tests.",))
    controller.enable()

    assert controller.is_enabled()
    assert settrace_calls[-1] == controller._trace
    assert thread_settrace_calls[-1] == controller._trace

    controller.disable()
    assert not controller.is_enabled()
    # Last call restores previous hook
    assert settrace_calls[-1] == "previous-hook"


def test_trace_controller_records_call() -> None:
    logger = CaptureLogger()
    controller = TraceController(logger=logger, include_modules=())

    frame = inspect.currentframe()
    assert frame is not None
    module_name = frame.f_globals.get("__name__", "")
    assert module_name

    controller._trace(frame, "call", None)

    debug_records = [record for record in logger.records if record["level"] == "debug"]
    assert debug_records
    record = debug_records[0]
    assert "TraceController._trace" in record["message"]
    assert record["kwargs"]["module"] == module_name
