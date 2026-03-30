# Ralph Pipeline

Iterative fresh-eyes refinement toward a goal. A single agent works in
independent iterations — each time it sees the codebase fresh, compares it
against the goal, and makes one improvement. Commits after each iteration for
crash safety and audit trail.

See: [loop-engine.md](loop-engine.md) for the `RalphStrategy` contract.

---

## Input modes

Ralph accepts work from one of three sources (mutually exclusive):

- `--prompt` — inline goal text
- `--file` — markdown file containing the goal
- `--plan` — plan file produced by `agent-loop plan` (treated as a file)

`--plan` and `--file` are functionally identical — the distinction is semantic
(plans are structured artifacts from a planning session; files are freeform).

---

## Flow

```
guard: no uncommitted changes (raises AgentLoopError)

branch = "ralph/<slugified-title>"

checkout default branch
pull default branch
checkout new ralph branch

loop_until_done(work, RalphStrategy, vcs, options)

if no changes:
  log warning
  → cleanup: return to default branch, delete ralph branch

if changes:
  push
  open draft PR with goal and completion status in body

  if converged:
    log success

  if not converged:
    log warning with iteration count
    post comment on PR warning that work may be incomplete

  → return to default branch

on any exception:
  → cleanup: return to default branch, delete ralph branch if not pushed
```

---

## Behavioral invariants

- Always returns to the default branch on exit, whether successful or not.
- The ralph branch is deleted if nothing was pushed (early return or exception).
- PRs are opened as drafts — the user must review before merging.
- Uncommitted changes are rejected upfront rather than risking a dirty merge.
- Individual iteration commits are made by the strategy (see
  [loop-engine.md](loop-engine.md)), not by the pipeline. The pipeline does not
  add a final commit — the strategy's per-iteration commits are the record.

---

## Completion vs. incomplete

Ralph distinguishes two outcomes:

### Converged

The agent output `##DONE##` on its own line during an iteration, signaling
that the goal is fully achieved. The PR body says "completed".

### Did not converge

The agent hit `max_iterations` without signaling completion. The PR body says
"stopped after N steps". An additional comment is posted on the PR:

> ⚠️ Ralph did not signal completion after N iterations.
> The work may be incomplete — review carefully before merging.

Both outcomes open a draft PR. The distinction is informational — the human
decides whether to merge.

---

## Branch naming

`ralph/<slugified-title>`, where the slug follows the same rules as fix:
lowercase, non-alphanumeric replaced with hyphens, leading/trailing hyphens
stripped, max 50 characters.

---

## Relationship to plan

The `plan` pipeline produces a structured plan file in `.plans/`. Ralph
consumes it via `--plan`. The plan file becomes the `WorkSpec.body` — Ralph
has no special awareness of plan structure. The plan's acceptance criteria
matter because the agent uses them to decide whether to output `##DONE##`.

The two pipelines are decoupled: ralph works equally well with a freeform
`--prompt` or `--file`. Plans are an optional upstream that improves ralph's
effectiveness by providing structured goals and acceptance criteria.
