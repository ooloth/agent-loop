"""Tests for cmd_analyze — dedup logic and issue creation."""

from agency.domain.ports.tests.stubs import StubAgent, StubTracker
from agency.features.analyze.command import cmd_analyze
from agency.features.tests.context import make_ctx

ANALYSIS_WITH_TWO_ISSUES = """```json
[
  {
    "title": "Missing error handling in parser",
    "body": "Crashes on empty input.",
    "labels": ["bug"]
  },
  {
    "title": "Add type hints to utils",
    "body": "No annotations in utils.py.",
    "labels": ["enhancement"]
  }
]
```"""

ANALYSIS_WITH_NO_ISSUES = "```json\n[]\n```"


class TestCmdAnalyze:
    def test_creates_new_issues(self) -> None:
        tracker = StubTracker()
        ctx = make_ctx(tracker=tracker)
        agent = StubAgent([ANALYSIS_WITH_TWO_ISSUES])

        cmd_analyze(ctx, agent)

        assert len(tracker.created_issues) == 2
        assert tracker.created_issues[0].title == "Missing error handling in parser"
        assert tracker.created_issues[1].title == "Add type hints to utils"

    def test_skips_duplicate_titles(self) -> None:
        tracker = StubTracker(open_titles={"Missing error handling in parser"})
        ctx = make_ctx(tracker=tracker)
        agent = StubAgent([ANALYSIS_WITH_TWO_ISSUES])

        cmd_analyze(ctx, agent)

        assert len(tracker.created_issues) == 1
        assert tracker.created_issues[0].title == "Add type hints to utils"

    def test_no_issues_found(self) -> None:
        tracker = StubTracker()
        ctx = make_ctx(tracker=tracker)
        agent = StubAgent([ANALYSIS_WITH_NO_ISSUES])

        cmd_analyze(ctx, agent)

        assert len(tracker.created_issues) == 0
