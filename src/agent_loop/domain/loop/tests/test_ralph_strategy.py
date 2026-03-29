"""Tests for RalphStrategy via loop_until_done."""

from collections.abc import Iterator

from agent_loop.domain.loop.engine import (
    EngineEvent,
    StepCompleted,
    StepStarted,
    loop_until_done,
)
from agent_loop.domain.loop.strategies import RalphStrategy
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
    """VCSBackend stub that tracks staged diffs and commits."""

    def __init__(self, diffs: list[str]) -> None:
        self._diffs: Iterator[str] = iter(diffs)
        self.commits: list[str] = []

    def stage_all(self) -> None:
        pass

    def diff_staged(self) -> str:
        return next(self._diffs)

    def commit(self, message: str) -> None:
        self.commits.append(message)

    def checkout(self, branch: str) -> None:
        pass

    def pull(self, branch: str) -> None:
        pass

    def checkout_new_branch(self, branch: str) -> None:
        pass

    def push(self, branch: str) -> None:
        pass

    def delete_branch(self, branch: str) -> None:
        pass


TEMPLATE = "Goal:\n{goal}"


class TestRalphStrategy:
    def test_converges_on_done_signal(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["step 1 done", "all done\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        vcs = StubVCS(["diff1", "diff2"])
        work = WorkSpec(title="test", body="add type hints")
        events: list[EngineEvent] = []

        result = loop_until_done(work, strategy, vcs, 5, "", events.append)

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
        vcs = StubVCS(["diff", "diff", "diff"])
        work = WorkSpec(title="test", body="big task")
        events: list[EngineEvent] = []

        result = loop_until_done(work, strategy, vcs, 3, "", events.append)

        assert result.converged is False
        assert result.iterations == 3
        assert result.has_changes is True

    def test_no_changes_iteration_skips_commit(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["looked around, nothing to do", "made a fix\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        # First iteration: no diff. Second: has diff.
        vcs = StubVCS(["", "diff2"])
        work = WorkSpec(title="test", body="check things")
        events: list[EngineEvent] = []

        result = loop_until_done(work, strategy, vcs, 5, "", events.append)

        assert result.converged is True
        assert result.iterations == 2
        assert vcs.commits == ["ralph: step 2"]  # only second iteration committed

    def test_context_prepended_to_prompt(self) -> None:
        agent = StubAgent(["done\n##DONE##"])
        strategy = RalphStrategy(agent=agent, prompt_template=TEMPLATE)
        vcs = StubVCS(["diff"])
        work = WorkSpec(title="test", body="the goal")

        loop_until_done(work, strategy, vcs, 5, "Python project", lambda _: None)

        assert "Project context:" in agent.prompts[0]
        assert "Python project" in agent.prompts[0]

    def test_progress_events_fired(self) -> None:
        strategy = RalphStrategy(
            agent=StubAgent(["working...", "done\n##DONE##"]),
            prompt_template=TEMPLATE,
        )
        vcs = StubVCS(["diff", "diff"])
        work = WorkSpec(title="test", body="goal")
        events: list[EngineEvent] = []

        loop_until_done(work, strategy, vcs, 5, "", events.append)

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
        vcs = StubVCS(["diff"])
        work = WorkSpec(title="test", body="add tests to foo.py")

        loop_until_done(work, strategy, vcs, 5, "", lambda _: None)

        assert "Do this: add tests to foo.py" in agent.prompts[0]

    def test_scratchpad_passed_to_next_iteration(self) -> None:
        agent = StubAgent(
            [
                "step 1\n\n```scratchpad\n## Status\nDid the first part.\n```",
                "step 2\n##DONE##\n\n```scratchpad\n## Status\nAll done.\n```",
            ]
        )
        strategy = RalphStrategy(agent=agent, prompt_template=TEMPLATE)
        vcs = StubVCS(["diff", "diff"])
        work = WorkSpec(title="test", body="the goal")

        loop_until_done(work, strategy, vcs, 5, "", lambda _: None)

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
        vcs = StubVCS(["diff", "diff"])
        work = WorkSpec(title="test", body="the goal")

        result = loop_until_done(work, strategy, vcs, 5, "", lambda _: None)

        # Should still converge — missing scratchpad doesn't break anything
        assert result.converged is True
        # Second prompt should NOT have scratchpad context (first response had none)
        assert "previous iteration" not in agent.prompts[1]
