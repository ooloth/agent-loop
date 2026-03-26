import re
import time
from dataclasses import dataclass
from typing import TypedDict

from agent_loop.domain.protocols import AgentBackend, VCSBackend
from agent_loop.io.logging import log_detail, log_step


class ReviewEntry(TypedDict):
    iteration: int
    approved: bool
    feedback: str


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


@dataclass(frozen=True)
class ImplementAndReviewResult:
    review_log: list[ReviewEntry]
    converged: bool
    has_changes: bool


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
    """Run the implement→review→address loop for an arbitrary task."""
    # Initial implementation
    fix_prompt = task.fix_prompt_template.format(title=task.title, body=task.body)
    if task.context:
        fix_prompt = f"Project context:\n{task.context}\n\n{fix_prompt}"

    log_step("🤖 Implementing fix...")
    task.implement_agent.run(fix_prompt)
    task.vcs.stage_all()

    # Review loop
    iteration = 0
    review_log: list[ReviewEntry] = []
    converged = False

    while iteration < task.max_iterations:
        iteration += 1

        diff = task.vcs.diff_staged()
        if not diff:
            log_step("⚠️  No changes were made", last=True)
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
            log_step(
                f"🔎 Review {iteration}/{task.max_iterations} — ✅ Approved ({review_elapsed}s)"
            )
            converged = True
            break

        is_last_iteration = iteration >= task.max_iterations
        log_step(
            f"🔎 Review {iteration}/{task.max_iterations} — 🔄 Changes requested ({review_elapsed}s)",
            last=is_last_iteration,
        )
        log_detail(summarize_feedback(feedback), last_step=is_last_iteration)

        if is_last_iteration:
            break

        # Address feedback
        fix_feedback_prompt = (
            f"Your previous fix received this review feedback:\n\n{feedback}\n\n"
            f"Original issue:\nTitle: {task.title}\nDescription:\n{task.body}\n\n"
            f"Please address the concerns. Prefer the simplest solution — if a problem\n"
            f"can be eliminated rather than handled, do that instead."
        )
        log_step("🤖 Addressing feedback...")
        task.implement_agent.run(fix_feedback_prompt)
        task.vcs.stage_all()

    has_changes = bool(task.vcs.diff_staged())
    return ImplementAndReviewResult(
        review_log=review_log,
        converged=converged,
        has_changes=has_changes,
    )
