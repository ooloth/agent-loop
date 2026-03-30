# Features

Vertical slices that compose domain and io building blocks (the _when_ and _why_).

The feature pipelines: `analyze`, `fix`, and `watch`.

Each pipeline orchestrates domain ports and the implement/review engine to carry
out one user-facing workflow. Pipelines depend on `domain/` and may use
`io/observability` for output, but never import adapters, bootstrap, or
transports — they receive concrete backends via `AppContext` at the call site.
See `ARCHITECTURE.md` at the repo root for the architectural rationale.

## Contents

- **`analyze/`** — Runs the agent against the codebase, parses the response, and files any newly
  discovered issues in the tracker
- **`fix/`** — Iterates over ready issues, runs the implement→review loop, commits the result,
  opens a PR, and posts the review trail as a comment
  - **`engine.py`** — The core `implement_and_review()` loop (no backend knowledge)
  - **`branch_session.py`** — `BranchSession`: manages git branch lifecycle around the engine
    (concrete context manager, not a protocol)
- **`watch/`** — Runs `fix` then `analyze` on a loop with backpressure gating
