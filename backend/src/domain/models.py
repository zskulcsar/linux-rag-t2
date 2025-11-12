"""Domain model types shared across services."""

from dataclasses import dataclass, field
import datetime as dt
import enum
from typing import List, Optional

from ports.ingestion import (
    IngestionJob as PortIngestionJob,
    IngestionStatus as PortIngestionStatus,
    IngestionTrigger as PortIngestionTrigger,
    SourceCatalog as PortSourceCatalog,
    SourceRecord as PortSourceRecord,
    SourceSnapshot,
    SourceType,
)
from ports.ingestion import SourceStatus as PortSourceStatus


KnowledgeSourceStatus = PortSourceStatus

# Expose ingestion-related enumerations for tests and services.
SourceStatus = PortSourceStatus
IngestionStatus = PortIngestionStatus
IngestionTrigger = PortIngestionTrigger
SourceCatalog = PortSourceCatalog
SourceRecord = PortSourceRecord
IngestionJob = PortIngestionJob


@dataclass(frozen=True, slots=True)
class KnowledgeSource:
    """Domain representation of a knowledge source record."""

    alias: str
    type: SourceType
    location: str
    language: str
    size_bytes: int
    last_updated: dt.datetime
    status: KnowledgeSourceStatus
    checksum: Optional[str] = None
    notes: Optional[str] = None
    created_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )
    updated_at: dt.datetime = field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc)
    )


class IndexStatus(str, enum.Enum):
    """Status values for content index versions."""

    READY = "ready"
    STALE = "stale"
    BUILDING = "building"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ContentIndexVersion:
    """Domain representation of a content index snapshot."""

    index_id: str
    status: IndexStatus
    checksum: str
    source_snapshot: List[SourceSnapshot]
    size_bytes: int
    document_count: int
    trigger_job_id: str
    built_at: Optional[dt.datetime] = None
    freshness_expires_at: Optional[dt.datetime] = None
    retrieval_latency_ms: Optional[int] = None
    llm_latency_ms: Optional[int] = None


__all__ = [
    "KnowledgeSource",
    "KnowledgeSourceStatus",
    "SourceType",
    "SourceStatus",
    "IngestionStatus",
    "IngestionTrigger",
    "IngestionJob",
    "SourceCatalog",
    "SourceRecord",
    "SourceSnapshot",
    "IndexStatus",
    "ContentIndexVersion",
]
