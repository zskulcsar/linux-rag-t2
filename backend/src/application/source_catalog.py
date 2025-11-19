"""Application service for managing the source catalog life cycle."""

from collections.abc import Callable, Sequence
import datetime as dt
import itertools
import re
from pathlib import Path
from typing import Protocol

from common.clock import utc_now

from adapters.storage.audit_log import AuditLogger
from adapters.weaviate.client import Document
from ports import ingestion as ingestion_ports
from telemetry import trace_call, trace_section

DEFAULT_LANGUAGE = "en"
_ALIAS_SANITIZER = re.compile(r"[^a-z0-9]+")
_ALIAS_MAX_LENGTH = 31


class CatalogStorage(Protocol):
    """Protocol describing catalog persistence helpers."""

    def load(self) -> ingestion_ports.SourceCatalog:  # pragma: no cover - protocol
        """Return the persisted catalog snapshot."""

    def save(self, catalog: ingestion_ports.SourceCatalog) -> None:  # pragma: no cover
        """Persist the provided catalog snapshot."""


ChecksumCalculator = Callable[[Path], str]


class ChunkBuilder(Protocol):
    """Protocol describing semantic chunk construction for ingestion."""

    def __call__(
        self,
        *,
        alias: str,
        checksum: str,
        location: Path,
        source_type: ingestion_ports.SourceType,
    ) -> Sequence[Document]:  # pragma: no cover - protocol
        """Create semantic chunks for a source location.

        Args:
            alias: Generated source alias.
            checksum: Deterministic checksum derived from the source contents.
            location: Filesystem path to the source payload.
            source_type: Source type used for downstream tagging.

        Returns:
            Sequence of prepared :class:`Document` instances.
        """


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
        audit_logger: AuditLogger | None = None,
    ) -> None:
        """Create a catalog service composed of storage and chunk builders.

        Args:
            storage: Storage backend responsible for persistence.
            checksum_calculator: Callable that returns deterministic checksums.
            chunk_builder: Callable that produces semantic chunks for ingestion.
            clock: Optional UTC clock override.
            audit_logger: Optional audit sink for catalog mutations.
        """
        self._storage = storage
        self._checksum_calculator = checksum_calculator
        self._chunk_builder = chunk_builder
        self._clock = clock or utc_now
        self._audit = audit_logger

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

        updated_sources = sorted(catalog.sources + [record], key=lambda src: src.alias)
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
                alias=alias,
                checksum=checksum,
                location=location_path,
                source_type=record.type,
            )
            section.debug(
                "chunks_planned",
                alias=alias,
                checksum=checksum,
                document_count=len(documents),
            )

        self._log_mutation(
            action="source_add",
            alias=alias,
            language=record.language,
            details=f"location={record.location}",
        )

        return ingestion_ports.SourceMutationResult(source=record, job=None)

    @trace_call
    def update_source(
        self, alias: str, request: ingestion_ports.SourceUpdateRequest
    ) -> ingestion_ports.SourceMutationResult:
        """Update metadata for an existing knowledge source.

        Args:
            alias: Unique alias identifying the source to update.
            request: Mutation payload describing updated fields. Omitted fields
                retain their current values.

        Returns:
            SourceMutationResult containing the refreshed :class:`SourceRecord`.

        Raises:
            ValueError: If the alias does not exist in the catalog.

        Example:
            >>> service.update_source(
            ...     \"linuxwiki\",
            ...     ingestion_ports.SourceUpdateRequest(notes=\"Restored\"),
            ... ).source.notes
            'Restored'
        """

        catalog = self._storage.load()
        try:
            current = next(
                record for record in catalog.sources if record.alias == alias
            )
        except StopIteration as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"unknown source alias: {alias}") from exc

        now = self._clock()

        location_path: Path | None = None
        new_checksum = current.checksum
        size_bytes = current.size_bytes
        location_value = current.location

        if request.location:
            location_path = _resolve_location(request.location)
            new_checksum = self._checksum_calculator(location_path)
            size_bytes = _stat_size(location_path)
            location_value = str(location_path)

        language_value = (
            _default_language(request.language)
            if request.language is not None
            else current.language
        )
        status_value = request.status if request.status is not None else current.status
        notes_value = request.notes if request.notes is not None else current.notes

        updated_record = ingestion_ports.SourceRecord(
            alias=current.alias,
            type=current.type,
            location=location_value,
            language=language_value,
            size_bytes=size_bytes,
            last_updated=now,
            status=status_value,
            checksum=new_checksum,
            notes=notes_value,
        )

        updated_sources = []
        for record in catalog.sources:
            if record.alias == alias:
                updated_sources.append(updated_record)
            else:
                updated_sources.append(record)
        updated_sources.sort(key=lambda record: record.alias)

        updated_snapshots: list[ingestion_ports.SourceSnapshot] = []
        replaced = False
        snapshot_checksum = new_checksum or current.checksum or ""
        for snapshot in catalog.snapshots:
            if snapshot.alias == alias:
                updated_snapshots.append(
                    ingestion_ports.SourceSnapshot(
                        alias=alias, checksum=snapshot_checksum
                    )
                )
                replaced = True
            else:
                updated_snapshots.append(snapshot)
        if not replaced:
            updated_snapshots.append(
                ingestion_ports.SourceSnapshot(alias=alias, checksum=snapshot_checksum)
            )

        updated_catalog = ingestion_ports.SourceCatalog(
            version=catalog.version + 1,
            updated_at=now,
            sources=updated_sources,
            snapshots=updated_snapshots,
        )
        self._storage.save(updated_catalog)

        if location_path is not None:
            with trace_section(
                "application.catalog.chunk_plan",
                metadata={"alias": alias},
            ) as section:
                documents = self._chunk_builder(
                    alias=alias,
                    checksum=new_checksum or "",
                    location=location_path,
                    source_type=updated_record.type,
                )
                section.debug(
                    "chunks_planned",
                    alias=alias,
                    checksum=new_checksum,
                    document_count=len(documents),
                )

        updated_fields = []
        if request.location:
            updated_fields.append("location")
        if request.language is not None:
            updated_fields.append("language")
        if request.status is not None:
            updated_fields.append("status")
        if request.notes is not None:
            updated_fields.append("notes")
        detail_value = (
            f"updated_fields={','.join(updated_fields)}" if updated_fields else None
        )
        self._log_mutation(
            action="source_update",
            alias=alias,
            language=updated_record.language,
            details=detail_value,
        )

        return ingestion_ports.SourceMutationResult(source=updated_record, job=None)

    @trace_call
    def remove_source(
        self, alias: str, *, reason: str | None = None
    ) -> ingestion_ports.SourceMutationResult:
        """Quarantine a source and remove it from active snapshots.

        Args:
            alias: Source alias to quarantine.
            reason: Optional human-readable explanation recorded in the notes.

        Returns:
            SourceMutationResult containing the quarantined :class:`SourceRecord`.

        Raises:
            ValueError: If the alias is unknown.

        Example:
            >>> service.remove_source('linuxwiki', reason='Obsolete content').source.status
            <SourceStatus.QUARANTINED: 'quarantined'>
        """

        catalog = self._storage.load()
        try:
            current = next(
                record for record in catalog.sources if record.alias == alias
            )
        except StopIteration as exc:  # pragma: no cover - defensive guard
            raise ValueError(f"unknown source alias: {alias}") from exc

        now = self._clock()
        note_reason = reason or "Removed via ragadmin"
        notes_value = (
            f"{current.notes}\n{note_reason}" if current.notes else note_reason
        )
        updated_record = ingestion_ports.SourceRecord(
            alias=current.alias,
            type=current.type,
            location=current.location,
            language=current.language,
            size_bytes=current.size_bytes,
            last_updated=now,
            status=ingestion_ports.SourceStatus.QUARANTINED,
            checksum=current.checksum,
            notes=notes_value,
        )

        updated_sources = []
        for record in catalog.sources:
            updated_sources.append(updated_record if record.alias == alias else record)
        updated_sources.sort(key=lambda record: record.alias)

        updated_snapshots = [
            snapshot for snapshot in catalog.snapshots if snapshot.alias != alias
        ]

        updated_catalog = ingestion_ports.SourceCatalog(
            version=catalog.version + 1,
            updated_at=now,
            sources=updated_sources,
            snapshots=updated_snapshots,
        )
        self._storage.save(updated_catalog)

        removal_detail = f"reason={reason}" if reason else "reason=unspecified"
        self._log_mutation(
            action="source_remove",
            alias=alias,
            language=updated_record.language,
            details=removal_detail,
        )

        return ingestion_ports.SourceMutationResult(source=updated_record, job=None)

    def _log_mutation(
        self,
        *,
        action: str,
        alias: str,
        language: str,
        details: str | None = None,
    ) -> None:
        """Emit an audit entry when the logger dependency is configured."""

        if self._audit is None:
            return

        self._audit.log_mutation(
            action=action,
            alias=alias,
            status="success",
            language=language,
            details=details,
        )


__all__ = [
    "SourceCatalogService",
    "CatalogStorage",
    "ChecksumCalculator",
    "ChunkBuilder",
]
