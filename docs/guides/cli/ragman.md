# ragman CLI (query interface)

`ragman` is the primary command-line interface for posing English-language
questions against the local Linux RAG backend. The CLI maintains the offline
contract defined in `specs/001-rag-cli/spec.md` and communicates with the
backend over Unix domain sockets.

## Usage

```bash
ragman query "How do I change file permissions?"
```

### Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--context-tokens` | `4096` | Maximum token budget forwarded to retrieval (min 512, max 8192). |
| `--conversation` | _(empty)_ | Optional conversation identifier for follow-up questions. |
| `--json` | `false` | Emit raw JSON payload from the backend. |
| `--plain` | `false` | Render plain-text output instead of Markdown. |

The CLI enforces the confidence threshold seeded via
`${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml`. Responses below the
threshold render the fixed fallback guidance defined in FR-002.

## Response Structure

The backend returns a `QueryResponse` JSON object as defined in
`specs/001-rag-cli/contracts/backend-openapi.yaml`. Key fields include:

- `summary`: High-level answer paragraph or low-confidence guidance.
- `steps[]`: Ordered procedural instructions rendered under a numbered list.
- `references[]`: Source citations with labels/URLs used to build the reference table.
- `confidence`: Float between `0` and `1` that drives confidence handling.
- `trace_id`: Correlation identifier propagated through logs and Phoenix traces.

## Example Output

```text
Summary: Use `chmod` with the desired mode to adjust permissions.

Steps:
1. Run `chmod 755 <file>` to grant execute permissions.
2. Verify with `ls -l` to confirm the new mode.

References:
- chmod(1)

Confidence: 0.82
Latency: retrieval 180 ms, llm 900 ms, total 1.2 s
```

## Logging

`ragman` emits structured JSON logs via `log/slog` using the format mandated by
the repository constitution, e.g.:

```text
QueryCommand.Execute(question="How do I change file permissions?") :: starting request
```

## Future Enhancements

- Contract test harness under `tests/go/contract/` exercises framing and JSON
  validation against the backend transport.
- MkDocs pages will be extended with generated Cobra command reference once the
  command tree is implemented.
