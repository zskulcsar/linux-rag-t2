# Reindex Streaming & Orchestration Design

## Transport behavior
- `/v1/index/reindex` remains a single Unix-socket request/response, but CatalogIngestionPort now streams multiple JSON frames.
- On request receipt, the handler issues an immediate `{"job": {...}}` frame with `status="running"` and `stage="preparing_index"`.
- Heavy work runs inside `asyncio.get_running_loop().run_in_executor(None, reindex_service.run, trigger)` so `_handle_connection` keeps servicing the socket.
- ReindexService emits job snapshots via callbacks; the transport drains them from an asyncio queue and writes each as a newline-delimited JSON frame.
- The connection closes only after a terminal snapshot with `status="succeeded"|"failed"` is sent.

## ReindexService flow
- New module `backend/src/application/reindex_service.py` depends on SourceCatalogService, chunk builder factory, checksum calculator, audit logger, telemetry helper, and CatalogStorage.
- `run(trigger)` loads the catalog snapshot, filters active sources, and initializes `IngestionJob` (job_id, trigger, timestamps, stage, percent, documents_processed).
- Sources are processed sequentially. For each alias:
  - `trace_section("application.reindex", alias=alias)` wraps tracing/logging/metrics.
  - Resolve path & recompute checksum. If unchanged vs snapshot, mark the source as `status="skipped"` and emit a progress update.
  - Otherwise call the chunk builder (`handlers/chunking/builder.py`) to regenerate documents and ingest into Weaviate; update metadata (size, checksum, last_updated) in the catalog snapshot.
  - After each alias, bump documents_processed, recompute percent complete, update `stage=f"ingesting:{alias}"`, and emit the snapshot.
- Any exception sets job status to failed, records `error_message`, logs an audit entry, emits a failure snapshot, and re-raises.

## Catalog/index persistence
- Reuse SourceCatalogService/CatalogStorage to persist both the catalog entries and ContentIndexVersion inside the same storage blob (minimal code change).
- After all sources succeed, increment catalog version/timestamps and build a new ContentIndexVersion (index_id, built_at, status ready, checksum snapshot, size/doc counts, trigger job id).
- Persist the combined snapshot, emit audit entry `action=admin_reindex status=success`, stamp job `completed_at` & `status="succeeded"`, and emit the final snapshot.
- Failed runs skip persistence but still emit final failure snapshot + audit entry.
