# Formatting Essentials

Go formatting is governed by `gofmt`. These rules keep codebases consistent and defer layout disputes to the tool.

## Tabs, Not Spaces
- Use tabs for indentation. `gofmt` emits tabs by default.
- Wrap long lines naturally; do not manually align continuation lines with spaces.

## Automatic Alignment
- Let `gofmt` align struct fields, composite literals, and import blocks.
- Avoid manual spacing for column alignment—`gofmt` will adjust it anyway.

## Semicolons
- Go inserts semicolons automatically at line breaks. Each statement should sit on its own line.
- Only use explicit semicolons in `for` headers or to separate multiple simple statements on one line (rare).

## Parentheses
- Go keeps expressions light on parentheses; only add them when required by operator precedence.

## Imports
- Group imports into standard library, third-party, and local packages.
- Use blank lines to separate groups; `goimports` or `gofmt` will maintain the grouping.

## gofmt as the Source of Truth
- Run `gofmt` (or `go fmt ./...`) before committing.
- If `gofmt` outputs something surprising, rewrite the code so the formatted version reads well.
