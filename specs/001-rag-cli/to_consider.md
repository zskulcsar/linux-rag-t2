# To-Consider Items: Local Linux RAG CLI

**Purpose**: Track open design/implementation questions that need explicit decisions before proceeding. Each entry should be actionable when picked up later.

---

## TC001 – Streaming response handling on client disconnect

- **Context**: During long-running `/v1/index/reindex` streams, the CLI may drop (timeout/exit) while the backend continues processing and streaming snapshots. The current server logs “Connection lost” and raises broken pipe exceptions when it tries to write additional frames to a dead socket.
- **Decision to make**: Should the backend:
  1) **Stop sending and abort the build** immediately on client disconnect, or
  2) **Continue processing** the ingestion job to completion and only silence writes, or
  3) **Continue processing with resumable streaming** if a new client reconnects?
- **Implications**:
  - Aborting preserves compute but might leave the catalog/index in an indeterminate state unless we roll back.
  - Continuing is safer for index integrity but can mask that the operator never saw progress/success.
  - Resumable streams would require correlation IDs/session tracking and a reconnect protocol (out of scope unless explicitly approved).
- **Open questions**:
  - What’s the expected UX if the operator closes `ragadmin reindex` mid-run?
  - Should we emit an audit/log marker when a client disconnects mid-stream?
  - Do we need a flag/environment toggle to select abort vs continue behavior?
- **Suggested next step**: Decide desired policy (abort vs continue) and implement corresponding server-side behavior, including graceful suppression of write errors and clear audit logging either way.

## TC002 – Configurable streaming timeouts/heartbeats

- **Context**: We currently rely on a fixed per-frame read timeout on the CLI (`15s`) and backend heartbeats (~10s) to keep long reindex streams alive. This works in the happy path but is static.
- **Decision to make**: Should we expose configuration (env/flags) for:
  - CLI per-frame read timeout for streaming IPC calls.
  - Backend heartbeat cadence (docs per batch, elapsed seconds).
- **Implications**: Tunables would help on slower machines or larger corpora without code changes, but add surface area and validation burden (e.g., avoid too-short timeouts or excessively chatty heartbeats).
- **Suggested next step**: If we see recurring timeout issues or need per-environment tuning, add env-based overrides with sane min/max guards and document the interaction between heartbeat and timeout.

## TC003 – Span processor choice for Phoenix

- **Context**: Observability wiring currently uses the default `SimpleSpanProcessor`. Switching to `BatchSpanProcessor` would reduce network chatter and improve flush behavior, but may complicate tests or shutdown paths.
- **Decision to make**: Should we adopt `BatchSpanProcessor` in dev/prod while keeping `SimpleSpanProcessor` for fast test runs? If yes, add shutdown flushing to avoid dropped spans.
- **Implications**: Batch mode yields better performance and fewer dropped spans but adds buffering and requires explicit close/flush. Simple mode is noisier and can drop spans on exit if the process ends abruptly.
- **Suggested next step**: Decide per-environment policy; implement conditional processor selection with a clean shutdown hook if batching is enabled.
