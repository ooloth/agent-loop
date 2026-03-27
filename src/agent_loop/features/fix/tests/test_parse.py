"""Tests for pure parsing functions used by the fix pipeline."""

from agent_loop.features.fix.engine import parse_review_verdict, summarize_feedback

# --- parse_review_verdict ---


class TestParseReviewVerdict:
    def test_lgtm_uppercase(self) -> None:
        assert parse_review_verdict("**Verdict**: LGTM") is True

    def test_lgtm_mixed_case(self) -> None:
        assert parse_review_verdict("**Verdict**: lgtm") is True

    def test_concerns(self) -> None:
        assert parse_review_verdict("**Verdict**: CONCERNS") is False

    def test_no_verdict(self) -> None:
        assert parse_review_verdict("This looks fine.") is False

    def test_lgtm_in_word(self) -> None:
        # "LGTM" must be a whole word
        assert parse_review_verdict("not_LGTM_here") is False

    def test_lgtm_as_word_boundary(self) -> None:
        assert parse_review_verdict("Verdict: LGTM!") is True


# --- summarize_feedback ---


class TestSummarizeFeedback:
    def test_required_changes_section(self) -> None:
        feedback = "#### 🔧 Required Changes\n- Fix the return type"
        assert summarize_feedback(feedback) == "Fix the return type"

    def test_concerns_verdict_fallback(self) -> None:
        feedback = "**Verdict**: CONCERNS\n\n- The approach is wrong"
        assert summarize_feedback(feedback) == "The approach is wrong"

    def test_first_substantive_line_fallback(self) -> None:
        feedback = "# Review\n**Bold header**\n---\nThis is the issue."
        assert summarize_feedback(feedback) == "This is the issue."

    def test_all_headers_returns_no_details(self) -> None:
        feedback = "# Header\n**Bold**\n---\n> Quote"
        assert summarize_feedback(feedback) == "(no details)"

    def test_truncation(self) -> None:
        long_feedback = "#### 🔧 Required Changes\n" + "x" * 100
        result = summarize_feedback(long_feedback, max_len=50)
        assert len(result) == 50
        assert result.endswith("…")

    def test_strips_bold_markdown(self) -> None:
        feedback = "#### 🔧 Required Changes\n- **Important** fix needed"
        assert summarize_feedback(feedback) == "Important fix needed"

    def test_strips_inline_code(self) -> None:
        feedback = "#### 🔧 Required Changes\n- Fix `my_func()` return"
        assert summarize_feedback(feedback) == "Fix my_func() return"
