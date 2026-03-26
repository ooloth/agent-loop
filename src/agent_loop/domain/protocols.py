"""Ports — interfaces the domain depends on, implemented by infra adapters."""

from typing import Protocol

from agent_loop.domain.issues import FoundIssue, Issue


class AgentBackend(Protocol):
    """Run a prompt and return the response. Abstracts the AI provider."""

    def run(self, prompt: str) -> str: ...


class VCSBackend(Protocol):
    """Minimal VCS operations needed by the implement→review engine."""

    def stage_all(self) -> None:
        """Stage all current changes (git add -A equivalent)."""
        ...

    def diff_staged(self) -> str:
        """Return the staged diff. Empty string means no staged changes."""
        ...


class IssueTracker(Protocol):
    """Issue platform operations used by the analyze and fix pipelines."""

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

    def open_pr(self, title: str, body: str, head: str) -> str:
        """Open a pull request. Returns a reference usable by comment_on_pr."""
        ...

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        """Post a comment on an open pull request."""
        ...
