# IssueTracker Protocol

The issue-platform port. Abstracts everything the analyze and fix pipelines need
from an issue tracker: listing, creating, labeling, PR creation, and commenting.

The engine (`implement_and_review`) does NOT depend on this protocol — it only
depends on `AgentBackend` and `VCSBackend`. `IssueTracker` is a pipeline-level
concern.

---

## Protocol definition

```python
from typing import Protocol
from agent_loop.domain.issues import Issue, FoundIssue


class IssueTracker(Protocol):

    # --- analyze pipeline ---

    def list_open_titles(self) -> set[str]:
        """Return titles of all currently open issues (for deduplication)."""
        ...

    def create_issue(self, found: FoundIssue) -> None:
        """File a new issue discovered by the analyzer."""
        ...

    # --- fix pipeline ---

    def list_ready_issues(self) -> list[Issue]:
        """Return issues approved for automated fixing, not already claimed."""
        ...

    def list_awaiting_review(self) -> list[Issue]:
        """Return issues waiting for human review (backpressure check for watch loop)."""
        ...

    def get_issue(self, number: int) -> Issue | None:
        """Fetch a single issue by number. Returns None if not found."""
        ...

    def is_ready_to_fix(self, issue: Issue) -> bool:
        """Return True if this issue is approved for fixing."""
        ...

    def is_claimed(self, issue: Issue) -> bool:
        """Return True if an agent is already working on this issue."""
        ...

    def claim_issue(self, number: int) -> None:
        """Mark the issue as in-progress (prevents concurrent attempts)."""
        ...

    def release_issue(self, number: int) -> None:
        """Remove the in-progress claim (called on failure cleanup)."""
        ...

    def remove_ready_label(self, number: int) -> None:
        """Remove the ready-to-fix label (called when no changes were made)."""
        ...

    def comment_on_issue(self, number: int, body: str) -> None:
        """Post a comment on an issue."""
        ...

    def get_default_branch(self) -> str:
        """Return the repo's default branch name (e.g. 'main')."""
        ...

    def open_pr(self, title: str, body: str, head: str) -> str:
        """Open a pull request and return a reference usable by comment_on_pr."""
        ...

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        """Post a comment on an open pull request."""
        ...
```

---

## Contract

- `list_ready_issues()` excludes issues already claimed (in-progress). Callers
  do not need to filter.
- `list_awaiting_review()` returns issues pending human triage. Used by the
  watch loop for backpressure — analysis is skipped when this count meets the cap.
- `get_issue()` returns `None` rather than raising for a missing issue, so
  the `--issue N` code path can emit a clean user-facing message.
- `is_ready_to_fix()` / `is_claimed()` check label state on an already-fetched
  `Issue`. Used as guards in the fix pipeline before entering `BranchSession`.
- `claim_issue()` / `release_issue()` are the locking pair. `release_issue()`
  must always be called on failure (the fix pipeline's `finally` block handles
  this).
- `open_pr()` returns a string reference (branch name, PR number, or URL —
  adapter-defined) that can be passed back to `comment_on_pr()`. Callers treat
  it as opaque.
- `create_issue()` is responsible for ensuring any required labels exist before
  creating the issue. Callers should not need to call a separate
  `ensure_labels()` step.

---

## Known adapters

### `GitHubTracker` (current)

Wraps the `gh` CLI via `io/process.py`'s `run()` helper. Lives in
`io/adapters/github.py`.

```python
class GitHubTracker:
    # No constructor — relies on gh picking up repo context from the working directory
    ...
```

`open_pr()` returns the branch name (used as `pr_ref` in subsequent
`gh pr comment <branch>` calls). `comment_on_pr()` calls `gh pr comment <branch>`.

#### Label lifecycle (GitHub-specific)

`GitHubTracker` maps workflow state to GitHub labels via a private `_Label`
StrEnum. Labels are created on demand (`_ensure_label`) before use.

```
Agent issue:  agent-reported + needs-human-review → ready-to-fix → agent-fix-in-progress → closed by PR
Human issue:  ready-to-fix → agent-fix-in-progress → closed by PR
```

- `agent-reported`, `needs-human-review` — permanent origin/triage labels
- `ready-to-fix` — transient; removed if agent makes no changes
- `agent-fix-in-progress` — transient lock; removed on failure via `release_issue()`

### Future adapters

- `JiraTracker` — wraps `jira-cli` CLI or Jira API
- `MondayTracker` — wraps Monday API
- `LinearTracker` — wraps Linear API; PRs map to branches linked to Linear issues
- `StubTracker` — in-memory implementation for testing; records calls for assertion
