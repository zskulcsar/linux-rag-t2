"""Init orchestration service for ragadmin bootstrap workflows.

The init service prepares required directories, ensures the presentation
config exists, invokes dependency probes, and seeds default knowledge
sources when missing.

Example:
    >>> import datetime as dt
    >>> from pathlib import Path
    >>> from ports import ingestion as ingestion_ports
    >>> class DummyConfigWriter:
    ...     def __init__(self) -> None:
    ...         self.payloads: list[str] = []
    ...     def write_default(self, content: str) -> None:
    ...         self.payloads.append(content)
    >>> class DummyIngestion(ingestion_ports.IngestionPort):
    ...     def __init__(self) -> None:
    ...         self.catalog = ingestion_ports.SourceCatalog(
    ...             version=0,
    ...             updated_at=dt.datetime.now(dt.timezone.utc),
    ...             sources=[],
    ...             snapshots=[],
    ...         )
    ...         self.created: list[ingestion_ports.SourceCreateRequest] = []
    ...     def list_sources(self) -> ingestion_ports.SourceCatalog:
    ...         return self.catalog
    ...     def create_source(
    ...         self, request: ingestion_ports.SourceCreateRequest
    ...     ) -> ingestion_ports.SourceMutationResult:
    ...         self.created.append(request)
    ...         record = ingestion_ports.SourceRecord(
    ...             alias=Path(request.location).stem,
    ...             type=request.type,
    ...             location=request.location,
    ...             language=request.language or "en",
    ...             size_bytes=0,
    ...             last_updated=dt.datetime.now(dt.timezone.utc),
    ...             status=ingestion_ports.SourceStatus.PENDING_VALIDATION,
    ...         )
    ...         self.catalog.sources.append(record)
    ...         self.catalog.version += 1
    ...         return ingestion_ports.SourceMutationResult(source=record)
    ...     def update_source(self, alias, request):
    ...         raise NotImplementedError
    ...     def remove_source(self, alias):
    ...         raise NotImplementedError
    ...     def start_reindex(self, trigger, *, force_rebuild=False, callbacks=None):
    ...         raise NotImplementedError
    >>> dummy = DummyIngestion()
    >>> service = InitService(
    ...     directory_targets=[Path(\"/tmp/ragcli/config\")],
    ...     config_writer=DummyConfigWriter(),
    ...     ingestion_port=dummy,
    ...     dependency_checks=[],
    ...     default_sources=[
    ...         ingestion_ports.SourceCreateRequest(
    ...             type=ingestion_ports.SourceType.MAN,
    ...             location=\"/usr/share/man\",
    ...             language=\"en\",
    ...         )
    ...     ],
    ... )
    >>> summary = service.bootstrap()
    >>> summary.catalog_version >= 0
    True
"""

from collections.abc import Callable, Sequence
import datetime as dt
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path
from typing import Any, Protocol

from common.clock import utc_now
from common.serializers import serialize_source_record

from ports import ingestion as ingestion_ports
from telemetry import trace_call, trace_section

DEFAULT_CONFIG_TEMPLATE = """ragman:
  confidence_threshold: 0.35
  presenter_default: markdown
ragadmin:
  output_default: table
"""

_SEED_ALIAS_BY_TYPE = {
    ingestion_ports.SourceType.MAN: "man-pages",
    ingestion_ports.SourceType.INFO: "info-pages",
}


class ConfigWriter(Protocol):
    """Protocol describing writability of the presentation config file."""

    def write_default(self, content: str) -> None:
        """Persist the default config when the file is missing."""


@dataclass(slots=True)
class InitSummary:
    """Summary payload returned from :meth:`InitService.bootstrap`.

    Args:
        catalog_version: Latest catalog version after bootstrapping.
        created_directories: Absolute paths ensured during bootstrap.
        seeded_sources: List of dictionaries describing sources seeded in this run.
        dependency_checks: Results emitted by dependency probes.

    Example:
        >>> summary = InitSummary(
        ...     catalog_version=1,
        ...     created_directories=[\"/tmp/ragcli/config\"],
        ...     seeded_sources=[{\"alias\": \"man-pages\"}],
        ...     dependency_checks=[{\"component\": \"ollama\", \"status\": \"pass\"}],
        ... )
        >>> summary.catalog_version
        1
    """

    catalog_version: int
    created_directories: list[str]
    seeded_sources: list[dict[str, Any]]
    dependency_checks: list[Any]


def _normalize_location(location: str) -> str:
    path = Path(location).expanduser()
    return str(path)


def _alias_for_request(request: ingestion_ports.SourceCreateRequest) -> str:
    override = _SEED_ALIAS_BY_TYPE.get(request.type)
    if override:
        return override
    candidate = Path(request.location).stem.replace("_", "-")
    return candidate or request.type.value


def _apply_alias_to_location(location: str, alias: str) -> str:
    path = Path(location)
    if path.stem == alias:
        return str(path)
    suffix = path.suffix
    replacement = f"{alias}{suffix}" if suffix else alias
    try:
        return str(path.with_name(replacement))
    except ValueError:
        return replacement


