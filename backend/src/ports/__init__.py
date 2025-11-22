"""Backend port protocols for hexagonal boundaries."""

from .health import HealthPort, HealthCheck, HealthReport, HealthStatus, HealthComponent
from .ingestion import (
    IngestionPort,
    SourceType,
    SourceStatus,
    IngestionStatus,
    IngestionTrigger,
    SourceCreateRequest,
    SourceUpdateRequest,
    SourceRecord,
    SourceCatalog,
    SourceMutationResult,
    IngestionJob,
    SourceSnapshot,
)
from .query import QueryPort, QueryRequest, QueryResponse, Reference, Citation

__all__ = [
    "HealthPort",
    "HealthCheck",
    "HealthReport",
    "HealthStatus",
    "HealthComponent",
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
    "QueryPort",
    "QueryRequest",
    "QueryResponse",
    "Reference",
    "Citation",
]
