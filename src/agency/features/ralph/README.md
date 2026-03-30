# Ralph

Iterative fresh-eyes refinement toward a goal. Each iteration starts from a
clean read of the codebase and commits its changes for crash safety. Opens a
draft PR when done.

```bash
# Execute a plan from a planning session
agent-loop ralph --plan .plans/add-error-handling.md

# Work from a file or inline prompt
agent-loop ralph --file goal.md
agent-loop ralph --prompt 'add type hints to foo.py' --max-iterations 10
```