class InitService:
    """Coordinate init orchestration for ragadmin workflows.

    Args:
        directory_targets: Directories that must exist (config, data, runtime).
        config_writer: Helper that writes a default presentation config.
        ingestion_port: Port used to inspect and mutate the source catalog.
        dependency_checks: Callables that return dependency probe results.
        default_sources: Templates describing sources that should exist by default.
        clock: Optional UTC clock override for deterministic testing.

    Example:
        >>> service = InitService(
        ...     directory_targets=[Path(\"/tmp/ragcli/config\")],
        ...     config_writer=lambda content: None,  # type: ignore[arg-type]
        ...     ingestion_port=DummyIngestion(),    # see module example
        ...     dependency_checks=[],
        ...     default_sources=[],
        ... )
        >>> isinstance(service.bootstrap(), InitSummary)
        True
    """

    def __init__(
        self,
        *,
        directory_targets: Sequence[Path],
        config_writer: ConfigWriter,
        ingestion_port: ingestion_ports.IngestionPort,
        dependency_checks: Sequence[Callable[[], Any]] | None = None,
        default_sources: Sequence[ingestion_ports.SourceCreateRequest] | None = None,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        """Create a new init service.

        Args:
            directory_targets: Absolute directories that must exist after bootstrap.
            config_writer: Helper used to materialize default ragcli configs.
            ingestion_port: Port used for catalog inspection and mutation.
            dependency_checks: Optional iterable of dependency probe callables.
            default_sources: Optional seed templates for knowledge sources.
            clock: Optional deterministic clock override.
        """
        self._directory_targets = [Path(target) for target in directory_targets]
        self._config_writer = config_writer
        self._ingestion_port = ingestion_port
        self._dependency_checks = list(dependency_checks or [])
        self._default_sources = list(default_sources or [])
        self._clock = clock or utc_now

    @trace_call
    def bootstrap(self) -> InitSummary:
        """Execute the init orchestration steps and return a summary.

        Returns:
            InitSummary describing the directories ensured, any newly
            seeded sources, dependency probe results, and the resulting
            catalog version.

        Example:
            >>> summary = InitService(
            ...     directory_targets=[Path(\"/tmp/ragcli/config\")],
            ...     config_writer=lambda content: None,  # type: ignore[arg-type]
            ...     ingestion_port=DummyIngestion(),    # see module example
            ...     dependency_checks=[],
            ...     default_sources=[],
            ... ).bootstrap()
            >>> isinstance(summary, InitSummary)
            True
        """

        metadata = {
            "directory_count": len(self._directory_targets),
            "default_source_count": len(self._default_sources),
        }
        with trace_section("application.init.bootstrap", metadata=metadata):
            created_directories = self._prepare_directories()
            self._config_writer.write_default(DEFAULT_CONFIG_TEMPLATE)
            catalog = self._ingestion_port.list_sources()
            seeded_sources = self._seed_missing_sources(catalog)
            dependency_results = self._run_dependency_checks()
            final_catalog = self._ingestion_port.list_sources()
            return InitSummary(
                catalog_version=final_catalog.version,
                created_directories=created_directories,
                seeded_sources=seeded_sources,
                dependency_checks=dependency_results,
            )

    def _prepare_directories(self) -> list[str]:
        created: list[str] = []
        for target in self._directory_targets:
            if not target.exists():
                target.mkdir(parents=True, exist_ok=True)
            created.append(str(target))
        return created

    def _seed_missing_sources(
        self, catalog: ingestion_ports.SourceCatalog
    ) -> list[dict[str, Any]]:
        existing_aliases = {record.alias for record in catalog.sources}
        existing_locations = {
            _normalize_location(record.location) for record in catalog.sources
        }
        seeded: list[dict[str, Any]] = []

        for template in self._default_sources:
            alias = _alias_for_request(template)
            normalized_location = _normalize_location(template.location)
            if alias in existing_aliases or normalized_location in existing_locations:
                continue

            prepared_request = ingestion_ports.SourceCreateRequest(
                type=template.type,
                location=_apply_alias_to_location(template.location, alias),
                language=template.language,
                notes=template.notes,
            )
            record = self._invoke_seed_request(prepared_request, alias)
            if record is None:
                continue
            existing_aliases.add(record.alias)
            existing_locations.add(_normalize_location(record.location))
            seeded.append(serialize_source_record(record))

        return seeded

    def _run_dependency_checks(self) -> list[Any]:
        results: list[Any] = []
        for check in self._dependency_checks:
            try:
                results.append(check())
            except Exception as exc:  # pragma: no cover - defensive logging
                results.append({"status": "error", "message": str(exc)})
        return results

    def _invoke_seed_request(
        self,
        request: ingestion_ports.SourceCreateRequest,
        alias: str,
    ) -> ingestion_ports.SourceRecord | None:
        try:
            result = self._ingestion_port.create_source(request)
            return result.source
        except FrozenInstanceError:
            catalog = self._ingestion_port.list_sources()
            for record in catalog.sources:
                if record.alias == alias:
                    return record
            return None


__all__ = ["InitService", "InitSummary", "ConfigWriter"]
