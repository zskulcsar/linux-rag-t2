"""Utilities for instrumenting callable entry/exit logging."""

from __future__ import annotations

import inspect
from functools import wraps
from typing import Any, Callable, ParamSpec, TypeVar, overload

from .logger import get_logger

P = ParamSpec("P")
R = TypeVar("R")


def _serialise_arguments(bound_arguments: inspect.BoundArguments) -> dict[str, Any]:
    """Serialise positional and keyword arguments into a JSON-friendly mapping.

    Args:
        bound_arguments: Bound argument mapping produced by :func:`inspect.signature`.

    Returns:
        Dictionary mapping argument names to truncated repr() strings.
    """

    result: dict[str, Any] = {}
    for name, value in bound_arguments.arguments.items():
        try:
            text = repr(value)
        except Exception:  # pragma: no cover - extremely defensive
            text = f"<unreprable:{type(value).__name__}>"
        result[name] = text[:128]
    return result


@overload
def trace_call(func: Callable[P, R]) -> Callable[P, R]: ...


@overload
def trace_call(
    *,
    name: str | None = ...,
    logger: Any | None = ...,
) -> Callable[[Callable[P, R]], Callable[P, R]]: ...


def trace_call(
    func: Callable[P, R] | None = None,
    *,
    name: str | None = None,
    logger: Any | None = None,
) -> Callable[..., Any]:
    """Decorate a callable so entry, exit, and errors emit structured logs.

    This decorator is safe for both synchronous and asynchronous callables. It
    logs function entry with argument values (truncated `repr` output), emits an
    exit log on success, and logs an error when an exception is raised.

    Args:
        func: Callable being wrapped. When ``None`` the decorator is returned for later use.
        name: Optional override for the log prefix; defaults to
            ``<module>.<qualname>``.
        logger: Optional logger instance returned by :func:`get_logger`. When
            omitted, a module-qualified logger is created automatically.

    Returns:
        A callable that mirrors the wrapped function but adds logging side effects.
    """

    def decorator(inner: Callable[P, R]) -> Callable[P, R]:
        call_logger = logger or get_logger(f"{inner.__module__}.{inner.__qualname__}")
        call_name = name or f"{inner.__module__}.{inner.__qualname__}"
        signature = inspect.signature(inner)

        if inspect.iscoroutinefunction(inner):

            @wraps(inner)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
                bound = signature.bind_partial(*args, **kwargs)
                payload = _serialise_arguments(bound)
                call_logger.info("%s :: enter", call_name, arguments=payload)
                try:
                    result = await inner(*args, **kwargs)
                    call_logger.info("%s :: exit", call_name)
                    return result
                except Exception as exc:
                    call_logger.error(
                        "%s :: error", call_name, error=str(exc), arguments=payload
                    )
                    raise

            return async_wrapper

        @wraps(inner)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            bound = signature.bind_partial(*args, **kwargs)
            payload = _serialise_arguments(bound)
            call_logger.info("%s :: enter", call_name, arguments=payload)
            try:
                result = inner(*args, **kwargs)
                call_logger.info("%s :: exit", call_name)
                return result
            except Exception as exc:  # pragma: no cover - exercised via tests
                call_logger.error(
                    "%s :: error", call_name, error=str(exc), arguments=payload
                )
                raise

        return wrapper

    if func is not None:
        return decorator(func)

    return decorator


__all__ = ["trace_call"]
