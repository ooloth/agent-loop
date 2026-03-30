"""Tests for RalphStrategy via loop_until_done."""

from agency.domain.loop.engine import (
    EngineEvent,
    LoopOptions,
    StepCompleted,
    StepStarted,
    loop_until_done,
)
from agency.domain.loop.strategies import RalphStrategy
from agency.domain.loop.work import WorkSpec
from agency.domain.ports.tests.stubs import StubAgent, StubVCS

TEMPLATE = "Goal:\n{goal}"


class TestRalphStrategy:
    def test_converges_on_done_signal(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["step 1 done", "all done\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        vcs = StubVCS(diffs=["diff1", "diff2"])
        work = WorkSpec(title="test", body="add type hints")
        events: list[EngineEvent] = []

        result = loop_until_done(
            work, strategy, vcs, LoopOptions(max_iterations=5, on_progress=events.append)
        )

        assert result.converged is True
        assert result.iterations == 2
        assert result.has_changes is True
        assert len(strategy.responses) == 2
        assert vcs.commits == ["ralph: step 1", "ralph: step 2"]

    def test_hits_max_iterations(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["progress 1", "progress 2", "progress 3"]),
            prompt_template=TEMPLATE,
        )
        vcs = StubVCS(diffs=["diff", "diff", "diff"])
        work = WorkSpec(title="test", body="big task")
        events: list[EngineEvent] = []

        result = loop_until_done(
            work, strategy, vcs, LoopOptions(max_iterations=3, on_progress=events.append)
        )

        assert result.converged is False
        assert result.iterations == 3
        assert result.has_changes is True

    def test_no_changes_iteration_skips_commit(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["looked around, nothing to do", "made a fix\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        # First iteration: no diff. Second: has diff.
        vcs = StubVCS(diffs=["", "diff2"])
        work = WorkSpec(title="test", body="check things")
        events: list[EngineEvent] = []

        result = loop_until_done(
            work, strategy, vcs, LoopOptions(max_iterations=5, on_progress=events.append)
        )

        assert result.converged is True
        assert result.iterations == 2
        assert vcs.commits == ["ralph: step 2"]  # only second iteration committed

    def test_context_prepended_to_prompt(self) -> None:
        agent = StubAgent(["done\n##DONE##"])
        strategy = RalphStrategy(agent=agent, prompt_template=TEMPLATE)
        vcs = StubVCS(diffs=["diff"])
        work = WorkSpec(title="test", body="the goal")

        loop_until_done(
            work, strategy, vcs, LoopOptions(max_iterations=5, context="Python project")
        )

        assert "Project context:" in agent.prompts[0]
        assert "Python project" in agent.prompts[0]

    def test_progress_events_fired(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["working...", "done\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        vcs = StubVCS(diffs=["diff", "diff"])
        work = WorkSpec(title="test", body="goal")
        events: list[EngineEvent] = []

        loop_until_done(
            work, strategy, vcs, LoopOptions(max_iterations=5, on_progress=events.append)
        )

        assert events[0] == StepStarted(iteration=1, max_iterations=5)
        assert isinstance(events[1], StepCompleted)
        assert events[1].iteration == 1
        assert events[1].done is False
        assert events[2] == StepStarted(iteration=2, max_iterations=5)
        assert isinstance(events[3], StepCompleted)
        assert events[3].iteration == 2
        assert events[3].done is True

    def test_prompt_template_receives_goal(self) -> None:
        agent = StubAgent(["##DONE##"])
        strategy = RalphStrategy(agent=agent, prompt_template="Do this: {goal}")
        vcs = StubVCS(diffs=["diff"])
        work = WorkSpec(title="test", body="add tests to foo.py")

        loop_until_done(work, strategy, vcs, LoopOptions(max_iterations=5))

        assert "Do this: add tests to foo.py" in agent.prompts[0]

    def test_scratchpad_passed_to_next_iteration(self) -> None:
        agent = StubAgent(
            [
                "step 1\n\n```scratchpad\n## Status\nDid the first part.\n```",
                "step 2\n##DONE##\n\n```scratchpad\n## Status\nAll done.\n```",
            ]
        )
        strategy = RalphStrategy(agent=agent, prompt_template=TEMPLATE)
        vcs = StubVCS(diffs=["diff", "diff"])
        work = WorkSpec(title="test", body="the goal")

        loop_until_done(work, strategy, vcs, LoopOptions(max_iterations=5))

        # First prompt should NOT have scratchpad context
        assert "previous iteration" not in agent.prompts[0]
        # Second prompt SHOULD have scratchpad from first iteration
        assert "previous iteration" in agent.prompts[1]
        assert "Did the first part." in agent.prompts[1]
        # Final scratchpad is stored on the strategy
        assert strategy.scratchpad == "## Status\nAll done."

    def test_scratchpad_graceful_degradation(self) -> None:
        agent = StubAgent(
            [
                "step 1 — no scratchpad in this response",
                "step 2\n##DONE##",
            ]
        )
        strategy = RalphStrategy(agent=agent, prompt_template=TEMPLATE)
        vcs = StubVCS(diffs=["diff", "diff"])
        work = WorkSpec(title="test", body="the goal")

        result = loop_until_done(work, strategy, vcs, LoopOptions(max_iterations=5))

        # Should still converge — missing scratchpad doesn't break anything
        assert result.converged is True
        # Second prompt should NOT have scratchpad context (first response had none)
        assert "previous iteration" not in agent.prompts[1]
