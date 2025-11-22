# ragadmin Reindex Streaming Progress

## Context

Backend `/v1/index/reindex` now streams multiple job snapshots (stages, percent complete) over a single Unix-socket response. `ragadmin reindex` still calls `Client.StartReindex`, which only retrieves the first frame, so operators see a static “Reindex running” message irrespective of actual progress. We want option B from the brainstorming prompt: the CLI updates one line in place as new snapshots arrive. Work spans the Go IPC client (`cli/shared/ipc`) and the ragadmin command (`cli/ragadmin/cmd/reindex.go`). Tests and docs must reflect the streaming UX.

## Design Overview

1. **Streaming IPC API**: Introduce `StartReindexStream(ctx, req, onUpdate)` that:
   - Sends the reindex request (same payload as today) and reads the initial 202 frame.
   - Invokes `onUpdate(IngestionJob)` for the initial job as well as every subsequent frame, looping until a terminal status appears (`succeeded`, `failed`, `cancelled`).
   - Leaves connection clean-up to the client once the stream concludes or context cancels. The existing `StartReindex` wraps the streamer, recording the most recent job snapshot and returning it.
   - Implementation detail: factor a `callStream` helper into `Client` that returns the first `responseFrame` plus a `func(context.Context) (responseFrame, bool, error)` iterator; the streamer consumes the iterator until `ok == false` or the job terminates.

2. **CLI Rendering**: `ragadmin reindex` switches to the streaming helper and registers a callback that:
   - Updates a shared `lastJob` pointer for final summary/audit.
   - For TTY output, rewrites the same line via `fmt.Fprintf(out, "\rReindex %s — Stage: %s (%d%%)", ...)` and flushes after each update. Once the stream completes, print a newline followed by the existing summary (status, stage, duration).
   - For `--json`, emit each snapshot as JSON on its own line (`{"event":"progress","job":...}`) to keep scripts simple.
   - Errors from the streaming client (connection drop, context cancellation) bubble up; the CLI prints the final job snapshot (if any) and returns a failure exit code.

3. **Testing & Docs**:
   - New Go unit tests for `StartReindexStream` simulate a sequence of frames using a stubbed reader, asserting callback ordering and proper termination.
   - Extend ragadmin contract/integration tests to verify multiple progress frames: run `ragadmin reindex` against the fake backend with `RAG_BACKEND_FAKE_SERVICES=1` and assert captured stdout contains carriage-return progress updates before the final summary.
   - Document the streaming UX in `docs/guides/cli/ragadmin.md` and mention the JSON event stream format.
   - Update spec/plan/tasks to capture this deliverable via new tasks (tests first, implementation second) referencing this design.

