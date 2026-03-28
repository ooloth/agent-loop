from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TypedDict

from agent_loop.domain.ports.agent_backend import AgentBackend
from agent_loop.domain.ports.vcs_backend import VCSBackend


class ReviewEntry(TypedDict):
    iteration: int
    approved: bool
    feedback: str


# ---------------------------------------------------------------------------
# Typed progress events
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Implementing:
    """The implement agent is working on the initial fix."""


@dataclass(frozen=True)
class NoChanges:
    """The implement agent produced no staged diff."""


@dataclass(frozen=True)
class ReviewApproved:
    """The review agent approved the diff."""

    iteration: int
    max_iterations: int
    elapsed_seconds: int


@dataclass(frozen=True)
class ReviewRejected:
    """The review agent requested changes."""

    iteration: int
    max_iterations: int
    elapsed_seconds: int
    summary: str


@dataclass(frozen=True)
class AddressingFeedback:
    """The implement agent is addressing review feedback."""


EngineEvent = Implementing | NoChanges | ReviewApproved | ReviewRejected | AddressingFeedback
ProgressCallback = Callable[[EngineEvent], None]


def _noop(_event: EngineEvent) -> None:
    pass


@dataclass(frozen=True)
class ImplementAndReviewInput:
    title: str
    body: str
    implement_agent: AgentBackend
    review_agent: AgentBackend
    vcs: VCSBackend
    max_iterations: int
    context: str
    fix_prompt_template: str
    review_prompt: str
    on_progress: ProgressCallback = field(default=_noop)


@dataclass(frozen=True)
class ImplementAndReviewResult:
    review_log: list[ReviewEntry]
    converged: bool
    has_changes: bool
    # The implement agent's response to the initial fix prompt — useful when no
    # changes were made, since the review_log will be empty in that case.
    implement_response: str


def parse_review_verdict(feedback: str) -> bool:
    """Return True if the review feedback contains an LGTM verdict."""
    return bool(re.search(r"\bLGTM\b", feedback, re.IGNORECASE))


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


def implement_and_review(task: ImplementAndReviewInput) -> ImplementAndReviewResult:
    """Run the implement→review→address loop for an arbitrary task.

    Progress is reported via task.on_progress (a callback). The engine itself
    does no I/O beyond the injected AgentBackend and VCSBackend calls.
    """
    notify = task.on_progress

    # Initial implementation
    fix_prompt = task.fix_prompt_template.format(title=task.title, body=task.body)
    if task.context:
        fix_prompt = f"Project context:\n{task.context}\n\n{fix_prompt}"

    notify(Implementing())
    implement_response = task.implement_agent.run(fix_prompt)
    task.vcs.stage_all()

    # Review loop
    iteration = 0
    review_log: list[ReviewEntry] = []
    converged = False

    while iteration < task.max_iterations:
        iteration += 1

        diff = task.vcs.diff_staged()
        if not diff:
            notify(NoChanges())
            break

        review_prompt = (
            task.review_prompt
            + f"\n\n## Issue being fixed\n\nTitle: {task.title}\nDescription:\n{task.body}"
            + f"\n\n## Diff to review\n\n{diff}"
        )
        if task.context:
            review_prompt = f"Project context:\n{task.context}\n\n{review_prompt}"

        t0 = time.monotonic()
        feedback = task.review_agent.run(review_prompt)
        review_elapsed = int(time.monotonic() - t0)
        approved = parse_review_verdict(feedback)

        review_log.append(
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
                    max_iterations=task.max_iterations,
                    elapsed_seconds=review_elapsed,
                )
            )
            converged = True
            break

        summary = summarize_feedback(feedback)
        is_last_iteration = iteration >= task.max_iterations
        notify(
            ReviewRejected(
                iteration=iteration,
                max_iterations=task.max_iterations,
                elapsed_seconds=review_elapsed,
                summary=summary,
            )
        )

        if is_last_iteration:
            break

        # Address feedback
        fix_feedback_prompt = (
            f"Your previous fix received this review feedback:\n\n{feedback}\n\n"
            f"Original issue:\nTitle: {task.title}\nDescription:\n{task.body}\n\n"
            f"Please address the concerns. Prefer the simplest solution — if a problem\n"
            f"can be eliminated rather than handled, do that instead."
        )
        notify(AddressingFeedback())
        task.implement_agent.run(fix_feedback_prompt)
        task.vcs.stage_all()

    has_changes = bool(task.vcs.diff_staged())
    return ImplementAndReviewResult(
        review_log=review_log,
        converged=converged,
        has_changes=has_changes,
        implement_response=implement_response,
    )
