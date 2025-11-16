import inspect
import sys
import threading


from telemetry.tracing import TraceController, _default_filter


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


def test_default_filter_honours_include_and_exclude() -> None:
    assert not _default_filter("domain.service", include=("adapters",), exclude=())
    assert not _default_filter("telemetry.metrics", include=(), exclude=("telemetry",))
    assert _default_filter("application.service", include=("application",), exclude=())


def test_trace_controller_enable_is_idempotent(monkeypatch) -> None:
    logger = CaptureLogger()
    settrace_calls: list[object] = []
    monkeypatch.setattr(sys, "gettrace", lambda: None)
    monkeypatch.setattr(sys, "settrace", lambda func: settrace_calls.append(func))
    monkeypatch.setattr(threading, "settrace", lambda func: None)

    controller = TraceController(logger=logger, include_modules=("tests.",))
    controller.enable()
    controller.enable()

    assert settrace_calls.count(controller._trace) == 1

    controller.disable()
    controller.disable()
    assert not controller.is_enabled()


def test_trace_controller_traces_varargs_and_kwargs() -> None:
    logger = CaptureLogger()
    controller = TraceController(logger=logger, include_modules=())

    def _frame_factory(*args, **kwargs):
        frame = inspect.currentframe()
        assert frame is not None
        return frame

    frame = _frame_factory(1, 2, key="value")
    controller._trace(frame, "call", None)

    debug_records = [record for record in logger.records if record["level"] == "debug"]
    assert debug_records
    arguments = debug_records[0]["kwargs"]["arguments"] or {}
    assert arguments["*args"] == "(1, 2)"
    assert arguments["**kwargs"] == "{'key': 'value'}"


def test_trace_controller_records_named_arguments() -> None:
    logger = CaptureLogger()
    controller = TraceController(logger=logger, include_modules=())

    def with_args(a: int, b: int):
        frame = inspect.currentframe()
        assert frame is not None
        return frame

    frame = with_args(5, 10)
    controller._trace(frame, "call", None)

    arguments = logger.records[-1]["kwargs"]["arguments"]
    assert arguments["a"] == "5"
    assert arguments["b"] == "10"


def test_trace_controller_skips_non_matching_modules() -> None:
    logger = CaptureLogger()
    controller = TraceController(logger=logger, include_modules=("adapters.",))

    frame = inspect.currentframe()
    assert frame is not None

    controller._trace(frame, "call", None)
    assert not logger.records


def test_trace_controller_returns_same_trace_for_non_call_events() -> None:
    logger = CaptureLogger()
    controller = TraceController(logger=logger, include_modules=())

    frame = inspect.currentframe()
    assert frame is not None

    result = controller._trace(frame, "return", None)
    assert result == controller._trace
