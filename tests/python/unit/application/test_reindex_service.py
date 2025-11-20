"""Unit tests for :mod:`application.reindex_service`."""

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from adapters.weaviate.client import Document
from application.reindex_service import ReindexService
from domain.models import ContentIndexVersion, IndexStatus
from ports.ingestion import (
    IngestionStatus,
    IngestionTrigger,
    SourceCatalog,
    SourceRecord,
    SourceSnapshot,
    SourceStatus,
    SourceType,
    ReindexCallbacks,
)


@dataclass
class _RecordingChunkBuilder:
    calls: list[str]
    documents: int

    def __call__(
        self,
        *,
        alias: str,
        checksum: str,
        location: Path,
        source_type: SourceType,
    ) -> list[Document]:
        self.calls.append(alias)
        return [
            Document(
                alias=alias,
                checksum=checksum,
                chunk_id=i,
                text=f"{alias}-chunk-{i}",
                source_type=source_type,
                language="en",
            )
            for i in range(self.documents)
        ]


@dataclass
class _RecordingStorage:
    catalog: SourceCatalog
    saved: list[SourceCatalog]

    def load(self) -> SourceCatalog:
        return self.catalog

    def save(self, catalog: SourceCatalog) -> None:
        self.saved.append(catalog)
        self.catalog = catalog


class _RecordingIndexWriter:
    def __init__(self) -> None:
        self.snapshots: list[ContentIndexVersion] = []

    def __call__(self, version: ContentIndexVersion) -> None:
        self.snapshots.append(version)


class _RecordingCallbacks:
    def __init__(self) -> None:
        self.progress: list[IngestionStatus] = []
        self.stages: list[str | None] = []
        self.completed: IngestionStatus | None = None

    def progress_hook(self, job) -> None:
        self.progress.append(job.status)
        self.stages.append(job.stage)

    def complete_hook(self, job) -> None:
        self.completed = job.status
        self.progress_hook(job)


def _build_catalog(
    tmp_path: Path,
    *,
    checksums: dict[str, str],
    snapshot_checksums: dict[str, str] | None = None,
) -> SourceCatalog:
    now = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
    sources: list[SourceRecord] = []
    snapshots: list[SourceSnapshot] = []
    for alias, checksum in checksums.items():
        location = tmp_path / f"{alias}.txt"
        location.write_text(alias, encoding="utf-8")
        sources.append(
            SourceRecord(
                alias=alias,
                type=SourceType.MAN,
                location=str(location),
                language="en",
                size_bytes=len(alias),
                last_updated=now,
                status=SourceStatus.ACTIVE,
                checksum=checksum,
            )
        )
        snapshot_value = (
            snapshot_checksums[alias]
            if snapshot_checksums and alias in snapshot_checksums
            else f"stale-{checksum}"
        )
        snapshots.append(SourceSnapshot(alias=alias, checksum=snapshot_value))
    return SourceCatalog(version=1, updated_at=now, sources=sources, snapshots=snapshots)


def _checksum_factory(checksum_map: dict[str, str]) -> Callable[[Path], str]:
    def _calculate(path: Path) -> str:
        return checksum_map[str(path)]

    return _calculate


