# agent-loop

Analyze a codebase for issues, fix them with AI review, open PRs.

## Workflow

```
Analyzer Agent → Human Triage → Fix + Review Loop → PR → Human Review
```

1. `agent-loop analyze` — agent scans codebase, creates GitHub issues labeled `needs-review`
2. Human reviews issues on GitHub, relabels to `ready-to-fix`
3. `agent-loop fix` — picks up `ready-to-fix` issues, runs fix + review loop, opens PR
4. Human reviews the PR

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
labels:
  needs_review: needs-review
  ready_to_fix: ready-to-fix
  in_progress: in-progress
```

All fields are optional — sensible defaults are built in.
