"""Tests for the antagonistic loop strategy via loop_until_done."""

from agency.domain.loop.engine import (
    AddressedFeedback,
    EngineEvent,
    Implemented,
    LoopOptions,
    NoChanges,
    ReviewApproved,
    loop_until_done,
)
from agency.domain.loop.strategies import AntagonisticStrategy
from agency.domain.loop.work import WorkSpec
from agency.domain.ports.tests.stubs import StubAgent, StubVCS


def _make_task(
    implement_responses: list[str],
    review_responses: list[str],
    diffs: list[str],
    max_iterations: int = 5,
    context: str = "",
) -> tuple[AntagonisticStrategy, WorkSpec, StubVCS, LoopOptions, list[EngineEvent]]:
    events: list[EngineEvent] = []
    strategy = AntagonisticStrategy(
        implement_agent=StubAgent(implement_responses),
        review_agent=StubAgent(review_responses),
        fix_prompt_template="Fix: {title}\n{body}",
        review_prompt="Review this diff.",
    )
    work = WorkSpec(title="Test issue", body="Fix the thing.")
    vcs = StubVCS(diffs=diffs)
    options = LoopOptions(max_iterations=max_iterations, context=context, on_progress=events.append)
    return strategy, work, vcs, options, events


class TestImplementAndReview:
    def test_approved_first_try(self) -> None:
        strategy, work, vcs, options, events = _make_task(
            implement_responses=["fixed it"],
            review_responses=["**Verdict**: LGTM"],
            # diff_staged called twice: once in the review loop, once for has_changes
            diffs=["diff content", "diff content"],
        )
        result = loop_until_done(work, strategy, vcs, options)

        assert result.converged is True
        assert result.has_changes is True
        assert strategy.initial_response == "fixed it"
        assert len(strategy.review_log) == 1
        assert strategy.review_log[0]["approved"] is True
        assert any(isinstance(e, Implemented) for e in events)
        assert any(isinstance(e, ReviewApproved) for e in events)

    def test_no_changes_after_implementation(self) -> None:
        strategy, work, vcs, options, events = _make_task(
            implement_responses=["nothing to do"],
            review_responses=[],
            # Empty diff after staging → no changes
            diffs=["", ""],
        )
        result = loop_until_done(work, strategy, vcs, options)

        assert result.converged is False
        assert result.has_changes is False
        assert strategy.review_log == []
        assert NoChanges() in events

    def test_feedback_addressed_then_approved(self) -> None:
        strategy, work, vcs, options, events = _make_task(
            implement_responses=["first attempt", "addressed feedback"],
            review_responses=[
                "**Verdict**: CONCERNS\n\n#### 🔧 Required Changes\n- Fix the edge case",
                "**Verdict**: LGTM",
            ],
            # diff after impl, diff after review1, diff after address, diff after review2, final
            diffs=["diff1", "diff2", "diff3", "diff3"],
        )
        result = loop_until_done(work, strategy, vcs, options)

        assert result.converged is True
        assert len(strategy.review_log) == 2
        assert strategy.review_log[0]["approved"] is False
        assert strategy.review_log[1]["approved"] is True
        assert any(isinstance(e, AddressedFeedback) for e in events)

    def test_max_iterations_exhausted(self) -> None:
        strategy, work, vcs, options, _events = _make_task(
            implement_responses=["attempt1", "attempt2"],
            review_responses=[
                "**Verdict**: CONCERNS\n\nStill wrong.",
                "**Verdict**: CONCERNS\n\nStill wrong.",
            ],
            diffs=["diff", "diff", "diff", "diff"],
            max_iterations=2,
        )
        result = loop_until_done(work, strategy, vcs, options)

        assert result.converged is False
        assert result.has_changes is True
        assert len(strategy.review_log) == 2

    def test_context_prepended_to_prompts(self) -> None:
        strategy, work, vcs, options, _events = _make_task(
            implement_responses=["done"],
            review_responses=["**Verdict**: LGTM"],
            diffs=["diff", "diff"],
            context="This is a Python project.",
        )
        loop_until_done(work, strategy, vcs, options)

        impl_agent = strategy._implement_agent
        assert isinstance(impl_agent, StubAgent)
        assert "Project context:" in impl_agent.prompts[0]
        assert "This is a Python project." in impl_agent.prompts[0]

        review_agent = strategy._review_agent
        assert isinstance(review_agent, StubAgent)
        assert "Project context:" in review_agent.prompts[0]
