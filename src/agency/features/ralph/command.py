"""Ralph command — iterative fresh-eyes refinement toward a goal.

Accepts work from --prompt, --file, or --plan (mutually exclusive). The --plan
flag is functionally identical to --file — the distinction is semantic (plans
are structured artifacts from a planning session; files are freeform).

Uses RalphStrategy, which commits per iteration for crash safety. The pipeline
handles branch lifecycle and PR creation. See RalphStrategy for the iteration
and scratchpad mechanics.
"""

import re
import time
from pathlib import Path

from agency.domain.context import AppContext
from agency.domain.errors import AgentLoopError
from agency.domain.loop.engine import (
    EngineEvent,
    LoopOptions,
    StepCompleted,
    StepStarted,
    loop_until_done,
)
from agency.domain.loop.strategies import RalphStrategy
from agency.domain.loop.work import WorkSpec, from_file, from_prompt
from agency.domain.ports.agent_backend import AgentBackend
from agency.features.ralph.prompts import RALPH_PROMPT_TEMPLATE
from agency.io.observability.logging import log, log_detail, log_step


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a branch-name-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _log_ralph_progress(event: EngineEvent) -> None:
    match event:
        case StepStarted(iteration=i, max_iterations=m):
            log_step(f"🔄 Step {i}/{m}...")
        case StepCompleted(
            iteration=i, max_iterations=m, elapsed_seconds=s, done=done, scratchpad=sp
        ):
            is_last = done or i >= m
            status = "✅ Done" if done else "→ continuing"
            log_step(f"🔄 Step {i}/{m} — {status} ({s}s)", last=is_last and not sp)
            if sp:
                for line in sp.splitlines():
                    log_detail(line, last_step=is_last)
                if not is_last:
                    log_detail("", last_step=False)


def cmd_ralph(
    ctx: AppContext,
    agent: AgentBackend,
    max_iterations: int,
    *,
    prompt: str | None = None,
    file: Path | None = None,
) -> None:
    """Run the Ralph loop: iterative fresh-eyes refinement toward a goal.

    Branch lifecycle:
    - Rejects uncommitted changes upfront (raises AgentLoopError).
    - Creates ralph/<slugified-title> branch from the default branch.
    - Opens a draft PR on success. If the agent did not signal completion
      (##DONE##), posts a warning comment on the PR.
    - Always returns to the default branch on exit.
    - Deletes the ralph branch if nothing was pushed (early return or exception).
    """
    if ctx.vcs.has_uncommitted_changes():
        msg = "Working tree has uncommitted changes. Commit or stash them before running ralph."
        raise AgentLoopError(msg)

    work: WorkSpec
    if file is not None:
        work = from_file(file)
    elif prompt is not None:
        work = from_prompt(prompt)
    else:
        msg = "Either --prompt or --file is required"
        raise ValueError(msg)

    branch = f"ralph/{_slugify(work.title)}"

    log.info("🔁 Ralph: %s", work.title)

    default_branch = ctx.tracker.get_default_branch()
    ctx.vcs.checkout(default_branch)
    ctx.vcs.pull(default_branch)
    ctx.vcs.checkout_new_branch(branch)

    pushed = False
    try:
        strategy = RalphStrategy(
            agent=agent,
            prompt_template=RALPH_PROMPT_TEMPLATE,
        )
        t0 = time.monotonic()
        result = loop_until_done(
            work=work,
            strategy=strategy,
            vcs=ctx.vcs,
            options=LoopOptions(
                max_iterations=max_iterations,
                context=ctx.config.context,
                on_progress=_log_ralph_progress,
            ),
        )
        elapsed = int(time.monotonic() - t0)

        if not result.has_changes:
            log.warning("└── ⚠️  No changes were made")
            return

        ctx.vcs.push(branch)
        pushed = True

        status = "completed" if result.converged else f"stopped after {result.iterations} steps"
        pr_body = (
            f"**Goal:** {work.body}\n\n"
            f"**Status:** {status} ({elapsed}s total)\n\n"
            f"---\n\n"
            f"_Opened by `agency ralph` — review before merging._"
        )
        pr_ref = ctx.tracker.open_pr(
            title=f"Ralph: {work.title}",
            body=pr_body,
            head=branch,
            draft=True,
        )

        if result.converged:
            log_step(f"🎉 Done — draft PR opened ({elapsed}s total)", last=True)
        else:
            log_step(
                f"⚠️  Hit iteration cap ({result.iterations}/{max_iterations})"
                f" — draft PR opened ({elapsed}s total)",
                last=True,
            )
            ctx.tracker.comment_on_pr(
                pr_ref,
                f"⚠️ Ralph did not signal completion after {result.iterations} iterations.\n\n"
                f"The work may be incomplete — review carefully before merging.",
            )
    finally:
        ctx.vcs.checkout(default_branch)
        if not pushed:
            log.warning("Cleaning up branch %s (no changes pushed)", branch)
            ctx.vcs.delete_branch(branch)
