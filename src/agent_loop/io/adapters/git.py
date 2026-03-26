from agent_loop.io.process import run


def _git(*args: str) -> str:
    return run(["git", *args])


class GitBackend:
    """VCSBackend implementation backed by the git CLI.

    Implements the VCSBackend protocol (stage_all, diff_staged) and also
    exposes the branch workflow operations needed by fix_single_issue.
    """

    def stage_all(self) -> None:
        _git("add", "-A")

    def diff_staged(self) -> str:
        return _git("diff", "--cached")

    def checkout(self, branch: str) -> None:
        _git("checkout", branch)

    def pull(self, branch: str) -> None:
        _git("pull", "--ff-only", "origin", branch)

    def checkout_new_branch(self, branch: str) -> None:
        """Checkout branch, resetting it if a prior attempt left it behind."""
        _git("checkout", "-B", branch)

    def commit(self, message: str) -> None:
        _git("commit", "-m", message)

    def push(self, branch: str) -> None:
        _git("push", "--force-with-lease", "-u", "origin", branch)

    def delete_branch(self, branch: str) -> None:
        _git("branch", "-D", branch)
