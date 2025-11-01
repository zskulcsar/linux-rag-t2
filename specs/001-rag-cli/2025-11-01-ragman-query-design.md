# Ragman Query Presentation Design

## Context
`ragman` must answer Linux questions with rich, citation-heavy markdown while also supporting a plain-text fallback. The CLI communicates with the Python backend over the existing Unix socket JSON protocol; this design focuses on the command-side presentation, confidence gating, and configuration surfaces, assuming transport and domain responses comply with `contracts/backend-openapi.yaml`.

## Architecture Overview
The Cobra root command remains a thin adapter responsible for gathering CLI inputs (`question`, `--plain`), generating correlation IDs, and invoking the shared IPC client. Responses instantiate a `QueryResponse` domain struct that the presenter layer consumes. Presentation logic lives in `cli/ragman/internal/presentation`, exposing a `Presenter` interface with `Render(QueryResponse) (string, error)`. Two concrete presenters load Go `text/template` layouts: `answer.md.tmpl` (default markdown) and `answer.txt.tmpl` (plain). The command selects the presenter at runtime based on the `--plain` flag. Rendered strings write directly to stdout, preserving the hexagonal split between Cobra wiring, transport adapters, and view concerns.

## Template Strategy
Templates reside in `cli/ragman/internal/presentation/templates/` and are embedded via Go `embed` so binaries stay self-contained. A shared `AnswerViewModel` carries ordered sections: summary paragraph, confidence line, step-by-step bullets, citation list. Conditional blocks switch to a friendly “no answer” layout (with remediation guidance) when the view model signals low confidence or backend-declared gaps. Embedding templates permits golden-file testing and quick iteration without mixing formatting strings into Go sources.

## Confidence Threshold Configuration
Confidence gating reads from `${XDG_CONFIG_HOME:-$HOME/.config}/ragcli/config.yaml` under a `query_presentation.min_confidence` field. A new loader in `cli/ragman/internal/config` resolves the file, validates `0.0 ≤ min_confidence ≤ 1.0`, and falls back to the compiled default (0.35) on parse or range failures, logging a WARN before continuing. `ragadmin init` will seed the config to guarantee first-run defaults. The chosen threshold flows into presenters alongside backend confidence; values below the threshold trigger the “no answer” rendering while still returning exit code 0.

## Error Handling & Logging
Transport errors bubble through `RunE`, yielding non-zero exits and structured ERROR logs (`QueryCommand.execute(question) :: transport_failed`). Template or configuration issues raise annotated errors that Cobra prints concisely while slog logs include correlation IDs passed from the IPC client. No-answer cases and low-confidence fallbacks log at INFO to avoid noisy alerts. The CLI never exits on configuration warnings alone, ensuring resilience during partial misconfiguration.

## Testing Plan
1. Presenter unit tests (`presenter_test.go`) exercise markdown/plain templates across high-confidence, threshold, low-confidence, and backend “no answer” scenarios using golden outputs under `testdata/`.
2. Config loader tests (`config_test.go`) verify defaulting, valid overrides, malformed YAML, and out-of-range values via temporary directories mimicking XDG paths.
3. Cobra command tests (`cmd/query_test.go`) inject fake IPC clients/config loaders to assert rendered stdout, exit codes, and logged metadata.
4. Future end-to-end contract tests ensure CLI behaviour aligns with backend confidence semantics near configured thresholds.
