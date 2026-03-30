"""VCSBackend backed by the git CLI."""

from pathlib import Path

from agent_loop.io.transports.process import run


class GitBackend:
    """VCSBackend implementation backed by the git CLI.

    Implements the VCSBackend protocol and exposes the branch workflow operations needed
    by fix_single_issue.
    """

    def __init__(self, project_dir: Path) -> None:
        """Bind to the given project directory for all git operations."""
        self._project_dir = project_dir

    def _git(self, *args: str) -> str:
        return run(["git", *args], cwd=self._project_dir)

    def has_uncommitted_changes(self) -> bool:
        """Return True if the working tree or index has uncommitted changes."""
        output = self._git("status", "--porcelain")
        return output.strip() != ""

    def stage_all(self) -> None:
        """Stage all current changes."""
        self._git("add", "-A")

    def diff_staged(self) -> str:
        """Return the staged diff."""
        return self._git("diff", "--cached")

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch."""
        self._git("checkout", branch)

    def pull(self, branch: str) -> None:
        """Fast-forward pull from origin."""
        self._git("pull", "--ff-only", "origin", branch)

    def checkout_new_branch(self, branch: str) -> None:
        """Checkout branch, resetting it if a prior attempt left it behind."""
        self._git("checkout", "-B", branch)

    def commit(self, message: str) -> None:
        """Commit all staged changes."""
        self._git("commit", "-m", message)

    def push(self, branch: str) -> None:
        """Force-push with lease to origin."""
        self._git("push", "--force-with-lease", "-u", "origin", branch)

    def delete_branch(self, branch: str) -> None:
        """Delete a local branch."""
        self._git("branch", "-D", branch)
