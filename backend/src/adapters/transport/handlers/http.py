"""HTTP helpers used by transport handlers."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable, Sequence, TypeVar

from .common import LOGGER

_RetryResult = TypeVar("_RetryResult")


class _UrllibHttpResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def json(self) -> Any:
        return json.loads(self._payload.decode("utf-8"))


class _UrllibHttpClient:
    def post(
        self, url: str, payload: dict[str, Any], timeout: float
    ) -> _UrllibHttpResponse:
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            LOGGER.warning(
                "factory.urllib_http_client(url) :: request_failed",
                url=url,
                status=exc.code,
                error=str(exc),
            )
            body = exc.read()
        return _UrllibHttpResponse(body)


def _retry_with_backoff(
    name: str,
    func: Callable[[], _RetryResult],
    delays: Sequence[float] | None = None,
) -> _RetryResult:
    schedule = list(delays or (0.5, 1.0, 2.0, 4.0, 8.0))
    attempts = len(schedule) + 1
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:
            last_error = exc
            LOGGER.warning(
                "factory.%s :: retrying", name, error=str(exc), attempt=attempt + 1
            )
            if attempt < len(schedule):
                time.sleep(schedule[attempt])
    if last_error:
        raise last_error
    raise RuntimeError(f"{name} failed without raising an exception")


def _http_get_json(url: str, *, timeout: float = 3.0) -> dict[str, Any]:
    _, body = _http_request(url, timeout=timeout)
    if not body:
        return {}
    return json.loads(body.decode("utf-8"))


def _http_request(url: str, *, timeout: float = 3.0) -> tuple[int, bytes]:
    request = urllib.request.Request(url)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read()


__all__ = [
    "_UrllibHttpClient",
    "_UrllibHttpResponse",
    "_http_get_json",
    "_http_request",
    "_retry_with_backoff",
]
