---
name: go-testing
description: Applies Go testing best practices aligned with the Linux RAG T2 constitution (Go 1.23). Use when writing or modifying Go test files or advising on Go testing strategies.
---

# Go Testing Best Practices (Go 1.23)

## Always Apply These Rules

### 1. Test Organisation
- Place tests alongside source files using the `*_test.go` suffix.
- Use internal tests (same package) for fine-grained unit coverage; reserve external tests (`package foo_test`) for integration, examples, and black-box validation.
- Split long test files once they exceed ~600 lines to keep suites readable.

### 2. Table-Driven Testing
- Prefer slice-based tables with explicit `name` fields. Use `t.Run(tc.name, func(t *testing.T) { ... })` for clarity.
- Keep inputs, expected outputs, and setup within the table struct; extract helpers when logic repeats.

### 3. Deterministic Concurrency
- With Go 1.23, favour explicit synchronization (channels, WaitGroups) over time-based sleeps.
- Use `t.Parallel()` when tests are self-contained; call it immediately inside the test function to avoid data races.

### 4. Assertions & Comparisons
- The standard library (`if got != want`) is sufficient for simple values.
- For complex structs, use `cmp.Diff` from `google/go-cmp` and fail with the diff.
- Avoid heavy assertion frameworks unless justified.

### 5. Test Doubles & Integration
- Accept interfaces, return concrete types, enabling simple hand-crafted mocks when needed.
- Prefer integration tests with real dependencies (e.g., Testcontainers) when behaviour depends on external systems.
- When mocking, understand the full contract; keep mocks minimal and scope them to the test.

### 6. Coverage Targets
- Per the constitution: libraries must maintain **≥90 %** line coverage; services require **≥80 %**.
- Use `go test -cover ./...` and review `go tool cover -html` outputs before merging.

### 7. Fixtures & Golden Files
- Store reusable fixtures under a `testdata/` directory (ignored by `go build`).
- For golden tests, add `-update` flags to regenerate expected output intentionally.

### 8. Helpers & Cleanup
- Mark helper functions with `t.Helper()` so failures point to the caller.
- Use `t.Cleanup()` for teardown logic; it runs even if a test fails early.

### 9. Benchmarks & Profiling
- Stick to standard benchmarking patterns (`func BenchmarkX(b *testing.B)`).
- Use `b.ResetTimer()` and `b.ReportAllocs()` as needed; integrate `benchstat` for comparing runs.

### 10. Naming Conventions
- Functions: `TestX`, `BenchmarkX`, `FuzzX`, `ExampleX`.
- Locals: `got`/`want` for actual vs expected; include descriptive subtest names.

## Workflow Expectations

1. **TDD**: Follow the repository’s TDD skill—write failing tests first, then implement.
2. **CI Integration**: Ensure `go test ./...` and `golangci-lint` run clean before committing.
3. **Hermetic Tests**: Avoid reliance on ambient network or filesystem state; use temp dirs (`t.TempDir()`) and in-memory doubles.

## Quick Checklist

- [ ] Tests live next to production code with clear naming
- [ ] Table-driven structure with `t.Run` per case
- [ ] Concurrency controlled deterministically
- [ ] Coverage meets ≥90 % (libs) / ≥80 % (services)
- [ ] Helpers marked with `t.Helper()` and use `t.Cleanup()`
- [ ] No reliance on Go 1.24-only APIs (repository locked to Go 1.23)
- [ ] All tests pass locally (`go test ./...`)

## References

- Go testing package: https://pkg.go.dev/testing
- Go testable examples: https://go.dev/doc/tutorial/add-a-test
- `google/go-cmp`: https://pkg.go.dev/github.com/google/go-cmp/cmp
- Project constitution: `.specify/memory/constitution.md`
