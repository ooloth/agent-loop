"""Tests for cmd_fix — issue-based fix pipeline."""

from agency.domain.ports.tests.stubs import StubAgent, StubTracker, StubVCS, make_issue
from agency.features.fix.command import cmd_fix
from agency.features.tests.context import make_ctx


class TestCmdFix:
    def test_fixes_ready_issue_and_opens_pr(self) -> None:
        issue = make_issue(number=42, title="Fix parser bug")
        tracker = StubTracker(ready_issues=[issue], issues={42: issue})
        vcs = StubVCS(diffs=["diff content", "diff content"])
        ctx = make_ctx(tracker=tracker, vcs=vcs)

        cmd_fix(
            ctx,
            edit_agent=StubAgent(["fixed the parser"]),
            review_agent=StubAgent(["**Verdict**: LGTM"]),
        )

        assert tracker.claimed == [42]
        assert len(tracker.opened_prs) == 1
        assert "Fix #42" in str(tracker.opened_prs[0]["title"])
        assert len(tracker.pr_comments) == 1

    def test_no_ready_issues(self) -> None:
        tracker = StubTracker(ready_issues=[])
        ctx = make_ctx(tracker=tracker)

        cmd_fix(ctx, edit_agent=StubAgent(), review_agent=StubAgent())

        assert tracker.opened_prs == []

    def test_skips_claimed_issue(self) -> None:
        issue = make_issue(
            number=10,
            labels=frozenset({"ready-to-fix", "agent-fix-in-progress"}),
        )
        tracker = StubTracker(issues={10: issue})
        ctx = make_ctx(tracker=tracker)

        cmd_fix(ctx, edit_agent=StubAgent(), review_agent=StubAgent(), issue_number=10)

        assert tracker.claimed == []
        assert tracker.opened_prs == []

    def test_no_changes_releases_issue(self) -> None:
        issue = make_issue(number=5, title="Already fixed")
        tracker = StubTracker(ready_issues=[issue], issues={5: issue})
        vcs = StubVCS(diffs=["", ""])
        ctx = make_ctx(tracker=tracker, vcs=vcs)

        cmd_fix(
            ctx,
            edit_agent=StubAgent(["nothing to do"]),
            review_agent=StubAgent([]),
        )

        assert tracker.opened_prs == []
        assert tracker.removed_ready == [5]
        assert tracker.released == [5]
