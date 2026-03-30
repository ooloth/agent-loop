# Domain Layer

Shared types and contracts (the _what_).

Nothing in this package depends on any external system. It is the contract the rest of the codebase
is built around. See `ARCHITECTURE.md` at the repo root for the architectural rationale.

- **`models/`** — Domain entities that flow through the system (`Issue`, `FoundIssue`). Pure data,
  no dependencies on other domain modules.
- **`ports/`** — Port protocols (`AgentBackend`, `VCSBackend`, `IssueTracker`) that feature
  pipelines depend on and adapters implement. Depend on models only.
- **`config.py`** — `Config`: settings loaded from `.agent-loop.yml`
- **`context.py`** — `AppContext`: the composition root passed to every pipeline command; carries
  all backends so features never import adapters directly. The top of the domain DAG — nothing
  else in domain imports it.
- **`errors.py`** — Domain exceptions (`AgentLoopError`, `SubprocessError`, `AgentError`,
  `AnalysisParseError`) raised by adapters and pipelines, caught at the CLI boundary.

## Dependency rules within domain/

Models and errors are leaves. Ports depend on models only. Context sits at the
top — consumed by higher layers, never by peers.

| From ↓ · To →  | models | ports | config | context | errors |
| --------------- | ------ | ----- | ------ | ------- | ------ |
| **models**      | —      | ❌    | ❌     | ❌      | ❌     |
| **ports**       | ✅     | —     | ❌     | ❌      | ❌     |
| **config**      | ❌     | ❌    | —      | ❌      | ❌     |
| **context**     | ❌     | ✅    | ✅     | —       | ❌     |
| **errors**      | ❌     | ❌    | ❌     | ❌      | —      |
