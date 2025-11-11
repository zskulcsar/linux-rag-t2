# Weaviate Adapter Schema & Resilience Design

## Summary
The backend retains a single Weaviate `Document` class for all searchable chunks. Each object stores vectorized content along with scalar metadata (`source_alias`, `source_type`, `language`, `chunk_id`, `title`, `section`, `checksum`, `snippet_start`). Deterministic identifiers `<alias>:<checksum>:<chunk_id>` keep re-ingestion idempotent, and dynamic batching respects local resource limits. The adapter logs, traces, and exports metrics per alias/type to satisfy observability requirements without introducing deployment automation.

## Schema & Metadata Mapping
- **Class**: `Document`
  - Vectorized: `body`
  - Scalar properties (non-vectorized): `source_alias`, `source_type`, `language`, `chunk_id`, `title`, `section`, `checksum`, `snippet_start`, `language_mismatch`
  - Inverted index enabled on `source_alias`, `source_type`, `language`
- **Identifiers**: `<source_alias>:<checksum>:<chunk_id>`
  - Enables deterministic upserts and stale-vector cleanup
- **Validation**:
  - Ensure chunk metadata matches the source catalog entry before ingest
  - Set `language_mismatch` flag if chunk language differs from catalog

## Ingestion Workflow
1. Load source catalog entry; validate alias/type/language.
2. Chunk documents and enqueue into a dynamic batching loop (`client.batch.configure(dynamic=True)`).
3. Deduplicate pending batch on `chunk_id`; log and abort if conflicting metadata exists.
4. Upsert batch objects; on checksum mismatch, delete stale object and retry once.
5. Flush batches respecting a configurable max in-flight vector count derived from the 4 GiB memory target.
6. Emit structured logs and Phoenix spans per batch.

## Query Workflow
- Build Weaviate GraphQL with filters: `language == "en"`, `source_alias` in active aliases, optional `source_type` filters from CLI flags.
- Return scalar metadata alongside vector distance so the domain layer can compute confidence and render citations.
- Enforce FR-007 by halting queries when the domain marks the index stale; adapter surfaces backend errors with `IndexUnavailable` payloads.

## Observability & Metrics
- Logs: `WeaviateClient.ingest_batch :: completed` / `:: retrying` / `:: aborted` with alias/type/language/batch size/duration.
- Traces: Phoenix spans `ingest_batch`, `query_vectors` with custom attributes (`rag.alias`, `rag.type`, `rag.language`).
- Metrics:
  - Counters `rag.weaviate.ingested_docs{alias,type}`
  - Histograms `rag.weaviate.ingest_duration_ms`, `rag.weaviate.query_latency_ms`
- Health reporter pulls aggregated counts per alias/type for `ragadmin health`.

## Testing Strategy
- Integration tests ingest fixture chunks, query them, and assert alias/type/language round-trip.
- Contract tests query by alias/type filters to prove schema guarantees.
- Observability tests capture logs/metrics to ensure instrumentation fires per batch/query.

## Out of Scope
- Deployment automation or schema migration tooling (init already checks Weaviate readiness).
- Multi-language retrieval beyond tagging mismatches for FR-011 warnings.
