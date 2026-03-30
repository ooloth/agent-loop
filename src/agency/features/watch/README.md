# Watch

Continuous loop: fix ready issues, analyze when the queue is low, sleep.

```bash
agent-loop watch
agent-loop watch --interval 1800          # poll every 30 minutes
agent-loop watch --max-open-issues 5      # pause analysis when 5+ issues await review
```

Each cycle:

1. **Fix** any `ready-to-fix` issues
2. **Analyze** if `needs-human-review` issues are below the cap (default: 3)
3. **Sleep** for the interval (default: 300s)

Press `Ctrl+C` to stop gracefully — the current step finishes before exiting.
