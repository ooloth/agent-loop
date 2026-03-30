# Plan

Interactive planning session — the agent explores the codebase, discusses
options with the user, and writes a plan file to `.plans/`. No automated loop.

```bash
agent-loop plan 'add error handling'
agent-loop plan                          # the agent will ask
```

The resulting plan can be fed directly to `ralph --plan`.
