# Data Model

## KnowledgeSource
- **Fields**: `alias` (string, unique, auto-derived from filename with numeric suffix conflict resolution), `type` (enum: `man`, `kiwix`, `info`), `location` (absolute path or URI), `language` (ISO code, default `en`), `size_bytes` (int), `last_updated` (datetime), `status` (enum: `pending_validation`, `active`, `quarantined`, `error`), `checksum` (optional string), `notes` (optional string), `created_at` (datetime), `updated_at` (datetime).
- **Relationships**: One-to-many with `IngestionJob` (a source produces ingestion jobs); contributes documents to `ContentIndex`.
- **Validation**: Alias uniqueness enforced; `location` must exist and be readable; language must equal `en` or trigger warning with status downgrade; size must be ≥0; `type` validation influences ingestion adapter.
- **State Transitions**: `pending_validation` → `active` after checksum verification and initial ingestion; `active` → `quarantined` on corruption or missing path; `active` → `error` when ingestion fails; `quarantined` → `active` after operator remediation.

## IngestionJob
- **Fields**: `job_id` (UUID), `source_alias` (string, FK to KnowledgeSource), `requested_at` (datetime), `started_at` (datetime), `completed_at` (datetime), `status` (enum: `queued`, `running`, `succeeded`, `failed`, `cancelled`), `documents_processed` (int), `error_message` (optional string), `trigger` (enum: `init`, `manual`, `scheduled`).
- **Relationships**: Belongs to a `KnowledgeSource`; may feed into `ContentIndexVersion`.
- **Validation**: `completed_at` required when status terminal; `documents_processed` ≥0; `source_alias` must reference existing active/quarantined source.
- **State Transitions**: `queued` → `running` → `succeeded|failed`; manual cancellation moves `running` → `cancelled`; failed jobs may be retried creating new record.

## ContentIndexVersion
- **Fields**: `index_id` (UUID), `built_at` (datetime), `status` (enum: `ready`, `stale`, `building`, `failed`), `checksum` (string), `source_snapshot` (list of `{alias, checksum}`), `size_bytes` (int), `document_count` (int), `freshness_expires_at` (datetime), `trigger_job_id` (UUID reference).
- **Relationships**: One-to-one with the currently active index; references `IngestionJob` that produced it; aggregates many `KnowledgeSource` entries.
- **Validation**: `status` must be `ready` before `ragman` queries execute; `source_snapshot` must list every active source; `freshness_expires_at` computed from policy (e.g., 7 days).
- **State Transitions**: `building` → `ready` on success; `building` → `failed` on error; `ready` → `stale` once `freshness_expires_at` passed or a source changed.

## QuerySession
- **Fields**: `session_id` (UUID), `question` (string), `summary` (string), `steps` (list of strings), `references` (list of `{label, url, notes}`), `confidence` (float 0-1), `citations` (list of `{alias, document_ref}`), `no_answer` (boolean), `latency_ms` (int), `retrieval_latency_ms` (int), `llm_latency_ms` (int), `timestamp` (datetime), `trace_id` (string).
- **Relationships**: Optionally associates with `ContentIndexVersion` used; logged to Phoenix for observability.
- **Validation**: `citations` MUST contain at least one entry unless `no_answer` is true; `confidence` between 0 and 1; `summary` may contain the fallback guidance when `no_answer` is true.
- **State Transitions**: Stateless per request; archived for observability only.

## AuditLogEntry
- **Fields**: `entry_id` (UUID), `timestamp` (datetime), `actor` (string, default `local-admin`), `action` (enum: `init`, `source_add`, `source_update`, `source_remove`, `reindex_start`, `reindex_complete`, `health_check`), `target` (string), `status` (enum: `success`, `failure`), `details` (string), `trace_id` (string).
- **Relationships**: References the domain event that generated it (e.g., `IngestionJob` or `KnowledgeSource`).
- **Validation**: Mandatory `trace_id` to correlate with logs; `details` captured for failure states.
- **State Transitions**: Append-only ledger; no transitions.

## HealthCheckResult
- **Fields**: `check_id` (UUID), `timestamp` (datetime), `component` (enum: `index_freshness`, `source_access`, `disk_capacity`, `ollama`, `weaviate`), `status` (enum: `pass`, `warn`, `fail`), `message` (string), `remediation` (string), `metrics` (JSON object for numeric values).
- **Relationships**: Grouped per `ragadmin health` invocation for response payloads; overall status computed on the fly (any `fail` → `fail`, else `warn` if any `warn`).
- **Validation**: `status` derived from thresholds (e.g., disk < 10% free → `fail`); `component` enumerated.
- **State Transitions**: None; results are immutable snapshots.

## SourceCatalog
- **Fields**: `updated_at` (datetime), `entries` (list of current `KnowledgeSource` snapshots).
- **Relationships**: Single persisted record representing the active catalog consumed by backend and CLIs.
- **Validation**: Entries sorted by alias; aliases remain unique.
- **State Transitions**: Snapshot overwritten in place when sources are added, updated, or removed.
