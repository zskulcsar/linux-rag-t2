"""Tracing utilities for optional deep observability mode."""


import inspect
import sys
import threading
from dataclasses import dataclass, field
from types import FrameType
from typing import TYPE_CHECKING, Any, Callable, Iterable, cast

if TYPE_CHECKING:  # pragma: no cover - typing-time import
    from _typeshed import TraceFunction as TypeshedTraceFunction
else:  # pragma: no cover - runtime stub
    TypeshedTraceFunction = Callable[[FrameType, str, Any], object]

from .logger import get_logger


def _default_filter(
    module_name: str, include: Iterable[str], exclude: Iterable[str]
) -> bool:
    """Determine whether a module should be traced.

    Args:
        module_name: Fully qualified module path.
        include: Iterable of prefixes that must match for tracing to occur. Empty
            iterables imply all modules are eligible.
        exclude: Iterable of prefixes that, when matched, skip tracing.

    Returns:
        ``True`` when the module satisfies inclusion rules and avoids exclusion
        rules; ``False`` otherwise.
    """

    if include:
        if not any(module_name.startswith(prefix) for prefix in include):
            return False
    if exclude:
        if any(module_name.startswith(prefix) for prefix in exclude):
            return False
    return True


TraceFunction = Callable[[FrameType, str, Any], "TraceFunction | None"]


@dataclass
class TraceController:
    """Manage activation of Python tracing hooks for deep observability sessions.

    Args:
        logger: Structured logger used to emit tracing diagnostics.
        include_modules: Tuple of module prefixes to allow during tracing.
        exclude_modules: Tuple of module prefixes to filter out during tracing.
    """

    logger: Any = field(
        default_factory=lambda: get_logger("rag_backend.telemetry.trace_controller")
    )
    include_modules: tuple[str, ...] = (
        "adapters",
        "application",
        "domain",
        "ports",
        "telemetry",
        "main",
    )
    exclude_modules: tuple[str, ...] = ("telemetry",)
    _enabled: bool = field(init=False, default=False)
    _previous_trace: TraceFunction | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def enable(self) -> None:
        """Enable tracing across the current interpreter.

        Subsequent function calls within included modules generate DEBUG logs
        until :meth:`disable` is invoked. Re-entrant calls are ignored.
        """

        with self._lock:
            if self._enabled:
                return
            self.logger.info(
                "TraceController.enable(self) :: start",
                include=list(self.include_modules) or None,
                exclude=list(self.exclude_modules) or None,
            )
            self._previous_trace = sys.gettrace()
            trace_callback = cast("TypeshedTraceFunction", self._trace)
            sys.settrace(trace_callback)  # type: ignore[arg-type]
            threading.settrace(trace_callback)  # type: ignore[arg-type]
            self._enabled = True

    def disable(self) -> None:
        """Disable tracing and restore any previous hooks.

        When tracing was not previously enabled, this method is a no-op.
        """

        with self._lock:
            if not self._enabled:
                return
            previous = cast("TypeshedTraceFunction | None", self._previous_trace)
            sys.settrace(previous)  # type: ignore[arg-type]
            threading.settrace(previous)  # type: ignore[arg-type]
            self.logger.info("TraceController.disable(self) :: complete")
            self._enabled = False
            self._previous_trace = None

    def is_enabled(self) -> bool:
        """Return whether tracing is currently enabled.

        Returns:
            ``True`` when tracing hooks are active; otherwise ``False``.
        """

        return self._enabled

    def _trace(self, frame: FrameType, event: str, arg: Any) -> TraceFunction | None:
        """Trace hook invoked by the Python interpreter.

        Args:
            frame: Current stack frame being executed.
            event: Interpreter event type such as ``"call"`` or ``"return"``.
            arg: Event-specific argument defined by the tracing API.

        Returns:
            A reference to this trace function so nested frames continue to
            receive callbacks.
        """

        if event != "call":
            return self._trace

        module_name = frame.f_globals.get("__name__", "")
        if not _default_filter(module_name, self.include_modules, self.exclude_modules):
            return self._trace

        code = frame.f_code
        func_name = code.co_name
        filename = code.co_filename
        lineno = frame.f_lineno
        info = inspect.getargvalues(frame)
        arguments = {}
        for name in info.args:
            value = info.locals.get(name, "<missing>")
            try:
                arguments[name] = repr(value)[:128]
            except Exception:  # pragma: no cover - defensive
                arguments[name] = f"<unreprable:{type(value).__name__}>"
        if info.varargs:
            arguments[f"*{info.varargs}"] = repr(info.locals.get(info.varargs))[:128]
        if info.keywords:
            arguments[f"**{info.keywords}"] = repr(info.locals.get(info.keywords))[:128]

        self.logger.debug(
            "TraceController._trace(frame, event, arg) :: call",
            module=module_name,
            function=func_name,
            filename=filename,
            lineno=lineno,
            arguments=arguments or None,
        )
        return self._trace


__all__ = ["TraceController"]
