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

| Label | Type | Set by | Lifecycle |
|---|---|---|---|
| `agent-reported` | Origin | Analyzer | Permanent |
| `needs-human-review` | Status | Analyzer | Until human triages |
| `ready-to-fix` | Trigger | Human | Permanent (signals approval) |
| `agent-fix-in-progress` | Lock | Fixer | Permanent |

Human-authored issues skip `agent-reported` and `needs-human-review` — just add `ready-to-fix`.

## Requirements

- [uv](https://docs.astral.sh/uv/)
- [gh](https://cli.github.com/) (authenticated)
- [claude](https://docs.anthropic.com/en/docs/claude-cli) CLI

## Usage

```bash
# Analyze current project
cd /path/to/project
agent-loop analyze

# Fix all ready-to-fix issues
agent-loop fix

# Fix a specific issue
agent-loop fix --issue 42

# Point at a different project
agent-loop --project-dir /path/to/project analyze
```

## Configuration

Drop a `.agent-loop.yml` in your project root to customize behavior:

```yaml
max_iterations: 3
context: |
  This is a Python project using FastAPI.
  Tests use pytest. Run them with `make test`.
```

All fields are optional — sensible defaults are built in.
