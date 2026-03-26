"""BranchSession — concrete context manager for the fix pipeline's git workflow.

Handles branch creation, label locking, and cleanup so that fix_single_issue
can focus on the issue-resolution logic rather than branch bookkeeping.
"""

from types import TracebackType

from agent_loop.domain.issues import Issue
from agent_loop.domain.protocols import IssueTracker, VCSBackend


class BranchSession:
    """Own the branch lifecycle and issue lock for a single fix attempt.

    On entry:
      - Pull the default branch so we start from a clean base.
      - Claim the issue (add the in-progress label lock).
      - Checkout the fix branch, resetting it if a prior attempt left it behind.

    On exit:
      - Always return to the default branch.
      - If commit_and_push() was never called (no changes, or an exception mid-fix),
        delete the branch and release the issue lock so it can be retried.
    """

    def __init__(self, issue: Issue, tracker: IssueTracker, vcs: VCSBackend) -> None:
        self._issue = issue
        self._tracker = tracker
        self._vcs = vcs
        self._branch = f"fix/issue-{issue.number}"
        self._default_branch: str = ""
        self._pushed = False

    def __enter__(self) -> "BranchSession":
        self._default_branch = self._tracker.get_default_branch()

        # Pull before claiming so a network failure doesn't leave the lock stuck.
        self._vcs.checkout(self._default_branch)
        self._vcs.pull(self._default_branch)

        self._tracker.claim_issue(self._issue.number)
        self._vcs.checkout_new_branch(self._branch)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self._vcs.checkout(self._default_branch)

        # Clean up if no commit was pushed — covers both early returns and exceptions.
        if not self._pushed:
            self._vcs.delete_branch(self._branch)
            self._tracker.release_issue(self._issue.number)

    def commit_and_push(self) -> None:
        """Commit all staged changes and push the fix branch."""
        number = self._issue.number
        title = self._issue.title
        self._vcs.commit(f"fix: address issue #{number} - {title}")
        self._vcs.push(self._branch)
        self._pushed = True

    @property
    def branch(self) -> str:
        return self._branch
