# Analyze

Scan the codebase for issues and file them in the tracker.

```bash
agent-loop analyze
agent-loop --project-dir /path/to/project analyze
```

## Labels

| Label                   | Type    | Set by   | Lifecycle                    |
| ----------------------- | ------- | -------- | ---------------------------- |
| `agent-reported`        | Origin  | Analyzer | Permanent                    |
| `needs-human-review`    | Status  | Analyzer | Until human triages          |
| `ready-to-fix`          | Trigger | Human    | Permanent (signals approval) |
| `agent-fix-in-progress` | Lock    | Fixer    | Permanent                    |

Human-authored issues skip `agent-reported` and `needs-human-review` — just add `ready-to-fix`.
