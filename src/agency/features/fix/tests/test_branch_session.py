"""Tests for BranchSession — branch lifecycle and issue lock management."""

import pytest

from agency.domain.ports.tests.stubs import StubTracker, StubVCS, make_issue
from agency.features.fix.branch_session import BranchSession


class TestBranchSessionSuccess:
    def test_enters_fix_branch_and_claims_issue(self) -> None:
        issue = make_issue(number=42)
        tracker = StubTracker()
        vcs = StubVCS()

        with BranchSession(issue, tracker, vcs):
            pass

        assert vcs.checkouts[0] == "main"
        assert vcs.pulls == ["main"]
        assert tracker.claimed == [42]
        assert vcs.new_branches == ["fix/issue-42"]

    def test_returns_to_default_branch_on_exit(self) -> None:
        issue = make_issue(number=1)
        tracker = StubTracker(default_branch="develop")
        vcs = StubVCS()

        with BranchSession(issue, tracker, vcs):
            pass

        assert vcs.checkouts[-1] == "develop"

    def test_commit_and_push_prevents_cleanup(self) -> None:
        issue = make_issue(number=7)
        tracker = StubTracker()
        vcs = StubVCS()

        with BranchSession(issue, tracker, vcs) as session:
            session.commit_and_push()

        # Branch not deleted, issue not released
        assert vcs.deleted_branches == []
        assert tracker.released == []
        # But commit and push happened
        assert len(vcs.commits) == 1
        assert vcs.pushes == ["fix/issue-7"]

    def test_branch_property(self) -> None:
        issue = make_issue(number=99)
        tracker = StubTracker()
        vcs = StubVCS()

        with BranchSession(issue, tracker, vcs) as session:
            assert session.branch == "fix/issue-99"


class TestBranchSessionCleanup:
    def test_deletes_branch_and_releases_issue_when_not_pushed(self) -> None:
        issue = make_issue(number=5)
        tracker = StubTracker()
        vcs = StubVCS()

        with BranchSession(issue, tracker, vcs):
            pass  # no commit_and_push

        assert vcs.deleted_branches == ["fix/issue-5"]
        assert tracker.released == [5]

    def test_cleans_up_on_exception(self) -> None:
        issue = make_issue(number=3)
        tracker = StubTracker()
        vcs = StubVCS()
        msg = "boom"

        with pytest.raises(RuntimeError, match=msg), BranchSession(issue, tracker, vcs):
            raise RuntimeError(msg)

        # Cleanup still happened
        assert vcs.deleted_branches == ["fix/issue-3"]
        assert tracker.released == [3]
        assert vcs.checkouts[-1] == "main"
