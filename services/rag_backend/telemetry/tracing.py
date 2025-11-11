"""Tracing utilities for optional deep observability mode."""

from __future__ import annotations

import inspect
import sys
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from .logger import get_logger


def _default_filter(module_name: str, include: Iterable[str], exclude: Iterable[str]) -> bool:
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


@dataclass
class TraceController:
    """Manage activation of Python tracing hooks for deep observability sessions.

    Args:
        logger: Structured logger used to emit tracing diagnostics.
        include_modules: Tuple of module prefixes to allow during tracing.
        exclude_modules: Tuple of module prefixes to filter out during tracing.
    """

    logger: Any | None = None
    include_modules: tuple[str, ...] = ("services.rag_backend",)
    exclude_modules: tuple[str, ...] = ("services.rag_backend.telemetry",)
    _enabled: bool = field(init=False, default=False)
    _previous_trace: Callable | None = field(init=False, default=None)
    _lock: threading.Lock = field(init=False, default_factory=threading.Lock)

    def __post_init__(self) -> None:
        if self.logger is None:
            self.logger = get_logger("rag_backend.telemetry.trace_controller")

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
            sys.settrace(self._trace)
            threading.settrace(self._trace)
            self._enabled = True

    def disable(self) -> None:
        """Disable tracing and restore any previous hooks.

        When tracing was not previously enabled, this method is a no-op.
        """

        with self._lock:
            if not self._enabled:
                return
            sys.settrace(self._previous_trace)
            threading.settrace(self._previous_trace)
            self.logger.info("TraceController.disable(self) :: complete")
            self._enabled = False
            self._previous_trace = None

    def is_enabled(self) -> bool:
        """Return whether tracing is currently enabled.

        Returns:
            ``True`` when tracing hooks are active; otherwise ``False``.
        """

        return self._enabled

    def _trace(self, frame, event: str, arg):
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
