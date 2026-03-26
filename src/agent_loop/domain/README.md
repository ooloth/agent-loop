# Domain Layer

Shared types and contracts (the _what_).

Nothing in this package depends on any external system. It is the contract the rest of the codebase
is built around. See `specs/architecture.md` for the architectural rationale.

## Contents

- **`protocols.py`** — Port protocols (`AgentBackend`, `VCSBackend`, `IssueTracker`) that feature pipelines depend on and adapters implement
- **`context.py`** — `AppContext`: the composition root passed to every pipeline command
- **`config.py`** — `Config`: settings loaded from `.agent-loop.yml`
- **`issues.py`** — `Issue` and `FoundIssue`: tracker-agnostic work item types
