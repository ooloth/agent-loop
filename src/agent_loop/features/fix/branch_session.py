"""BranchSession — concrete context manager for the fix pipeline's git workflow.

Handles branch creation, label locking, and cleanup so that fix_single_issue
can focus on the issue-resolution logic rather than branch bookkeeping.
"""

from types import TracebackType
from typing import Self

from agent_loop.domain.errors import AgentLoopError
from agent_loop.domain.models.issues import Issue
from agent_loop.domain.ports.issue_tracker import IssueTracker
from agent_loop.domain.ports.vcs_backend import VCSBackend
from agent_loop.io.observability.logging import log


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

    Invariants:
      - Pull happens before claim, so a network failure doesn't leave the lock
        stuck on an issue.
      - commit_and_push() sets a flag that prevents cleanup from deleting the
        branch and releasing the lock — the PR now owns the lifecycle.
      - Each cleanup step is independently try/caught — a failure to delete the
        branch does not prevent releasing the issue lock.
      - Branch name is deterministic from the issue number: fix/issue-{number}.
    """

    def __init__(self, issue: Issue, tracker: IssueTracker, vcs: VCSBackend) -> None:
        """Bind the issue and infrastructure needed for branch lifecycle."""
        self._issue = issue
        self._tracker = tracker
        self._vcs = vcs
        self._branch = f"fix/issue-{issue.number}"
        self._default_branch: str = ""
        self._pushed = False

    def __enter__(self) -> Self:
        log.debug("BranchSession: entering %s for issue #%d", self._branch, self._issue.number)
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
        log.debug("BranchSession: exiting %s, pushed=%s", self._branch, self._pushed)
        try:
            self._vcs.checkout(self._default_branch)
        except AgentLoopError:
            log.exception("BranchSession: failed to checkout %s", self._default_branch)

        # Clean up if no commit was pushed — covers both early returns and exceptions.
        if not self._pushed:
            try:
                self._vcs.delete_branch(self._branch)
            except AgentLoopError:
                log.exception("BranchSession: failed to delete branch %s", self._branch)
            try:
                self._tracker.release_issue(self._issue.number)
            except AgentLoopError:
                log.exception("BranchSession: failed to release issue #%d", self._issue.number)

    def commit_and_push(self) -> None:
        """Commit all staged changes and push the fix branch."""
        number = self._issue.number
        title = self._issue.title
        self._vcs.commit(f"fix: address issue #{number} - {title}")
        self._vcs.push(self._branch)
        self._pushed = True

    @property
    def branch(self) -> str:
        """The fix branch name for this issue."""
        return self._branch
