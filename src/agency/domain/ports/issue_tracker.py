"""IssueTracker port — the issue-platform interface.

Abstracts everything the analyze and fix pipelines need from an issue tracker:
listing, creating, labeling, PR creation, and commenting. The engine
(loop_until_done) does NOT depend on this protocol — it only depends on
AgentBackend and VCSBackend. IssueTracker is a pipeline-level concern.

Known adapters:
- GitHubTracker (io/adapters/github.py) — wraps the gh CLI
"""

from typing import Protocol

from agency.domain.models.issues import FoundIssue, Issue


class IssueTracker(Protocol):
    """Issue platform operations used by the analyze and fix pipelines.

    Contract:
    - list_ready_issues() excludes issues already claimed (in-progress).
      Callers do not need to filter.
    - list_awaiting_review() returns issues pending human triage. Used by the
      watch loop for backpressure — analysis is skipped when this count meets
      the cap.
    - get_issue() returns None rather than raising for a missing issue, so the
      --issue N code path can emit a clean user-facing message.
    - is_ready_to_fix() / is_claimed() check workflow state on an
      already-fetched Issue. Used as guards in the fix pipeline before entering
      BranchSession.
    - claim_issue() / release_issue() are the locking pair. release_issue()
      must always be called on failure (the fix pipeline's cleanup block
      handles this).
    - open_pr() returns a string reference (branch name, PR number, or URL —
      adapter-defined) that can be passed back to comment_on_pr(). Callers
      treat it as opaque.
    - create_issue() is responsible for ensuring any required labels/tags exist
      before creating the issue. Callers do not need a separate setup step.
    """

    # --- analyze pipeline ---

    def list_open_titles(self) -> set[str]:
        """Return titles of all open issues (used for deduplication)."""
        ...

    def create_issue(self, found: FoundIssue) -> None:
        """File a new issue discovered by the analyzer."""
        ...

    # --- fix pipeline ---

    def list_ready_issues(self) -> list[Issue]:
        """Return issues approved for fixing that are not already claimed."""
        ...

    def list_awaiting_review(self) -> list[Issue]:
        """Return issues waiting for human review (backpressure check for the watch loop)."""
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
        """Mark the issue as in-progress to prevent concurrent attempts."""
        ...

    def release_issue(self, number: int) -> None:
        """Remove the in-progress claim (called on failure cleanup)."""
        ...

    def remove_ready_label(self, number: int) -> None:
        """Remove the ready-to-fix label when no changes were made."""
        ...

    def comment_on_issue(self, number: int, body: str) -> None:
        """Post a comment on an issue."""
        ...

    def get_default_branch(self) -> str:
        """Return the repo's default branch name."""
        ...

    def open_pr(self, title: str, body: str, head: str, *, draft: bool = False) -> str:
        """Open a pull request. Returns a reference usable by comment_on_pr."""
        ...

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        """Post a comment on an open pull request."""
        ...
