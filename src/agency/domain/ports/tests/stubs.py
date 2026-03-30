"""Shared test stubs implementing the domain ports.

These stubs record interactions for assertion and return preset responses.
They are the canonical test doubles — individual test files should import
from here rather than defining their own.
"""

from collections.abc import Iterator

from agency.domain.models.issues import FoundIssue, Issue


class StubAgent:
    """AgentBackend stub that returns preset responses in order."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses: Iterator[str] = iter(responses or [])
        self.prompts: list[str] = []

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return next(self._responses)


class StubVCS:
    """VCSBackend stub tracking branch and commit operations."""

    def __init__(self, *, diffs: list[str] | None = None, uncommitted: bool = False) -> None:
        self._diffs: Iterator[str] = iter(diffs or [])
        self._uncommitted = uncommitted
        self.checkouts: list[str] = []
        self.pulls: list[str] = []
        self.new_branches: list[str] = []
        self.commits: list[str] = []
        self.pushes: list[str] = []
        self.deleted_branches: list[str] = []
        self.staged: int = 0

    def has_uncommitted_changes(self) -> bool:
        return self._uncommitted

    def stage_all(self) -> None:
        self.staged += 1

    def diff_staged(self) -> str:
        return next(self._diffs)

    def checkout(self, branch: str) -> None:
        self.checkouts.append(branch)

    def pull(self, branch: str) -> None:
        self.pulls.append(branch)

    def checkout_new_branch(self, branch: str) -> None:
        self.new_branches.append(branch)

    def commit(self, message: str) -> None:
        self.commits.append(message)

    def push(self, branch: str) -> None:
        self.pushes.append(branch)

    def delete_branch(self, branch: str) -> None:
        self.deleted_branches.append(branch)


class StubTracker:
    """IssueTracker stub tracking all issue and PR operations."""

    def __init__(
        self,
        *,
        open_titles: set[str] | None = None,
        ready_issues: list[Issue] | None = None,
        awaiting_review: list[Issue] | None = None,
        issues: dict[int, Issue] | None = None,
        default_branch: str = "main",
    ) -> None:
        self._open_titles = open_titles or set()
        self._ready_issues = ready_issues or []
        self._awaiting_review = awaiting_review or []
        self._issues = issues or {}
        self._default_branch = default_branch

        self.created_issues: list[FoundIssue] = []
        self.claimed: list[int] = []
        self.released: list[int] = []
        self.removed_ready: list[int] = []
        self.issue_comments: list[tuple[int, str]] = []
        self.opened_prs: list[dict[str, object]] = []
        self.pr_comments: list[tuple[str, str]] = []

    def list_open_titles(self) -> set[str]:
        return self._open_titles

    def create_issue(self, found: FoundIssue) -> None:
        self.created_issues.append(found)

    def list_ready_issues(self) -> list[Issue]:
        return self._ready_issues

    def list_awaiting_review(self) -> list[Issue]:
        return self._awaiting_review

    def get_issue(self, number: int) -> Issue | None:
        return self._issues.get(number)

    def is_ready_to_fix(self, issue: Issue) -> bool:
        return "ready-to-fix" in issue.labels

    def is_claimed(self, issue: Issue) -> bool:
        return "agent-fix-in-progress" in issue.labels

    def claim_issue(self, number: int) -> None:
        self.claimed.append(number)

    def release_issue(self, number: int) -> None:
        self.released.append(number)

    def remove_ready_label(self, number: int) -> None:
        self.removed_ready.append(number)

    def comment_on_issue(self, number: int, body: str) -> None:
        self.issue_comments.append((number, body))

    def get_default_branch(self) -> str:
        return self._default_branch

    def open_pr(self, title: str, body: str, head: str, *, draft: bool = False) -> str:
        self.opened_prs.append({"title": title, "body": body, "head": head, "draft": draft})
        return head

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        self.pr_comments.append((pr_ref, body))


def make_issue(
    number: int = 1,
    title: str = "Test issue",
    body: str = "Fix the thing.",
    labels: frozenset[str] = frozenset({"ready-to-fix"}),
) -> Issue:
    """Build an Issue with sensible defaults."""
    return Issue(number=number, title=title, body=body, labels=labels)
