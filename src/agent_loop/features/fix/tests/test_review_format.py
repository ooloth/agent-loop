"""Tests for the review comment formatter."""

from agent_loop.features.fix.engine import ReviewEntry
from agent_loop.features.fix.review import format_review_comment


class TestFormatReviewComment:
    def test_single_approval(self) -> None:
        log: list[ReviewEntry] = [{"iteration": 1, "approved": True, "feedback": "Looks great."}]
        result = format_review_comment(log, converged=True, max_iterations=5)

        assert "✅ Passed after 1 iteration" in result
        assert "**1** iteration " in result
        assert "**1** approved" in result
        assert "**0** requested changes" in result
        assert "Looks great." in result
        # Single iteration should not be in a <details> block
        assert "<details>" not in result

    def test_two_iterations_converged(self) -> None:
        log: list[ReviewEntry] = [
            {"iteration": 1, "approved": False, "feedback": "Fix the bug."},
            {"iteration": 2, "approved": True, "feedback": "LGTM now."},
        ]
        result = format_review_comment(log, converged=True, max_iterations=5)

        assert "✅ Passed after 2 iterations" in result
        assert "**1** approved" in result
        assert "**1** requested changes" in result
        # First iteration should be collapsed
        assert "<details>" in result
        assert "Fix the bug." in result
        # Last iteration should be open
        assert "### ✅ Iteration 2" in result
        assert "LGTM now." in result

    def test_did_not_converge(self) -> None:
        log: list[ReviewEntry] = [
            {"iteration": 1, "approved": False, "feedback": "Nope."},
            {"iteration": 2, "approved": False, "feedback": "Still no."},
        ]
        result = format_review_comment(log, converged=False, max_iterations=2)

        assert "⚠️ Did not converge after 2 iterations" in result
        assert "**0** approved" in result
        assert "**2** requested changes" in result

    def test_empty_log(self) -> None:
        result = format_review_comment([], converged=False, max_iterations=5)
        assert "**0** iterations" in result
