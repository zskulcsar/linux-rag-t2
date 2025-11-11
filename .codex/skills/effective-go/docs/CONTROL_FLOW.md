# Control Flow Patterns

## If Statements
- Declare short-lived variables in the `if` initializer (`if err := parse(...); err != nil { ... }`).
- Limit scope by keeping the variable inside the `if` statement when possible.

## For Loops
- Go has a single `for` construct: classic `for init; condition; post`, condition-only `for condition`, and infinite `for {}`.
- Prefer range loops for slices, arrays, maps, strings, and channels (`for i, v := range data`).
- Avoid manual index increments when `range` suffices.

## Switch
- `switch` statements do not require explicit `break`.
- Use `switch true { ... }` for if-else ladders.
- Type switches (`switch v := x.(type) { ... }`) discriminate on interface concrete types.

## Redeclaration
- `:=` reuses variables when at least one existing variable is on the left-hand side and all occur in the same scope.
- Keep an eye on shadowing—avoid redeclaring existing identifiers unintentionally.

## Defer
- Defer cleanup close to the resource acquisition: `f, err := os.Open(...); if err != nil { return err }; defer f.Close()`.
- Defers run in LIFO order when the surrounding function returns.
- Limited to function scope; avoid deferring in loops if the function runs often (or consider immediate cleanup).
