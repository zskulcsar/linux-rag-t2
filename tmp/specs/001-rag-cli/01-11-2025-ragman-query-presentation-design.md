# ragman Query Presentation Design

## Context
`ragman` must render Linux answers in two styles—rich markdown (default) and a plain-text variant—while honouring backend confidence scores and a configurable threshold override. The CLI already talks to the Python backend over the Unix socket JSON protocol defined in `contracts/backend-openapi.yaml`; this design covers command-side presentation, the `--plain` flag, configuration loading, and the logging/error conventions needed to keep behaviour predictable.

## Architecture Overview
The Cobra root command accepts the positional `question` plus `--plain`, generates a correlation ID, and delegates to a `QueryService`. That service loads presentation config, calls the shared IPC client with `{ question, correlation_id, format: "structured" }`, and hydrates a `QueryResponse` struct containing summary text, ordered steps, references, inline alias markers, confidence, and optional `no_answer` guidance. Presentation lives under `cli/ragman/internal/presentation` behind a `Presenter` interface. Two implementations (`MarkdownPresenter`, `PlainPresenter`) embed Go `text/template` layouts via `go:embed`. The command selects the presenter at runtime, invokes `Render`, and writes the returned bytes directly to stdout, keeping Cobra free of formatting logic and preserving the hexagonal split.

## Template Strategy & Formatting
Templates reside in `internal/presentation/templates/` and share a single view model with fields for confidence, summary paragraph, step list, references, threshold, and remediation guidance. Each template begins with a Confidence line (`Confidence: {{ printf "%.0f%%" (mul .Confidence 100) }}`) so formatting occurs in the template, not Go code. Inline aliases such as `(man chmod)` are preserved because the backend places them inside summary/step strings; templates never strip them. The Markdown template renders sections as:

```
Confidence: 82%

Summary:
{{ .Summary }}

Steps:
1. {{ index .Steps 0 }}
...

References:
[1] {{ index .References 0 }}
```

If `ShowAnswer` is false (confidence below threshold or backend `no_answer` flag), the template switches to:

```
Confidence: 28% (threshold 35%)

No answer found.
- {{ range .Guidance }}{{ . }}
```

The plain template uses the same structure but trims markdown emphasis while retaining numbering and brackets, yielding a best-effort plain output without losing citations. Future formats can plug in new templates and presenters without touching command wiring.

## Confidence Configuration & Override
`cli/ragman/internal/config` loads `${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml` using `os.UserConfigDir`. Structure:

```yaml
query_presentation:
  min_confidence: 0.35
  default_format: markdown
```

Loader rules: treat missing files as defaults (0.35, markdown) and log at INFO; permit overrides where `0.0 <= min_confidence <= 1.0`; malformed YAML or out-of-range values trigger WARN logs and fall back to 0.35. The loader returns `(Config, error)` so the `QueryService` can log warnings alongside the correlation ID but continue. `ragadmin init` seeds the config file on first run with the default values to guarantee deterministic behaviour. The effective threshold travels into the view model, and templates display it as a percentage rounded to the nearest integer.

## Error Handling & Logging
Transport errors surface as `RunE` failures with exit code 2 and an ERROR log `QueryCommand.execute(question) :: transport_failed` tagging the correlation ID. Template, config, or rendering issues bubble up as user-friendly CLI errors, still logging WARN/ERROR with `presentation_failed`. Low-confidence fallbacks and backend-declared `no_answer` cases log at INFO (`QueryService.render :: no_answer`), avoiding noisy alerts. Configuration warnings never abort execution, ensuring resilience even when the config file is absent or malformed.

## Testing Plan
1. Presenter unit tests (`internal/presentation/presenter_test.go`) cover markdown/plain outputs at high confidence, just-below-threshold, backend `no_answer`, and malformed data. Golden files under `testdata/` safeguard template changes.
2. Config loader tests (`internal/config/config_test.go`) use `t.TempDir()` to simulate XDG paths, checking defaults, valid overrides (e.g., 0.42), malformed YAML, and out-of-range values.
3. Command-level tests (`cmd/query_test.go`) inject fake IPC clients and configs to assert stdout rendering, exit codes, and logged correlation IDs across success, low confidence, backend errors, and transport failures.
4. Contract tests extend existing suites to validate CLI behaviour near the configured threshold, ensuring plain/markdown modes stay consistent with backend semantics.