def test_run_processes_sources_and_updates_catalog(tmp_path: Path) -> None:
    """`run()` should iterate sources sequentially and persist refreshed snapshots."""

    checksum_map = {
        "man-pages": "sha256:man-new",
        "info-pages": "sha256:info-new",
    }
    catalog = _build_catalog(
        tmp_path,
        checksums={
            "man-pages": "sha256:man-old",
            "info-pages": "sha256:info-old",
        },
        snapshot_checksums={
            "man-pages": "sha256:man-old",
            "info-pages": "sha256:info-old",
        },
    )
    storage = _RecordingStorage(catalog=catalog, saved=[])
    builder = _RecordingChunkBuilder(calls=[], documents=2)
    index_writer = _RecordingIndexWriter()
    callbacks = _RecordingCallbacks()
    clock = lambda: dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc)

    service = ReindexService(
        storage=storage,
        chunk_builder=builder,
        checksum_calculator=_checksum_factory(
            {
                str(tmp_path / "man-pages.txt"): checksum_map["man-pages"],
                str(tmp_path / "info-pages.txt"): checksum_map["info-pages"],
            }
        ),
        audit_logger=None,
        index_writer=index_writer,
        clock=clock,
        job_id_factory=lambda: "job-123",
    )

    job = service.run(
        IngestionTrigger.MANUAL,
        callbacks=ReindexCallbacks(
            on_progress=callbacks.progress_hook,
            on_complete=callbacks.complete_hook,
        ),
    )

    assert builder.calls == ["man-pages", "info-pages"]
    assert job.status is IngestionStatus.SUCCEEDED
    assert job.documents_processed == 4
    assert job.percent_complete == 100.0
    assert job.stage == "completed"
    assert callbacks.completed is IngestionStatus.SUCCEEDED
    assert callbacks.stages[:2] == ["preparing_index", "ingesting:man-pages"]
    assert "ingesting:info-pages" in callbacks.stages
    assert callbacks.stages[-1] == "completed"

    assert storage.saved, "catalog save was not invoked"
    saved_catalog = storage.saved[-1]
    assert saved_catalog.version == catalog.version + 1
    assert saved_catalog.snapshots == [
        SourceSnapshot(alias="man-pages", checksum="sha256:man-new"),
        SourceSnapshot(alias="info-pages", checksum="sha256:info-new"),
    ]

    assert index_writer.snapshots, "content index version was not recorded"
    version = index_writer.snapshots[-1]
    assert version.status is IndexStatus.READY
    assert version.trigger_job_id == job.job_id
    assert version.source_snapshot == [
        SourceSnapshot(alias="man-pages", checksum="sha256:man-new"),
        SourceSnapshot(alias="info-pages", checksum="sha256:info-new"),
    ]


def test_run_skips_sources_when_checksums_match(tmp_path: Path) -> None:
    """`run()` should skip chunk rebuilding when checksums match."""

    catalog = _build_catalog(
        tmp_path,
        checksums={
            "man-pages": "sha256:man-old",
            "info-pages": "sha256:info-same",
        },
        snapshot_checksums={
            "man-pages": "sha256:man-old",
            "info-pages": "sha256:info-same",
        },
    )
    storage = _RecordingStorage(catalog=catalog, saved=[])
    builder = _RecordingChunkBuilder(calls=[], documents=1)
    index_writer = _RecordingIndexWriter()
    callbacks = _RecordingCallbacks()

    service = ReindexService(
        storage=storage,
        chunk_builder=builder,
        checksum_calculator=_checksum_factory(
            {
                str(tmp_path / "man-pages.txt"): "sha256:man-new",
                str(tmp_path / "info-pages.txt"): "sha256:info-same",
            }
        ),
        audit_logger=None,
        index_writer=index_writer,
        clock=lambda: dt.datetime(2025, 1, 2, tzinfo=dt.timezone.utc),
        job_id_factory=lambda: "job-456",
    )

    job = service.run(
        IngestionTrigger.MANUAL,
        callbacks=ReindexCallbacks(
            on_progress=callbacks.progress_hook,
            on_complete=callbacks.complete_hook,
        ),
    )

    assert builder.calls == ["man-pages"]
    assert job.documents_processed == 1
    assert job.percent_complete == 100.0
    assert job.stage == "completed"
    assert any(stage == "skipping:info-pages" for stage in callbacks.stages)
    assert callbacks.completed is IngestionStatus.SUCCEEDED
    assert storage.saved[-1].snapshots == [
        SourceSnapshot(alias="man-pages", checksum="sha256:man-new"),
        SourceSnapshot(alias="info-pages", checksum="sha256:info-same"),
    ]
