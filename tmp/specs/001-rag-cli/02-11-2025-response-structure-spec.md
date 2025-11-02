# Response Structure & Renderers

## Backend Payload
- Extend `QueryResponse` to include structured sections:
  - `summary`: string — short answer paragraph.
  - `steps`: array[string] — ordered procedural guidance.
  - `references`: array[object] — render-ready references (fields: `label`, `url`, `notes`).
  - `no_answer`: boolean — remains for fallback branch.
- Keep `answer` for backwards compatibility? (consider deprecating once CLI updated).
- `citations` continue referencing chunk IDs; allow empty when `no_answer` is true.
- `latency_ms`, `retrieval_latency_ms`, `llm_latency_ms`, `trace_id`, `index_version` unchanged.

## CLI Rendering
- Markdown presenter: use summary/steps/references templating already defined.
- Plain presenter: same sections without Markdown formatting.
- JSON presenter (`--json`): output raw backend payload.

## Configuration Overrides
- `${XDG_CONFIG_HOME}/ragcli/config.yaml` schema:
  ```yaml
  ragman:
    confidence_threshold: 0.35
    presenter_default: markdown
  ragadmin:
    output_default: table
  ```
- `ragadmin init` creates the file when missing.
- CLI flags reference these defaults; `--context-tokens` fallback to `ragman.confidence_threshold`? (clarify) -> separate: `--context-tokens` default 4096 constant.

## Fallback Copy
- When `confidence < threshold`, backend sets `no_answer=true`, empties `steps`, populates `summary` with fixed string:
  "Answer is below the confidence threshold. Please rephrase your query."

## Health & Init Decisions
- Disk WARN when free ≤10 %, FAIL when ≤8 %; index freshness WARN at 30 days; Ollama/Weaviate checks use 3 s timeouts.
- All health probes retry 5 times with exponential backoff (0.5 s, 1 s, 2 s, 4 s, 8 s) and emit concise remediation hints.
- Extract retry/threshold logic into dedicated Go helpers consumed by `ragadmin health`.
- `ragadmin init` seeds default sources:
  - `man-pages` → type `man`, location `/usr/share/man`, language `en`
  - `info-pages` → type `info`, location `/usr/share/info`, language `en`
  - ensure `${XDG_DATA_HOME}/ragcli/kiwix/` exists but do not register a kiwix source.

## Ingestion & Models
- Use semantic chunking up to 2 000 tokens for all source types with IDs `<alias>:<checksum>:<chunk_id>`.
- Calculate checksums via SHA256 for versioning and reuse in deterministic IDs.
- Embeddings via `embeddinggemma:latest`; generation via `gemma3:1b`.
- `ragman` exposes `--context-tokens` (default 4096) and `--conversation` to forward request metadata.

## Audit & Output
- Emit newline-delimited JSON audit entries with `timestamp`, `action`, `target`, `status`, `trace_id`, optional `message`/`error_code`.
- CLI presenters: markdown (default from config), plain text (`--plain`), raw JSON (`--json`).
