# I/O Layer

Shared infrastructure and adapters (the _how_). All external I/O lives here.

Every module belongs to one of four subpackages:

- **`adapters/`** — Concrete implementations of domain protocols (`AgentBackend`, `VCSBackend`,
  `IssueTracker`). Swapping a backend (e.g. Linear instead of GitHub) means adding a new adapter
  here without touching features or the engine.
- **`bootstrap/`** — Startup assembly. Reads config from disk, constructs adapters, builds
  `AppContext`. Called by entrypoints, never by features.
- **`transports/`** — Low-level I/O channel wrappers (subprocess, HTTP) that adapters build on.
  Nothing outside `io/` imports these directly.
- **`observability/`** — Cross-cutting I/O that any layer may use (logging, telemetry). Independent
  of the other subpackages.

See `ARCHITECTURE.md` at the repo root for the full architectural rationale.

## Dependency rules within io/

The `layers` lint rule enforces that lower rows must not import higher rows.
Observability is independent: it may be imported by any of the others but imports
none of them.

| From ↓ · To →     | adapters | bootstrap | transports | observability |
| ----------------- | -------- | --------- | ---------- | ------------- |
| **adapters**      | —        | ❌        | ✅         | ✅            |
| **bootstrap**     | ✅       | —         | ✅         | ✅            |
| **transports**    | ❌       | ❌        | —          | ✅            |
| **observability** | ❌       | ❌        | ❌         | —             |

## Contents

- **`adapters/claude_cli.py`** — `ClaudeCliBackend`: runs the Claude CLI as a subprocess; provides
  separate read-only and edit tool sets for review vs implement agents
- **`adapters/git.py`** — `GitBackend`: wraps `git` CLI for staging, diffing, and branch operations
- **`adapters/github.py`** — `GitHubTracker`: wraps `gh` CLI for issues, labels, PRs, and the
  claim/release locking mechanism
- **`bootstrap/config.py`** — Loads and validates `.agent-loop.yml` into a `Config` instance
- **`observability/logging.py`** — Timestamped, tree-structured console logging helpers
- **`transports/process.py`** — Thin `subprocess.run()` wrapper used by all adapters
