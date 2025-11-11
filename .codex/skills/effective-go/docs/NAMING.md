# Naming Conventions

Idiomatic Go naming keeps APIs approachable and predictable.

## Packages
- Package names are short, lower-case, and avoid underscores (`net/http`, `json`, `os`).
- Choose a name that describes the purpose, not the implementation (`encoding/json`, not `jsonparser`).
- Importers refer to exported identifiers as `packagename.Symbol`, so avoid stuttering (e.g., `bytes.Buffer`, not `bytes.BytesBuffer`).

## Exported Identifiers
- Use `MixedCaps` for exported names (`NewClient`, `HTTPServer`).
- Export the minimum surface area needed—unexported helpers stay lower-case (`mixedCaps`).

## Getters and Setters
- Omit the `Get` prefix. Use the field name alone (`c.Name()` rather than `c.GetName()`).
- Setters include the verb `Set` when necessary (`SetDeadline`, `SetLogger`).

## Interface Names
- Prefer adjective or behavior-based names ending in `-er` (`Reader`, `Formatter`, `Stringer`).
- Small, focused interfaces (<3 methods) compose better and clarify intent.

## Acronyms
- Capitalize common acronyms (URL, HTTP) consistently: `ServeHTTP`, `NewURL`.
- For unexported names, keep acronyms in lower case (`url`, `http`).

## Stutter Avoidance
- Avoid repeating the package name in type names. If the package is `ring`, the type should be `type Buffer struct`, not `type RingBuffer struct`.
