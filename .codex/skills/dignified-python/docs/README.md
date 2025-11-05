# Python project Documentation

**Welcome!** This directory contains detailed documentation for any python project.

---

## For AI Agents: Start Here

Choose your starting point based on your task:

| Your Task                           | Start Here                                                                |
| ----------------------------------- | ------------------------------------------------------------------------- |
| **Need code examples**              | [PATTERNS.md](PATTERNS.md) - Code patterns and examples                   |
| **Working with exceptions**         | [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md) - Exception handling guide |

---

## Documentation Structure

### 📋 Core Standards (Start here)

**[../SKILL.md](../SKILL.md)** - Coding standards and rules

- Core rules (type annotations, imports, exception handling, etc.)
- Quick reference table to all other docs
- Design principles

### 📖 Detailed References

**[PATTERNS.md](PATTERNS.md)** - Code patterns and examples

- Type annotations examples
- Dependency injection pattern
- Import organization examples
- Code style (reducing nesting, etc.)
- File operations, CLI development, context managers
- Resource management

**[EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md)** - Complete exception handling guide

- LBYL vs EAFP patterns
- Critical enforcement rules
- Acceptable uses of exception handling
- Dictionary access, validation, file processing
- Anti-patterns and examples

### 🧪 Testing

**[../../test-driven-development/SKILL.md](../../test-driven-development/SKILL.md)** - Testing patterns and practices
**[../../testing-antipatterns/SKILL.md](../../testing-antipatterns/SKILL.md)** - Testing anti patterns and examples

- Unit tests with fakes
- Integration tests with real implementations
- Testing patterns

---

## Navigation Flow

### Typical Workflows

**1. First-time contributor:**

```
SKILL.md (core rules)
  └─> PATTERNS.md (see examples)
      └─> ../../test-driven-development/SKILL.md (learn testing)
```

**2. Working with exceptions:**

```
SKILL.md#exception-handling (rules)
  └─> EXCEPTION_HANDLING.md (complete guide)
```

**3. Understanding a pattern:**

```
SKILL.md (read rule)
  └─> PATTERNS.md#specific-pattern (see example)
```

---

## Quick Links

### Most Referenced Documents

1. [PATTERNS.md](PATTERNS.md) - Code examples
2. [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md) - Exception guide
3. [../../test-driven-development/SKILL.md](../../test-driven-development/SKILL.md) - Testing guide

### By Topic

**Writing code:**

- [SKILL.md](SKILL.md) - Coding standards
- [PATTERNS.md](PATTERNS.md) - Examples
- [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md) - Exception rules

**Testing:**

- [../../test-driven-development/SKILL.md](../../test-driven-development/SKILL.md) - Testing patterns

---

## Documentation Maintenance

### Review Checklist

During code review, verify:

- [ ] Examples in PATTERNS.md still compile and follow current patterns
- [ ] EXCEPTION_HANDLING.md reflects current exception handling approach
- [ ] ../../test-driven-development/SKILL.md matches current testing practices
- [ ] Links in all docs point to files that exist

---

## Contributing to Documentation

Documentation improvements are welcome! When updating docs:

1. **Keep it concise** - AI agents prefer brief, scannable content
2. **Use examples** - Code examples are worth a thousand words
3. **Link liberally** - Cross-reference related docs
4. **Maintain hierarchy** - Rules in CLAUDE.md, examples in PATTERNS.md
5. **Update navigation** - Keep quick reference tables current
6. **Only link to existing files** - Verify all links work

---

## Questions?

If you can't find what you need:

1. Check [PATTERNS.md](PATTERNS.md) for code examples
2. Check [EXCEPTION_HANDLING.md](EXCEPTION_HANDLING.md) for exception handling details

Still stuck? The documentation may need improvement - consider opening an issue or PR.
