"""Concrete loop strategies."""

from __future__ import annotations

import re
import textwrap
import time
from typing import TypedDict

from agent_loop.domain.loop.engine import (
    AddressingFeedback,
    Implementing,
    LoopResult,
    NoChanges,
    ProgressCallback,
    ReviewApproved,
    ReviewRejected,
    StepCompleted,
    StepStarted,
)
from agent_loop.domain.loop.termination import OutputSignal, ReviewApproval
from agent_loop.domain.loop.work import WorkSpec
from agent_loop.domain.ports.agent_backend import AgentBackend
from agent_loop.domain.ports.vcs_backend import VCSBackend


class ReviewEntry(TypedDict):
    iteration: int
    approved: bool
    feedback: str


def summarize_feedback(feedback: str, max_len: int = 80) -> str:
    """Extract a one-line summary from reviewer feedback."""
    # Look for the Required Changes section first
    match = re.search(r"#{1,4}\s*🔧\s*Required Changes\s*\n(.+)", feedback)
    if match:
        summary = match.group(1).strip()
    else:
        # Look for the CONCERNS verdict and take the line after it
        match = re.search(r"\*\*Verdict\*\*:\s*CONCERNS\s*\n+(.+)", feedback)
        if match:
            summary = match.group(1).strip()
        else:
            # Fall back to first substantive line
            for line in feedback.split("\n"):
                stripped = line.strip()
                if (
                    stripped
                    and not stripped.startswith("#")
                    and not stripped.startswith("**")
                    and not stripped.startswith("---")
                    and not stripped.startswith(">")
                ):
                    summary = stripped
                    break
            else:
                summary = "(no details)"
    # Clean up markdown artifacts
    summary = re.sub(r"\*\*(.+?)\*\*", r"\1", summary)  # remove bold
    summary = re.sub(r"`(.+?)`", r"\1", summary)  # remove inline code
    summary = summary.lstrip("- ").lstrip("* ")  # remove list markers
    if len(summary) > max_len:
        summary = summary[: max_len - 1] + "…"
    return summary


class AntagonisticStrategy:
    """Implement → review → address-feedback loop with two opposing agents.

    After execution, strategy-specific state is available via attributes:
    - review_log: list[ReviewEntry] — full review trail
    - initial_response: str — the implement agent's first response
    """

    def __init__(
        self,
        implement_agent: AgentBackend,
        review_agent: AgentBackend,
        fix_prompt_template: str,
        review_prompt: str,
    ) -> None:
        self._implement_agent = implement_agent
        self._review_agent = review_agent
        self._fix_prompt_template = fix_prompt_template
        self._review_prompt = review_prompt
        self._review_approval = ReviewApproval()
        self.review_log: list[ReviewEntry] = []
        self.initial_response: str = ""

    def execute(
        self,
        work: WorkSpec,
        vcs: VCSBackend,
        max_iterations: int,
        context: str,
        on_progress: ProgressCallback,
    ) -> LoopResult:
        notify = on_progress

        # Initial implementation
        fix_prompt = self._fix_prompt_template.format(title=work.title, body=work.body)
        if context:
            fix_prompt = f"Project context:\n{context}\n\n{fix_prompt}"

        notify(Implementing())
        self.initial_response = self._implement_agent.run(fix_prompt)
        vcs.stage_all()

        # Review loop
        iteration = 0
        converged = False

        while iteration < max_iterations:
            iteration += 1

            diff = vcs.diff_staged()
            if not diff:
                notify(NoChanges())
                break

            review_prompt = (
                self._review_prompt
                + f"\n\n## Issue being fixed\n\nTitle: {work.title}\nDescription:\n{work.body}"
                + f"\n\n## Diff to review\n\n{diff}"
            )
            if context:
                review_prompt = f"Project context:\n{context}\n\n{review_prompt}"

            t0 = time.monotonic()
            feedback = self._review_agent.run(review_prompt)
            review_elapsed = int(time.monotonic() - t0)
            approved = self._review_approval.is_met(feedback)

            self.review_log.append(
                {
                    "iteration": iteration,
                    "approved": approved,
                    "feedback": feedback,
                }
            )

            if approved:
                notify(
                    ReviewApproved(
                        iteration=iteration,
                        max_iterations=max_iterations,
                        elapsed_seconds=review_elapsed,
                    )
                )
                converged = True
                break

            summary = summarize_feedback(feedback)
            is_last_iteration = iteration >= max_iterations
            notify(
                ReviewRejected(
                    iteration=iteration,
                    max_iterations=max_iterations,
                    elapsed_seconds=review_elapsed,
                    summary=summary,
                )
            )

            if is_last_iteration:
                break

            # Address feedback
            fix_feedback_prompt = (
                f"Your previous fix received this review feedback:\n\n{feedback}\n\n"
                f"Original issue:\nTitle: {work.title}\nDescription:\n{work.body}\n\n"
                f"Please address the concerns. Prefer the simplest solution — if a problem\n"
                f"can be eliminated rather than handled, do that instead."
            )
            notify(AddressingFeedback())
            self._implement_agent.run(fix_feedback_prompt)
            vcs.stage_all()

        has_changes = bool(vcs.diff_staged())
        return LoopResult(
            converged=converged,
            has_changes=has_changes,
            iterations=iteration,
        )


