"""Port definitions for catalog and ingestion flows."""

import datetime as dt
import enum
from dataclasses import dataclass, field
from typing import Callable, Protocol


class SourceType(str, enum.Enum):
    """Supported source categories for ingestion."""

    MAN = "man"
    KIWIX = "kiwix"
    INFO = "info"


class SourceStatus(str, enum.Enum):
    """Lifecycle status for knowledge sources."""

    PENDING_VALIDATION = "pending_validation"
    ACTIVE = "active"
    QUARANTINED = "quarantined"
    ERROR = "error"


class IngestionStatus(str, enum.Enum):
    """Operational state for ingestion jobs."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class IngestionTrigger(str, enum.Enum):
    """Reason an ingestion job was initiated."""

    INIT = "init"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


@dataclass(frozen=True, slots=True)
class SourceCreateRequest:
    """Request payload for registering a new source."""

    type: SourceType
    location: str
    language: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SourceUpdateRequest:
    """Request payload for updating an existing source."""

    location: str | None = None
    notes: str | None = None
    language: str | None = None
    status: SourceStatus | None = None


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Canonical representation of a knowledge source."""

    alias: str
    type: SourceType
    location: str
    language: str
    size_bytes: int
    last_updated: dt.datetime
    status: SourceStatus
    checksum: str | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class SourceSnapshot:
    """Snapshot entry used for index builds."""

    alias: str
    checksum: str


@dataclass(frozen=True, slots=True)
class SourceCatalog:
    """Aggregated catalog of sources and active snapshots."""

    version: int
    updated_at: dt.datetime
    sources: list[SourceRecord] = field(default_factory=list)
    snapshots: list[SourceSnapshot] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class IngestionJob:
    """Ingestion job metadata emitted by the domain."""

    job_id: str
    source_alias: str
    status: IngestionStatus
    requested_at: dt.datetime
    started_at: dt.datetime | None = None
    completed_at: dt.datetime | None = None
    documents_processed: int = 0
    stage: str | None = None
    percent_complete: float | None = None
    error_message: str | None = None
    trigger: IngestionTrigger = IngestionTrigger.MANUAL


@dataclass(frozen=True, slots=True)
class SourceMutationResult:
    """Response payload returned from source mutations."""

    source: SourceRecord
    job: IngestionJob | None = None


@dataclass(frozen=True, slots=True)
class ReindexCallbacks:
    """Callback hooks invoked as reindex jobs progress."""

    on_progress: Callable[[IngestionJob], None] | None = None
    on_complete: Callable[[IngestionJob], None] | None = None


class IngestionPort(Protocol):
    """Protocol describing catalog and ingestion use cases."""

    def list_sources(self) -> SourceCatalog:
        """Return the current source catalog."""

    def create_source(self, request: SourceCreateRequest) -> SourceMutationResult:
        """Create a new source and optionally queue ingestion."""

    def update_source(
        self, alias: str, request: SourceUpdateRequest
    ) -> SourceMutationResult:
        """Update metadata for an existing source."""

    def remove_source(self, alias: str):
        """Remove a source from the catalog."""

    def start_reindex(
        self, trigger: IngestionTrigger, *, callbacks: ReindexCallbacks | None = None
    ) -> IngestionJob:
        """Queue a new ingestion job for the catalog."""


__all__ = [
    "IngestionPort",
    "SourceType",
    "SourceStatus",
    "IngestionStatus",
    "IngestionTrigger",
    "SourceCreateRequest",
    "SourceUpdateRequest",
    "SourceRecord",
    "SourceCatalog",
    "SourceMutationResult",
    "IngestionJob",
    "SourceSnapshot",
    "ReindexCallbacks",
]
