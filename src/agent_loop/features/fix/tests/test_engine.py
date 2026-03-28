"""Tests for the implement_and_review engine using stub backends."""

from collections.abc import Iterator

from agent_loop.features.fix.engine import ImplementAndReviewInput, implement_and_review


class StubAgent:
    """AgentBackend stub that returns preset responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses: Iterator[str] = iter(responses)
        self.prompts: list[str] = []

    def run(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return next(self._responses)


class StubVCS:
    """VCSBackend stub with controllable staged diff."""

    def __init__(self, diffs: list[str]) -> None:
        self._diffs: Iterator[str] = iter(diffs)

    def stage_all(self) -> None:
        pass

    def diff_staged(self) -> str:
        return next(self._diffs)

    def checkout(self, branch: str) -> None:
        pass

    def pull(self, branch: str) -> None:
        pass

    def checkout_new_branch(self, branch: str) -> None:
        pass

    def commit(self, message: str) -> None:
        pass

    def push(self, branch: str) -> None:
        pass

    def delete_branch(self, branch: str) -> None:
        pass


def _make_task(
    implement_responses: list[str],
    review_responses: list[str],
    diffs: list[str],
    max_iterations: int = 5,
    context: str = "",
) -> tuple[ImplementAndReviewInput, list[str]]:
    events: list[str] = []
    task = ImplementAndReviewInput(
        title="Test issue",
        body="Fix the thing.",
        implement_agent=StubAgent(implement_responses),
        review_agent=StubAgent(review_responses),
        vcs=StubVCS(diffs),
        max_iterations=max_iterations,
        context=context,
        fix_prompt_template="Fix: {title}\n{body}",
        review_prompt="Review this diff.",
        on_progress=events.append,
    )
    return task, events


class TestImplementAndReview:
    def test_approved_first_try(self) -> None:
        task, events = _make_task(
            implement_responses=["fixed it"],
            review_responses=["**Verdict**: LGTM"],
            # diff_staged called twice: once in the review loop, once for has_changes
            diffs=["diff content", "diff content"],
        )
        result = implement_and_review(task)

        assert result.converged is True
        assert result.has_changes is True
        assert result.implement_response == "fixed it"
        assert len(result.review_log) == 1
        assert result.review_log[0]["approved"] is True
        assert "implementing" in events
        assert any("review_approved" in e for e in events)

    def test_no_changes_after_implementation(self) -> None:
        task, events = _make_task(
            implement_responses=["nothing to do"],
            review_responses=[],
            # Empty diff after staging → no changes
            diffs=["", ""],
        )
        result = implement_and_review(task)

        assert result.converged is False
        assert result.has_changes is False
        assert result.review_log == []
        assert "no_changes" in events

    def test_feedback_addressed_then_approved(self) -> None:
        task, events = _make_task(
            implement_responses=["first attempt", "addressed feedback"],
            review_responses=[
                "**Verdict**: CONCERNS\n\n#### 🔧 Required Changes\n- Fix the edge case",
                "**Verdict**: LGTM",
            ],
            # diff after impl, diff after review1, diff after address, diff after review2, final
            diffs=["diff1", "diff2", "diff3", "diff3"],
        )
        result = implement_and_review(task)

        assert result.converged is True
        assert len(result.review_log) == 2
        assert result.review_log[0]["approved"] is False
        assert result.review_log[1]["approved"] is True
        assert "addressing_feedback" in events

    def test_max_iterations_exhausted(self) -> None:
        task, events = _make_task(
            implement_responses=["attempt1", "attempt2"],
            review_responses=[
                "**Verdict**: CONCERNS\n\nStill wrong.",
                "**Verdict**: CONCERNS\n\nStill wrong.",
            ],
            diffs=["diff", "diff", "diff", "diff"],
            max_iterations=2,
        )
        result = implement_and_review(task)

        assert result.converged is False
        assert result.has_changes is True
        assert len(result.review_log) == 2

    def test_context_prepended_to_prompts(self) -> None:
        task, events = _make_task(
            implement_responses=["done"],
            review_responses=["**Verdict**: LGTM"],
            diffs=["diff", "diff"],
            context="This is a Python project.",
        )
        implement_and_review(task)

        assert isinstance(task.implement_agent, StubAgent)
        assert "Project context:" in task.implement_agent.prompts[0]
        assert "This is a Python project." in task.implement_agent.prompts[0]

        assert isinstance(task.review_agent, StubAgent)
        assert "Project context:" in task.review_agent.prompts[0]
