# I/O Layer

Shared infrastructure and adapters (the _how_). All external I/O lives here.

Adapters implement the port protocols defined in `domain/` and are wired into `AppContext` at
startup. Swapping a backend (e.g. Linear instead of GitHub) means adding a new adapter here without
touching pipelines or the engine. See `specs/architecture.md` for the architectural rationale.

## Contents

- **`adapters/claude_cli.py`** — `ClaudeCliBackend`: runs the Claude CLI as a subprocess; provides
  separate read-only and edit tool sets for review vs implement agents
- **`adapters/git.py`** — `GitBackend`: wraps `git` CLI for staging, diffing, and branch operations
- **`adapters/github.py`** — `GitHubTracker`: wraps `gh` CLI for issues, labels, PRs, and the
  claim/release locking mechanism
- **`config.py`** — Loads and validates `.agent-loop.yml` into a `Config` instance
- **`logging.py`** — Timestamped, tree-structured console logging helpers
- **`process.py`** — Thin `subprocess.run()` wrapper used by all adapters
