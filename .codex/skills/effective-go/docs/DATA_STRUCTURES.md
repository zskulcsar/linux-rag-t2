# Data and Allocation

## `new` vs `make`
- `new(T)` allocates zeroed storage and returns `*T`.
- `make` initializes slices, maps, and channels, returning the initialized value (not a pointer).

## Composite Literals
- Use composite literals to populate structs, arrays, slices, and maps succinctly.
- For exported struct fields, specify field names to clarify intent.

## Arrays and Slices
- Arrays have fixed length; slices are descriptors (`len`, `cap`, pointer to array).
- Use slices for most collections; they reference shared backing arrays.
- Reslicing shares underlying data; copy if you need isolated storage (`b := append([]T(nil), a...)`).

## Append
- `append` handles capacity growth; capture the returned slice.
- Appending to nil slice works naturally (`var data []int; data = append(data, 1)`).

## Maps
- Initialize maps with `make(map[K]V)` before assignment.
- Map reads for missing keys return the zero value; use the second value to test presence (`v, ok := m[k]`).
- Maps are not safe for concurrent writes; guard with `sync.Mutex` or use `sync.Map`.

## Struct Initialization
- Provide zero-value friendly types; zero values should be ready for use.
- Avoid pointer fields unless nil is an intentional state.
