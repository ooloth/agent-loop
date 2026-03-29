"""Tests for the antagonistic loop strategy via loop_until_done."""

from collections.abc import Iterator

from agent_loop.domain.loop.engine import (
    AddressingFeedback,
    EngineEvent,
    Implementing,
    NoChanges,
    ReviewApproved,
    loop_until_done,
)
from agent_loop.domain.loop.strategies import AntagonisticStrategy
from agent_loop.domain.loop.work import WorkSpec


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

    def has_uncommitted_changes(self) -> bool:
        return False

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
) -> tuple[AntagonisticStrategy, WorkSpec, StubVCS, int, str, list[EngineEvent]]:
    events: list[EngineEvent] = []
    strategy = AntagonisticStrategy(
        implement_agent=StubAgent(implement_responses),
        review_agent=StubAgent(review_responses),
        fix_prompt_template="Fix: {title}\n{body}",
        review_prompt="Review this diff.",
    )
    work = WorkSpec(title="Test issue", body="Fix the thing.")
    vcs = StubVCS(diffs)
    return strategy, work, vcs, max_iterations, context, events


class TestImplementAndReview:
    def test_approved_first_try(self) -> None:
        strategy, work, vcs, max_iter, context, events = _make_task(
            implement_responses=["fixed it"],
            review_responses=["**Verdict**: LGTM"],
            # diff_staged called twice: once in the review loop, once for has_changes
            diffs=["diff content", "diff content"],
        )
        result = loop_until_done(work, strategy, vcs, max_iter, context, events.append)

        assert result.converged is True
        assert result.has_changes is True
        assert strategy.initial_response == "fixed it"
        assert len(strategy.review_log) == 1
        assert strategy.review_log[0]["approved"] is True
        assert Implementing() in events
        assert any(isinstance(e, ReviewApproved) for e in events)

    def test_no_changes_after_implementation(self) -> None:
        strategy, work, vcs, max_iter, context, events = _make_task(
            implement_responses=["nothing to do"],
            review_responses=[],
            # Empty diff after staging → no changes
            diffs=["", ""],
        )
        result = loop_until_done(work, strategy, vcs, max_iter, context, events.append)

        assert result.converged is False
        assert result.has_changes is False
        assert strategy.review_log == []
        assert NoChanges() in events

    def test_feedback_addressed_then_approved(self) -> None:
        strategy, work, vcs, max_iter, context, events = _make_task(
            implement_responses=["first attempt", "addressed feedback"],
            review_responses=[
                "**Verdict**: CONCERNS\n\n#### 🔧 Required Changes\n- Fix the edge case",
                "**Verdict**: LGTM",
            ],
            # diff after impl, diff after review1, diff after address, diff after review2, final
            diffs=["diff1", "diff2", "diff3", "diff3"],
        )
        result = loop_until_done(work, strategy, vcs, max_iter, context, events.append)

        assert result.converged is True
        assert len(strategy.review_log) == 2
        assert strategy.review_log[0]["approved"] is False
        assert strategy.review_log[1]["approved"] is True
        assert AddressingFeedback() in events

    def test_max_iterations_exhausted(self) -> None:
        strategy, work, vcs, max_iter, context, events = _make_task(
            implement_responses=["attempt1", "attempt2"],
            review_responses=[
                "**Verdict**: CONCERNS\n\nStill wrong.",
                "**Verdict**: CONCERNS\n\nStill wrong.",
            ],
            diffs=["diff", "diff", "diff", "diff"],
            max_iterations=2,
        )
        result = loop_until_done(work, strategy, vcs, max_iter, context, events.append)

        assert result.converged is False
        assert result.has_changes is True
        assert len(strategy.review_log) == 2

    def test_context_prepended_to_prompts(self) -> None:
        strategy, work, vcs, max_iter, context, events = _make_task(
            implement_responses=["done"],
            review_responses=["**Verdict**: LGTM"],
            diffs=["diff", "diff"],
            context="This is a Python project.",
        )
        loop_until_done(work, strategy, vcs, max_iter, context, events.append)

        impl_agent = strategy._implement_agent
        assert isinstance(impl_agent, StubAgent)
        assert "Project context:" in impl_agent.prompts[0]
        assert "This is a Python project." in impl_agent.prompts[0]

        review_agent = strategy._review_agent
        assert isinstance(review_agent, StubAgent)
        assert "Project context:" in review_agent.prompts[0]