_SCRATCHPAD_INSTRUCTIONS = textwrap.dedent("""\

    After making your change, end your response with a scratchpad for the
    next iteration using this exact format:

    ```scratchpad
    ## Status
    <what's done and what's in progress>

    ## Key decisions
    <choices made and why — help the next iteration understand your reasoning>

    ## Remaining work
    <what still needs to be done, if anything>
    ```""")


def extract_scratchpad(response: str) -> str:
    """Extract the scratchpad block from an agent response.

    Returns the content between ```scratchpad and ```, or empty string
    if no scratchpad block is found (graceful degradation).
    """
    match = re.search(r"```scratchpad\n(.*?)```", response, re.DOTALL)
    return match.group(1).strip() if match else ""


class RalphStrategy:
    """Fresh-eyes iterative refinement with a single agent.

    Each iteration the agent sees the current codebase with no memory of
    prior iterations, compares it against the goal, and makes one
    improvement — either new progress or correcting a prior step. Commits
    after each iteration for crash safety and audit trail.

    A scratchpad is passed between iterations: the agent outputs a
    ```scratchpad block in its response, which the strategy extracts and
    injects into the next iteration's prompt. This gives fresh eyes the
    context they need (why decisions were made, what's left) without the
    conformity pressure of a growing log — each agent writes its own
    assessment.

    After execution, strategy-specific state is available via attributes:
    - responses: list[str] — each iteration's agent response
    - scratchpad: str — the final scratchpad content
    """

    def __init__(
        self,
        agent: AgentBackend,
        prompt_template: str,
    ) -> None:
        self._agent = agent
        self._prompt_template = prompt_template
        self._output_signal = OutputSignal()
        self.responses: list[str] = []
        self.scratchpad: str = ""

    def execute(
        self,
        work: WorkSpec,
        vcs: VCSBackend,
        max_iterations: int,
        context: str,
        on_progress: ProgressCallback,
    ) -> LoopResult:
        notify = on_progress
        converged = False
        iteration = 0
        has_changes = False

        for iteration in range(1, max_iterations + 1):
            prompt = self._prompt_template.format(goal=work.body)
            if context:
                prompt = f"Project context:\n{context}\n\n{prompt}"
            if self.scratchpad:
                prompt += (
                    "\n\nScratchpad from the previous iteration"
                    " (use for context, but form your own assessment):\n\n"
                    f"{self.scratchpad}"
                )
            prompt += _SCRATCHPAD_INSTRUCTIONS

            notify(StepStarted(iteration=iteration, max_iterations=max_iterations))
            t0 = time.monotonic()
            response = self._agent.run(prompt)
            elapsed = int(time.monotonic() - t0)
            self.responses.append(response)
            self.scratchpad = extract_scratchpad(response)

            # Commit any changes this iteration produced
            vcs.stage_all()
            if vcs.diff_staged():
                vcs.commit(f"ralph: step {iteration}")
                has_changes = True

            done = self._output_signal.is_met(response)
            notify(
                StepCompleted(
                    iteration=iteration,
                    max_iterations=max_iterations,
                    elapsed_seconds=elapsed,
                    done=done,
                )
            )

            if done:
                converged = True
                break

        return LoopResult(
            converged=converged,
            has_changes=has_changes,
            iterations=iteration,
        )
