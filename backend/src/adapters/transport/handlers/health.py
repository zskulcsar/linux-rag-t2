"""Health check helpers for transport handlers."""

import shutil
from pathlib import Path
from typing import Callable

from adapters.storage.catalog import CatalogStorage
from application.handler_settings import HandlerSettings
from application.health_service import DiskSnapshot, HealthDiagnostics
from ports import HealthComponent, HealthPort, HealthStatus
from ports.health import HealthCheck

from .common import LOGGER, _using_fake_services
from .http import _http_get_json, _http_request, _retry_with_backoff


def _build_health_port(
    *,
    storage: CatalogStorage,
    settings: HandlerSettings,
) -> HealthPort:
    catalog_loader = storage.load
    base_dir = getattr(storage, "_base_dir", Path.home())

    dependency_checks: list[Callable[[], HealthCheck]] = [
        lambda: _ollama_health_check(settings),
        lambda: _weaviate_health_check(settings),
    ]
    if settings.phoenix_url or _using_fake_services():
        dependency_checks.append(lambda: _phoenix_health_check(settings))

    return HealthDiagnostics(
        catalog_loader=catalog_loader,
        disk_probe=lambda: _disk_snapshot(base_dir),
        dependency_checks=dependency_checks,
    )


def _ollama_health_check(settings: HandlerSettings) -> HealthCheck:
    component = HealthComponent.OLLAMA
    if _using_fake_services():
        return HealthCheck(
            component=component,
            status=HealthStatus.PASS,
            message="Ollama adapter running in fake mode.",
        )

    endpoint = settings.ollama_url.rstrip("/") + "/api/tags"

    def operation() -> dict[str, object]:
        return _http_get_json(endpoint)

    try:
        payload = _retry_with_backoff("ollama_health", operation)
    except Exception as exc:
        LOGGER.warning(
            "factory.ollama_health_check :: failure",
            error=str(exc),
            service_url=endpoint,
        )
        return HealthCheck(
            component=component,
            status=HealthStatus.FAIL,
            message="Unable to reach Ollama service.",
            remediation=f"Ensure Ollama is running locally at {settings.ollama_url}.",
        )

    model_count = 0
    if isinstance(payload, dict):
        models = payload.get("models")
        if isinstance(models, list):
            model_count = len(models)

    return HealthCheck(
        component=component,
        status=HealthStatus.PASS,
        message=f"Ollama responding with {model_count} models.",
        metrics={"model_count": model_count},
    )


def _weaviate_health_check(settings: HandlerSettings) -> HealthCheck:
    component = HealthComponent.WEAVIATE
    if _using_fake_services():
        return HealthCheck(
            component=component,
            status=HealthStatus.PASS,
            message="Weaviate adapter running in fake mode.",
        )

    endpoint = settings.weaviate_url.rstrip("/") + "/v1/.well-known/ready"

    def operation() -> dict[str, object]:
        return _http_get_json(endpoint)

    try:
        payload = _retry_with_backoff("weaviate_health", operation)
    except Exception as exc:
        LOGGER.warning(
            "factory.weaviate_health_check :: failure",
            error=str(exc),
            service_url=endpoint,
        )
        return HealthCheck(
            component=component,
            status=HealthStatus.FAIL,
            message="Unable to reach Weaviate service.",
            remediation=f"Ensure Weaviate is running locally at {settings.weaviate_url}.",
        )

    status_message = payload.get("status") if isinstance(payload, dict) else "ready"
    return HealthCheck(
        component=component,
        status=HealthStatus.PASS,
        message=f"Weaviate ready endpoint responded: {status_message}",
    )


def _phoenix_health_check(settings: HandlerSettings) -> HealthCheck:
    component = HealthComponent.PHOENIX
    if _using_fake_services():
        return HealthCheck(
            component=component,
            status=HealthStatus.PASS,
            message="Phoenix tracing running in fake mode.",
        )

    if not settings.phoenix_url:
        return HealthCheck(
            component=component,
            status=HealthStatus.PASS,
            message="Phoenix tracing not configured; set --phoenix-url to enable dashboards.",
        )

    base = settings.phoenix_url.rstrip("/")
    endpoints = [f"{base}/health", base]
    last_error: Exception | None = None
    for endpoint in endpoints:
        try:
            _retry_with_backoff(
                "phoenix_health",
                lambda: _http_request(endpoint),
            )
            return HealthCheck(
                component=component,
                status=HealthStatus.PASS,
                message=f"Phoenix reachable at {endpoint}.",
            )
        except Exception as exc:
            last_error = exc
            LOGGER.debug(
                "factory.phoenix_health_check :: attempt_failed",
                endpoint=endpoint,
                error=str(exc),
            )

    assert last_error is not None
    return HealthCheck(
        component=component,
        status=HealthStatus.FAIL,
        message="Unable to reach Phoenix tracing service.",
        remediation=f"Ensure Phoenix is running locally at {settings.phoenix_url}.",
    )


def _disk_snapshot(base_dir: Path) -> DiskSnapshot:
    usage = shutil.disk_usage(base_dir)
    return DiskSnapshot(total_bytes=usage.total, available_bytes=usage.free)


__all__ = [
    "_build_health_port",
    "_disk_snapshot",
    "_ollama_health_check",
    "_phoenix_health_check",
    "_weaviate_health_check",
]
