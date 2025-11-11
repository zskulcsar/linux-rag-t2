# Concurrency Principles

## Share Memory by Communicating
- Prefer channels for coordination over shared mutable state.
- Minimize the amount of data shared via mutexes; if you must share, keep critical sections small.

## Goroutines
- Launch concurrent work with `go f()`. Goroutines run asynchronously; ensure they eventually complete or their lifetime is deliberate.
- Capture loop variables correctly when launching goroutines—create a local copy inside the loop.

## Channels
- Use channels to synchronize or transfer data (`ch := make(chan T)`).
- Buffered channels decouple senders and receivers; size them according to pipeline throughput needs.
- Close channels from the sender side to signal completion. Receivers test closure via the second value: `v, ok := <-ch`.

## Select
- `select` waits on multiple channel operations simultaneously. Include a `default` case only when non-blocking behavior is required.

## Pipelines
- Structure concurrent stages with dedicated goroutines connected by channels.
- Handle cancellation via context (`context.Context`) to avoid leaking goroutines.
