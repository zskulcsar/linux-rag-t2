"""Integration tests covering init bootstrap and health diagnostics services."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from ports import ingestion as ingestion_ports
from ports.health import HealthCheck, HealthComponent, HealthStatus


def _import_init_service_module():
    try:
        from application import init_service  # type: ignore import-not-found
    except ImportError as exc:  # pragma: no cover - explicit failure message
        raise AssertionError(
            "application.init_service must define InitService to orchestrate "
            "directory bootstrap, dependency checks, and default source seeding."
        ) from exc

    if not hasattr(init_service, "InitService"):
        raise AssertionError(
            "application.init_service must expose an InitService class."
        )
    return init_service


def _import_health_service_module():
    try:
        from application import health_service  # type: ignore import-not-found
    except ImportError as exc:  # pragma: no cover - explicit failure message
        raise AssertionError(
            "application.health_service must define HealthDiagnostics to "
            "aggregate disk, dependency, and catalog checks."
        ) from exc

    if not hasattr(health_service, "HealthDiagnostics"):
        raise AssertionError(
            "application.health_service must expose a HealthDiagnostics class."
        )
    return health_service


def _utc(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0
) -> dt.datetime:
    return dt.datetime(year, month, day, hour, minute, tzinfo=dt.timezone.utc)


class _RecordingIngestionPort(ingestion_ports.IngestionPort):
    """Capture catalog interactions initiated by the init service."""

    def __init__(self, catalog: ingestion_ports.SourceCatalog) -> None:
        self._catalog = catalog
        self.created_requests: list[ingestion_ports.SourceCreateRequest] = []

    def list_sources(self) -> ingestion_ports.SourceCatalog:
        return self._catalog

    def create_source(
        self, request: ingestion_ports.SourceCreateRequest
    ) -> ingestion_ports.SourceMutationResult:
        alias = Path(request.location).stem.replace("_", "-")
        record = ingestion_ports.SourceRecord(
            alias=alias,
            type=request.type,
            location=request.location,
            language=request.language or "en",
            size_bytes=0,
            last_updated=_utc(2025, 1, 1, 12, 0),
            status=ingestion_ports.SourceStatus.PENDING_VALIDATION,
            checksum=None,
            notes=request.notes,
        )
        self.created_requests.append(request)
        self._catalog.sources.append(record)
        self._catalog.snapshots.append(
            ingestion_ports.SourceSnapshot(alias=alias, checksum="seeded-checksum")
        )
        self._catalog.version += 1
        return ingestion_ports.SourceMutationResult(source=record)

    def update_source(  # pragma: no cover - unused in tests
        self, alias: str, request: ingestion_ports.SourceUpdateRequest
    ) -> ingestion_ports.SourceMutationResult:
        raise NotImplementedError

    def remove_source(  # pragma: no cover - unused in tests
        self, alias: str
    ) -> ingestion_ports.SourceMutationResult:
        raise NotImplementedError

    def start_reindex(  # pragma: no cover - unused in tests
        self,
        trigger: ingestion_ports.IngestionTrigger,
        *,
        force_rebuild: bool = False,
        callbacks: ingestion_ports.ReindexCallbacks | None = None,
    ) -> ingestion_ports.IngestionJob:
        raise NotImplementedError


class _RecordingConfigWriter:
    """Capture config writes performed by the init service."""

    def __init__(self, target: Path) -> None:
        self.target = target
        self.writes: list[str] = []

    def write_default(self, content: str) -> None:
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(content, encoding="utf-8")
        self.writes.append(content)


@dataclass
class _DiskStats:
    total_bytes: int
    available_bytes: int


def _as_dict(result: Any, field: str) -> Any:
    if isinstance(result, dict):
        return result[field]
    return getattr(result, field)


def _find_check(report, component: HealthComponent) -> HealthCheck:
    checks: Iterable[HealthCheck] = report.checks if hasattr(report, "checks") else []
    for check in checks:
        if check.component is component:
            return check
    raise AssertionError(f"missing {component.value} check in report")


def test_init_service_bootstraps_directories_and_seeds_sources(tmp_path: Path) -> None:
    """InitService MUST create directories, seed missing sources, and report dependencies."""

    init_service = _import_init_service_module()

    config_dir = tmp_path / "cfg" / "ragcli"
    data_dir = tmp_path / "data" / "ragcli"
    runtime_dir = tmp_path / "runtime" / "ragcli"
    config_writer = _RecordingConfigWriter(config_dir / "config.yaml")

    catalog = ingestion_ports.SourceCatalog(
        version=5,
        updated_at=_utc(2025, 1, 1, 8, 0),
        sources=[
            ingestion_ports.SourceRecord(
                alias="man-pages",
                type=ingestion_ports.SourceType.MAN,
                location="/usr/share/man",
                language="en",
                size_bytes=512,
                last_updated=_utc(2025, 1, 1, 7, 30),
                status=ingestion_ports.SourceStatus.ACTIVE,
                checksum="sha256:man",
            )
        ],
        snapshots=[
            ingestion_ports.SourceSnapshot(alias="man-pages", checksum="sha256:man")
        ],
    )
    ingestion_port = _RecordingIngestionPort(catalog=catalog)
    dependency_checks = [
        lambda: {"component": "ollama", "status": "pass", "message": "ready"},
        lambda: {"component": "weaviate", "status": "pass", "message": "ready"},
    ]
    default_sources = [
        ingestion_ports.SourceCreateRequest(
            type=ingestion_ports.SourceType.MAN,
            location="/usr/share/man",
            language="en",
        ),
        ingestion_ports.SourceCreateRequest(
            type=ingestion_ports.SourceType.INFO,
            location="/usr/share/info",
            language="en",
        ),
    ]

    service = init_service.InitService(
        directory_targets=[config_dir, data_dir, runtime_dir],
        config_writer=config_writer,
        ingestion_port=ingestion_port,
        dependency_checks=dependency_checks,
        default_sources=default_sources,
        clock=lambda: _utc(2025, 1, 4, 12, 0),
    )

    summary = service.bootstrap()
    created_dirs = {Path(p) for p in _as_dict(summary, "created_directories")}

    assert config_dir in created_dirs
    assert data_dir in created_dirs
    assert runtime_dir in created_dirs
    assert config_writer.writes, "expected default config to be written"
    assert any(
        Path(req.location).stem == "info-pages"
        for req in ingestion_port.created_requests
    ), "missing seed call for info-pages"

    seeded_sources = _as_dict(summary, "seeded_sources")
    assert any(
        source.get("alias") == "info-pages"
        for source in seeded_sources
        if isinstance(source, dict)
    ), "summary must report newly seeded sources"
    dependency_summary = _as_dict(summary, "dependency_checks")
    assert len(dependency_summary) == 2
    assert _as_dict(summary, "catalog_version") >= 5


def test_health_diagnostics_merges_dependency_checks_with_system_probes(
    tmp_path: Path,
) -> None:
    """HealthDiagnostics MUST combine disk, catalog, and dependency checks into one report."""

    health_service = _import_health_service_module()

    catalog = ingestion_ports.SourceCatalog(
        version=7,
        updated_at=_utc(2025, 1, 2, 9, 0),
        sources=[
            ingestion_ports.SourceRecord(
                alias="man-pages",
                type=ingestion_ports.SourceType.MAN,
                location="/usr/share/man",
                language="en",
                size_bytes=1024,
                last_updated=_utc(2025, 1, 2, 8, 0),
                status=ingestion_ports.SourceStatus.ACTIVE,
                checksum="sha256:man",
            ),
            ingestion_ports.SourceRecord(
                alias="linuxwiki",
                type=ingestion_ports.SourceType.KIWIX,
                location="/data/linuxwiki_en.zim",
                language="en",
                size_bytes=2048,
                last_updated=_utc(2025, 1, 2, 7, 0),
                status=ingestion_ports.SourceStatus.ACTIVE,
                checksum="sha256:wiki",
            ),
        ],
        snapshots=[
            ingestion_ports.SourceSnapshot(alias="man-pages", checksum="sha256:man"),
            ingestion_ports.SourceSnapshot(alias="linuxwiki", checksum="sha256:wiki"),
        ],
    )

    dependencies: list[Callable[[], HealthCheck]] = [
        lambda: HealthCheck(
            component=HealthComponent.OLLAMA,
            status=HealthStatus.PASS,
            message="Ollama ready",
        ),
        lambda: HealthCheck(
            component=HealthComponent.WEAVIATE,
            status=HealthStatus.WARN,
            message="Weaviate lagging",
        ),
    ]

    diagnostics = health_service.HealthDiagnostics(
        catalog_loader=lambda: catalog,
        disk_probe=lambda: _DiskStats(
            total_bytes=1_000_000_000, available_bytes=600_000_000
        ),
        dependency_checks=dependencies,
        clock=lambda: _utc(2025, 1, 4, 12, 0),
    )

    report = diagnostics.evaluate()
    assert report.status is HealthStatus.WARN, (
        "warn dependency should elevate overall status"
    )

    disk_check = _find_check(report, HealthComponent.DISK_CAPACITY)
    assert disk_check.status is HealthStatus.PASS

    index_check = _find_check(report, HealthComponent.INDEX_FRESHNESS)
    assert index_check.status is HealthStatus.PASS

    source_check = _find_check(report, HealthComponent.SOURCE_ACCESS)
    assert source_check.status is HealthStatus.PASS

    weaviate_check = _find_check(report, HealthComponent.WEAVIATE)
    assert weaviate_check.status is HealthStatus.WARN
