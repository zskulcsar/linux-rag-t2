# Error Handling

## Explicit Errors
- Functions that can fail should return an `error` as the last result (`value, err := op()`).
- Check errors immediately; handle or propagate them with context.

## Custom Error Types
- Implement the `error` interface via `Error() string` when more context is needed.
- Prefer sentinel errors or wrapping via `fmt.Errorf("operation: %w", err)` for clarity.

## Control Flow
- Use errors, not panics, for expected failure cases (invalid input, missing files, timeouts).
- Panics are reserved for unrecoverable situations or programmer mistakes.

## Defer, Panic, Recover
- Deferred functions run even during panics; release resources or log before rethrowing.
- Use `recover` sparingly to convert a panic into an error at module boundaries.

## Returning Zero Values
- On error, return zero values for other results, keeping semantics consistent.
