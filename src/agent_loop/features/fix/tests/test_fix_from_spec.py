"""Tests for fix_from_spec — antagonistic loop from file/prompt input."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from agent_loop.domain.config import Config
from agent_loop.domain.context import AppContext
from agent_loop.domain.errors import AgentLoopError
from agent_loop.domain.loop.work import from_file, from_prompt
from agent_loop.domain.models.issues import FoundIssue, Issue
from agent_loop.features.fix.command import fix_from_spec


class StubAgent:
    """AgentBackend stub that returns preset responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses: Iterator[str] = iter(responses)
        self.prompts: list[str] = []

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return next(self._responses)


class StubVCS:
    """VCSBackend stub tracking branch and commit operations."""

    def __init__(self, *, diffs: list[str], uncommitted: bool = False) -> None:
        self._diffs: Iterator[str] = iter(diffs)
        self._uncommitted = uncommitted
        self.checkouts: list[str] = []
        self.pulls: list[str] = []
        self.new_branches: list[str] = []
        self.commits: list[str] = []
        self.pushes: list[str] = []
        self.deleted_branches: list[str] = []

    def has_uncommitted_changes(self) -> bool:
        return self._uncommitted

    def stage_all(self) -> None:
        pass

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
    """IssueTracker stub tracking PR operations.

    Only the methods used by fix_from_spec are implemented. The rest raise
    NotImplementedError to catch unexpected calls.
    """

    def __init__(self) -> None:
        self.opened_prs: list[dict[str, object]] = []
        self.pr_comments: list[tuple[str, str]] = []

    def get_default_branch(self) -> str:
        return "main"

    def open_pr(self, title: str, body: str, head: str, *, draft: bool = False) -> str:
        self.opened_prs.append({"title": title, "body": body, "head": head, "draft": draft})
        return f"PR#{len(self.opened_prs)}"

    def comment_on_pr(self, pr_ref: str, body: str) -> None:
        self.pr_comments.append((pr_ref, body))

    # --- unused protocol methods (raise if called unexpectedly) ---

    def list_open_titles(self) -> set[str]:
        raise NotImplementedError

    def create_issue(self, found: FoundIssue) -> None:
        raise NotImplementedError

    def list_ready_issues(self) -> list[Issue]:
        raise NotImplementedError

    def list_awaiting_review(self) -> list[Issue]:
        raise NotImplementedError

    def get_issue(self, number: int) -> Issue | None:
        raise NotImplementedError

    def is_ready_to_fix(self, issue: Issue) -> bool:
        raise NotImplementedError

    def is_claimed(self, issue: Issue) -> bool:
        raise NotImplementedError

    def claim_issue(self, number: int) -> None:
        raise NotImplementedError

    def release_issue(self, number: int) -> None:
        raise NotImplementedError

    def remove_ready_label(self, number: int) -> None:
        raise NotImplementedError

    def comment_on_issue(self, number: int, body: str) -> None:
        raise NotImplementedError


def _make_ctx(
    vcs: StubVCS,
    tracker: StubTracker | None = None,
    config: Config | None = None,
) -> AppContext:
    return AppContext(
        project_dir=Path("/fake"),
        config=config or Config(),
        tracker=tracker or StubTracker(),
        vcs=vcs,
    )


class TestFixFromSpec:
    def test_rejects_uncommitted_changes(self) -> None:
        vcs = StubVCS(diffs=[], uncommitted=True)
        ctx = _make_ctx(vcs)
        work = from_prompt("do something")

        with pytest.raises(AgentLoopError, match="uncommitted"):
            fix_from_spec(ctx, work, StubAgent([]), StubAgent([]))

    def test_approved_first_try_opens_draft_pr(self) -> None:
        vcs = StubVCS(diffs=["diff content", "diff content"])
        tracker = StubTracker()
        ctx = _make_ctx(vcs, tracker)
        work = from_prompt("handle edge case in parser")

        fix_from_spec(
            ctx,
            work,
            edit_agent=StubAgent(["fixed it"]),
            review_agent=StubAgent(["**Verdict**: LGTM"]),
        )

        # Branch lifecycle
        assert vcs.checkouts[0] == "main"
        assert vcs.pulls == ["main"]
        assert len(vcs.new_branches) == 1
        assert vcs.new_branches[0].startswith("fix/")
        assert len(vcs.commits) == 1
        assert len(vcs.pushes) == 1

        # PR opened as draft
        assert len(tracker.opened_prs) == 1
        pr = tracker.opened_prs[0]
        assert pr["draft"] is True
        assert "handle edge case in parser" in str(pr["body"])
        assert "converged" in str(pr["body"])

        # Review trail posted
        assert len(tracker.pr_comments) == 1

        # Returns to default branch
        assert vcs.checkouts[-1] == "main"

    def test_no_changes_cleans_up_branch(self) -> None:
        # Empty diffs → no changes
        vcs = StubVCS(diffs=["", ""])
        tracker = StubTracker()
        ctx = _make_ctx(vcs, tracker)
        work = from_prompt("do something")

        fix_from_spec(
            ctx,
            work,
            edit_agent=StubAgent(["nothing needed"]),
            review_agent=StubAgent([]),
        )

        # No PR opened
        assert len(tracker.opened_prs) == 0
        # Branch cleaned up
        assert len(vcs.deleted_branches) == 1
        # Returns to default branch
        assert vcs.checkouts[-1] == "main"

    def test_from_file_input(self, tmp_path: Path) -> None:
        spec = tmp_path / "spec.md"
        spec.write_text("# Fix the parser\n\nHandle edge cases.\n")
        work = from_file(spec)

        vcs = StubVCS(diffs=["diff", "diff"])
        tracker = StubTracker()
        ctx = _make_ctx(vcs, tracker)

        fix_from_spec(
            ctx,
            work,
            edit_agent=StubAgent(["done"]),
            review_agent=StubAgent(["**Verdict**: LGTM"]),
        )

        assert tracker.opened_prs[0]["title"] == "Fix: Fix the parser"

    def test_unconverged_opens_pr_with_warning(self) -> None:
        vcs = StubVCS(diffs=["diff", "diff", "diff", "diff"])
        tracker = StubTracker()
        ctx = _make_ctx(vcs, tracker, config=Config(max_iterations=1))
        work = from_prompt("tricky fix")

        fix_from_spec(
            ctx,
            work,
            edit_agent=StubAgent(["attempt"]),
            review_agent=StubAgent(["**Verdict**: CONCERNS\n\nStill wrong."]),
        )

        # PR still opened (with unconverged status)
        assert len(tracker.opened_prs) == 1
        assert "stopped after" in str(tracker.opened_prs[0]["body"])
