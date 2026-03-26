# agent-loop

Analyze a codebase for issues, fix them with AI review, open PRs.

## Workflow

```
Analyzer Agent → Human Triage → Fix + Review Loop → PR → Human Review → Merge
```

1. `agent-loop analyze` — agent scans codebase, creates GitHub issues
2. Human reviews issues, adds `ready-to-fix` label to approved ones
3. `agent-loop fix` — picks up ready issues, runs fix + review loop, opens PR
4. Human reviews the PR, merges it (which closes the issue)

## Labels

| Label                   | Type    | Set by   | Lifecycle                    |
| ----------------------- | ------- | -------- | ---------------------------- |
| `agent-reported`        | Origin  | Analyzer | Permanent                    |
| `needs-human-review`    | Status  | Analyzer | Until human triages          |
| `ready-to-fix`          | Trigger | Human    | Permanent (signals approval) |
| `agent-fix-in-progress` | Lock    | Fixer    | Permanent                    |

Human-authored issues skip `agent-reported` and `needs-human-review` — just add `ready-to-fix`.

## Specs

Domain specifications live in [`specs/`](specs/README.md) — timeless, tool-agnostic records of desired behavior, protocols, and architectural invariants.

| Spec | Covers |
|---|---|
| [architecture.md](specs/architecture.md) | Layered architecture, file structure, feature pipelines, domain types |
| [agent-backend.md](specs/agent-backend.md) | `AgentBackend` protocol — the AI execution port |
| [vcs-backend.md](specs/vcs-backend.md) | `VCSBackend` protocol — the version-control port |
| [issue-tracker.md](specs/issue-tracker.md) | `IssueTracker` protocol — the issue-platform port |

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [gh](https://cli.github.com/) (authenticated)
- [claude](https://docs.anthropic.com/en/docs/claude-cli) CLI

## Install

```bash
# Clone and enter the repo
git clone https://github.com/ooloth/agent-loop.git
cd agent-loop

# Install dependencies
uv sync --group dev

# Install as a CLI tool (editable — source changes take effect immediately)
uv tool install -e --reinstall .

# Install pre-commit hooks
prek install

# Verify
agent-loop --help
```

## Usage

```bash
# Analyze current project
cd /path/to/project
agent-loop analyze

# Fix all ready-to-fix issues
agent-loop fix

# Fix a specific issue
agent-loop fix --issue 42

# Watch mode — poll continuously
agent-loop watch
agent-loop watch --interval 1800          # poll every 30 minutes
agent-loop watch --max-open-issues 5      # pause analysis when 5+ issues await review

# Point at a different project
agent-loop --project-dir /path/to/project analyze
```

### Watch mode

`agent-loop watch` runs a continuous loop:

1. **Fix** any `ready-to-fix` issues
2. **Analyze** if `needs-human-review` issues are below the cap (default: 3)
3. **Sleep** for the interval (default: 300s)

Press `Ctrl+C` to stop gracefully — the current step finishes before exiting.

## Configuration

Drop a `.agent-loop.yml` in your project root to customize behavior:

```yaml
max_iterations: 5
context: |
  This is a Python project using FastAPI.
  Tests use pytest. Run them with `make test`.
```

All fields are optional — sensible defaults are built in.
