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

## Architecture

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for the layered architecture, domain
types, and feature pipeline overview. Protocol contracts and behavioral
invariants live as docstrings adjacent to the code they describe.

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

## Inspiration

- [Case Statement: Building a Harness](https://nicknisi.com/posts/case-statement/) + [workos/case](https://github.com/workos/case) by Nick Nisi
- [Harness engineering: leveraging Codex in an agent-first world](https://openai.com/index/harness-engineering/) by Ryan Lopopolo
- [Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) by Justin Young
- [Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps) by Prithvi Rajasekaran
- [Harness Engineering](https://martinfowler.com/articles/exploring-gen-ai/harness-engineering.html) by Birgitta Böckler
- [Relocating Rigor](https://aicoding.leaflet.pub/3mbrvhyye4k2e) by Chad Fowler
- [Skill Issue: Harness Engineering for Coding Agents](https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents) by Kyle Mistele
- [Engineer the Harness](https://mitchellh.com/writing/my-ai-adoption-journey#step-5-engineer-the-harness) by Mitchell Hashimoto
