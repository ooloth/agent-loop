# Specs

This directory contains the domain specifications for agent-loop.

## What these specs are

Each spec is a **timeless, tool-agnostic record of desired state**: the behaviors, invariants, contracts, and structural intentions that define what this project is and how it should work.

Specs are written to survive implementation churn. They should remain valid if the project were rewritten in a different language, with different tools, or targeting different providers. They describe *what* and *why*, not *how*.

A useful test: could you regenerate a working implementation from these specs alone?

## What belongs in a spec

- Protocol definitions and their contracts
- Behavioral invariants ("X must always Y", "Z never raises, returns empty instead")
- Domain types and their relationships
- Architectural layers and the boundaries between them
- Known adapters and planned future adapters
- Explicit decisions about what is *not* abstracted and why

## What does not belong

- Specific library versions or tool invocations
- Implementation details that are likely to change (e.g. exact subprocess flags)
- Operational concerns (deployment, configuration format)
- Anything that only makes sense in the current concrete implementation

## Format and style

Specs use **language-agnostic pseudocode** for all type and interface definitions.
The goal: a spec should be equally readable to someone implementing in Rust, Go,
or TypeScript. If it could only be read by a Python developer, it has too much
implementation detail.

**Use pseudocode like this:**

```
MyProtocol:
  method_name(param: type) -> return_type
  other_method(a: string, b: integer) -> list<Thing>

MyType:
  field_name:   type       -- inline comment explaining semantics
  optional?:    string     -- ? suffix means optional/nullable
```

**Do include:**
- Method names, parameter names, and abstract types (`string`, `integer`,
  `bool`, `list<T>`, `set<T>`, `T | null`)
- Field names and their purpose
- Behavioral invariants and edge cases
- Design rationale — especially for non-obvious decisions

**Do not include:**
- Language-specific syntax (`@dataclass`, `TypedDict`, `impl`, `struct`, etc.)
- File paths or module locations
- Constructor signatures or default parameter values
- Implementation details (subprocess flags, CLI arguments, library calls)
- Anything that would need updating when refactoring without changing behavior

---

## How to maintain specs

Specs are allowed to be **optimistically ahead of implementation** — writing a spec before or during implementation is the intended workflow. That lag is expected and normal.

Specs become a problem when they are:
- **Stale**: they describe something that was renamed, moved, or removed
- **Silent**: the implementation has evolved and the spec was never updated
- **Underspecified**: the implementation reveals decisions the spec doesn't capture

Run `/analyze-spec-drift` to detect these conditions and get recommendations.

## Spec inventory

| Spec | Covers |
|---|---|
| [architecture.md](architecture.md) | Layered architecture, file structure, feature pipelines, domain types |
| [agent-backend.md](agent-backend.md) | `AgentBackend` protocol — the AI execution port |
| [vcs-backend.md](vcs-backend.md) | `VCSBackend` protocol — the version-control port |
| [issue-tracker.md](issue-tracker.md) | `IssueTracker` protocol — the issue-platform port |
