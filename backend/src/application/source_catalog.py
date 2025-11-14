"""Application service for managing the source catalog life cycle."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import datetime as dt
import itertools
import re
from pathlib import Path
from typing import Protocol

from adapters.weaviate.client import Document
from ports import ingestion as ingestion_ports
from telemetry import trace_call, trace_section

DEFAULT_LANGUAGE = "en"
_ALIAS_SANITIZER = re.compile(r"[^a-z0-9]+")
_ALIAS_MAX_LENGTH = 31


class CatalogStorage(Protocol):
    """Protocol describing catalog persistence helpers."""

    def load(self) -> ingestion_ports.SourceCatalog:  # pragma: no cover - protocol
        ...

    def save(self, catalog: ingestion_ports.SourceCatalog) -> None:  # pragma: no cover
        ...


ChecksumCalculator = Callable[[Path], str]


class ChunkBuilder(Protocol):
    """Protocol describing semantic chunk construction for ingestion."""

    def __call__(
        self, *, alias: str, checksum: str, location: Path
    ) -> Sequence[Document]:  # pragma: no cover - protocol
        ...


def _default_clock() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _default_language(language: str | None) -> str:
    candidate = (language or DEFAULT_LANGUAGE).strip().lower()
    return candidate or DEFAULT_LANGUAGE


def _stat_size(path: Path) -> int:
    stat = path.stat()
    return int(stat.st_size)


def _resolve_location(location: str) -> Path:
    expanded = Path(location).expanduser()
    if not expanded.exists():
        raise FileNotFoundError(f"source location {expanded} does not exist")
    return expanded


def _slugify(value: str) -> str:
    slug = _ALIAS_SANITIZER.sub("-", value.lower()).strip("-")
    return slug or "source"


def _trim_alias(alias: str, *, suffix: str = "") -> str:
    """Trim alias to accommodate suffix within the max length."""

    budget = _ALIAS_MAX_LENGTH - len(suffix)
    trimmed = alias[:budget].rstrip("-")
    if not trimmed:
        trimmed = "source"
    return f"{trimmed}{suffix}"


def _generate_alias(
    *,
    location: Path,
    source_type: ingestion_ports.SourceType,
    existing_aliases: set[str],
) -> str:
    base_name = location.stem if location.is_file() else location.name
    slug_base = _slugify(base_name)
    if not slug_base[0].isalnum():
        slug_base = f"{source_type.value}-{slug_base}"
    slug_base = _trim_alias(slug_base)
    if slug_base not in existing_aliases:
        return slug_base

    for suffix in itertools.count(start=2):
        candidate = _trim_alias(slug_base, suffix=f"-{suffix}")
        if candidate not in existing_aliases:
            return candidate

    raise RuntimeError("unable to generate unique alias after exhausting suffixes")


class SourceCatalogService:
    """Coordinate catalog operations such as list and add flows.

    Args:
        storage: Persistence helper used to load and save catalog snapshots.
        checksum_calculator: Callable returning a deterministic checksum for the
            source location.
        chunk_builder: Callable that prepares semantic chunks for ingestion.
        clock: Optional callable producing the current UTC timestamp.

    Example:
        >>> service = SourceCatalogService(storage=storage, checksum_calculator=sha256, chunk_builder=builder)
        >>> catalog = service.list_sources()
        >>> result = service.create_source(
        ...     request=ingestion_ports.SourceCreateRequest(
        ...         type=ingestion_ports.SourceType.KIWIX,
        ...         location=\"/data/linuxwiki_en.zim\",
        ...     )
        ... )
        >>> result.source.alias
        'linuxwiki'
    """

    def __init__(
        self,
        *,
        storage: CatalogStorage,
        checksum_calculator: ChecksumCalculator,
        chunk_builder: ChunkBuilder,
        clock: Callable[[], dt.datetime] | None = None,
    ) -> None:
        self._storage = storage
        self._checksum_calculator = checksum_calculator
        self._chunk_builder = chunk_builder
        self._clock = clock or _default_clock

    @trace_call
    def list_sources(self) -> ingestion_ports.SourceCatalog:
        """Return the current catalog snapshot.

        Returns:
            SourceCatalog: Latest catalog loaded from the storage backend.

        Example:
            >>> service.list_sources().version >= 0
            True
        """

        return self._storage.load()

    @trace_call
    def create_source(
        self, request: ingestion_ports.SourceCreateRequest
    ) -> ingestion_ports.SourceMutationResult:
        """Register a new knowledge source and persist the catalog.

        Args:
            request: Parameters describing the new knowledge source location,
                type, and optional metadata such as language or notes.

        Returns:
            SourceMutationResult: Mutation result containing the newly
            registered :class:`SourceRecord`.

        Raises:
            FileNotFoundError: If the declared location does not exist.

        Example:
            >>> service.create_source(
            ...     ingestion_ports.SourceCreateRequest(
            ...         type=ingestion_ports.SourceType.KIWIX,
            ...         location=\"/data/linuxwiki.zim\",
            ...     )
            ... ).source.status
            <SourceStatus.PENDING_VALIDATION: 'pending_validation'>
        """

        location_path = _resolve_location(request.location)
        catalog = self._storage.load()
        existing_aliases = {record.alias for record in catalog.sources}
        alias = _generate_alias(
            location=location_path,
            source_type=request.type,
            existing_aliases=existing_aliases,
        )
        checksum = self._checksum_calculator(location_path)
        now = self._clock()
        language = _default_language(request.language)
        size_bytes = _stat_size(location_path)

        record = ingestion_ports.SourceRecord(
            alias=alias,
            type=request.type,
            location=str(location_path),
            language=language,
            size_bytes=size_bytes,
            last_updated=now,
            status=ingestion_ports.SourceStatus.PENDING_VALIDATION,
            checksum=checksum,
            notes=request.notes,
        )

        updated_sources = sorted(
            catalog.sources + [record], key=lambda src: src.alias
        )
        updated_snapshots = catalog.snapshots + [
            ingestion_ports.SourceSnapshot(alias=alias, checksum=checksum)
        ]
        updated_catalog = ingestion_ports.SourceCatalog(
            version=catalog.version + 1,
            updated_at=now,
            sources=updated_sources,
            snapshots=updated_snapshots,
        )
        self._storage.save(updated_catalog)

        with trace_section(
            "application.catalog.chunk_plan",
            metadata={"alias": alias},
        ) as section:
            documents = self._chunk_builder(
                alias=alias, checksum=checksum, location=location_path
            )
            section.debug(
                "chunks_planned",
                alias=alias,
                checksum=checksum,
                document_count=len(documents),
            )

        return ingestion_ports.SourceMutationResult(source=record, job=None)


__all__ = ["SourceCatalogService", "CatalogStorage", "ChecksumCalculator", "ChunkBuilder"]
