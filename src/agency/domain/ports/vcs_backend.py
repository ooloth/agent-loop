"""VCSBackend port — the version-control interface.

Abstracts all VCS operations used by the engine and fix pipeline: staging,
diffing, branching, committing, and pushing.

Known adapters:
- GitBackend (io/adapters/git.py) — wraps the git CLI
"""

from typing import Protocol


class VCSBackend(Protocol):
    """VCS operations used by the engine and fix pipeline.

    Contract:
    - has_uncommitted_changes() checks both the working tree and the index.
      Used as a guard by pipelines that manage their own branches (fix-from-spec,
      ralph) to prevent starting work on a dirty tree.
    - stage_all() is idempotent. Calling it when nothing has changed is safe.
    - diff_staged() returns an empty string (not None, not an error) when there
      are no staged changes. Callers use the empty-string check to detect "no
      work was done" and short-circuit the review loop.
    - checkout_new_branch() resets the branch if it already exists, so a prior
      failed attempt doesn't block a retry.
    - push() uses force-with-lease semantics to avoid overwriting unexpected
      remote changes while still allowing re-pushes of amended fix branches.
    """

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
