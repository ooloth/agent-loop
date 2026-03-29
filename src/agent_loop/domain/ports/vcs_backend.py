"""VCSBackend port — the version-control interface."""

from typing import Protocol


class VCSBackend(Protocol):
    """VCS operations used by the engine and fix pipeline."""

    def has_uncommitted_changes(self) -> bool:
        """Return True if the working tree or index has uncommitted changes."""
        ...

    def stage_all(self) -> None:
        """Stage all current changes (git add -A equivalent)."""
        ...

    def diff_staged(self) -> str:
        """Return the staged diff. Empty string means no staged changes."""
        ...

    def checkout(self, branch: str) -> None:
        """Switch to an existing branch."""
        ...

    def pull(self, branch: str) -> None:
        """Pull the latest changes for a branch from the remote."""
        ...

    def checkout_new_branch(self, branch: str) -> None:
        """Create and switch to a new branch, resetting it if it already exists."""
        ...

    def commit(self, message: str) -> None:
        """Commit all staged changes."""
        ...

    def push(self, branch: str) -> None:
        """Push a branch to the remote."""
        ...

    def delete_branch(self, branch: str) -> None:
        """Delete a local branch."""
        ...
