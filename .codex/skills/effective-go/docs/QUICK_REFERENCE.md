# Quick Reference

- **Format**: Run `gofmt` or `go fmt ./...` before committing.
- **Naming**: Package names are lower case, no underscores; exported identifiers use `MixedCaps`.
- **Imports**: Group into stdlib, third-party, and internal. Avoid unused imports.
- **Errors**: Return `error`, check immediately, wrap with context, avoid panics.
- **Interfaces**: Keep small and focused; accept interfaces, return concrete types.
- **Concurrency**: Launch goroutines deliberately, close channels from the sender, respect contexts.
- **Zero Values**: Design types so the zero value is usable.
- **Documentation**: Doc comments start with the identifier name and describe behavior succinctly.
