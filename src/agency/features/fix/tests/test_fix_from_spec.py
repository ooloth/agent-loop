"""Tests for fix_from_spec — antagonistic loop from file/prompt input."""

from pathlib import Path

import pytest

from agency.domain.config import Config
from agency.domain.errors import AgentLoopError
from agency.domain.loop.work import from_file, from_prompt
from agency.domain.ports.tests.stubs import StubAgent, StubTracker, StubVCS
from agency.features.fix.command import fix_from_spec
from agency.features.tests.context import make_ctx


class TestFixFromSpec:
    def test_rejects_uncommitted_changes(self) -> None:
        vcs = StubVCS(uncommitted=True)
        ctx = make_ctx(vcs=vcs)
        work = from_prompt("do something")

        with pytest.raises(AgentLoopError, match="uncommitted"):
            fix_from_spec(ctx, work, StubAgent([]), StubAgent([]))

    def test_approved_first_try_opens_draft_pr(self) -> None:
        vcs = StubVCS(diffs=["diff content", "diff content"])
        tracker = StubTracker()
        ctx = make_ctx(vcs=vcs, tracker=tracker)
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
        ctx = make_ctx(vcs=vcs, tracker=tracker)
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
        ctx = make_ctx(vcs=vcs, tracker=tracker)

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
        ctx = make_ctx(vcs=vcs, tracker=tracker, config=Config(max_iterations=1))
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
