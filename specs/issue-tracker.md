# IssueTracker Protocol

The issue-platform port. Abstracts everything the analyze and fix pipelines need
from an issue tracker: listing, creating, labeling, PR creation, and commenting.

The engine (`implement_and_review`) does NOT depend on this protocol — it only
depends on `AgentBackend` and `VCSBackend`. `IssueTracker` is a pipeline-level
concern.

---

## Protocol definition

```
IssueTracker:

  -- analyze pipeline

  list_open_titles()                          -> set<string>
  create_issue(found: FoundIssue)             -> void

  -- fix pipeline

  list_ready_issues()                         -> list<Issue>
  list_awaiting_review()                      -> list<Issue>
  get_issue(number: integer)                  -> Issue | null
  is_ready_to_fix(issue: Issue)               -> bool
  is_claimed(issue: Issue)                    -> bool
  claim_issue(number: integer)                -> void
  release_issue(number: integer)              -> void
  remove_ready_label(number: integer)         -> void
  comment_on_issue(number: integer, body: string) -> void
  get_default_branch()                        -> string
  open_pr(title: string, body: string, head: string, draft?: bool) -> string
  comment_on_pr(pr_ref: string, body: string) -> void
```

---

## Contract

- `list_ready_issues()` excludes issues already claimed (in-progress). Callers
  do not need to filter.
- `list_awaiting_review()` returns issues pending human triage. Used by the
  watch loop for backpressure — analysis is skipped when this count meets the cap.
- `get_issue()` returns null rather than raising for a missing issue, so
  the `--issue N` code path can emit a clean user-facing message.
- `is_ready_to_fix()` / `is_claimed()` check workflow state on an already-fetched
  `Issue`. Used as guards in the fix pipeline before entering `BranchSession`.
- `claim_issue()` / `release_issue()` are the locking pair. `release_issue()`
  must always be called on failure (the fix pipeline's cleanup block handles this).
- `open_pr()` returns a string reference (branch name, PR number, or URL —
  adapter-defined) that can be passed back to `comment_on_pr()`. Callers treat
  it as opaque.
- `create_issue()` is responsible for ensuring any required labels/tags exist
  before creating the issue. Callers do not need a separate setup step.

---

## Known adapters

### `GitHubTracker` (current)

Wraps the `gh` CLI. Represents workflow state via GitHub issue labels:

```
Issue lifecycle (agent-reported):
  created with [agent-reported, needs-human-review]
    → human adds ready-to-fix
      → agent adds agent-fix-in-progress (claim)
        → PR merged, issue closed

Issue lifecycle (human-reported):
  created manually with ready-to-fix
    → agent adds agent-fix-in-progress (claim)
      → PR merged, issue closed
```

- `needs-human-review` — pending triage; drives `list_awaiting_review()`
- `ready-to-fix` — approved for fixing; drives `list_ready_issues()`
- `agent-fix-in-progress` — concurrency lock; added by `claim_issue()`, removed by `release_issue()`
- `agent-reported` — permanent origin marker

`open_pr()` returns the branch name, which is passed as-is to `comment_on_pr()`.

### Future adapters

- `JiraTracker` — wraps `jira-cli` CLI or Jira API
- `LinearTracker` — wraps Linear API; PRs map to branches linked to Linear issues
- `StubTracker` — in-memory implementation for testing; records calls for assertion
