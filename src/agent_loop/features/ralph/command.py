import re
import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.errors import AgentLoopError
from agent_loop.domain.loop.engine import (
    EngineEvent,
    StepCompleted,
    StepStarted,
    loop_until_done,
)
from agent_loop.domain.loop.strategies import RalphStrategy
from agent_loop.domain.loop.work import from_prompt
from agent_loop.features.ralph.prompts import RALPH_PROMPT_TEMPLATE
from agent_loop.io.observability.logging import log, log_detail, log_step


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


def cmd_ralph(ctx: AppContext, prompt: str, max_iterations: int) -> None:
    """Run the Ralph loop: iterative fresh-eyes refinement toward a goal."""
    if ctx.vcs.has_uncommitted_changes():
        msg = "Working tree has uncommitted changes. Commit or stash them before running ralph."
        raise AgentLoopError(msg)

    work = from_prompt(prompt)
    branch = f"ralph/{_slugify(prompt)}"

    log(f"🔁 Ralph: {work.title}")

    default_branch = ctx.tracker.get_default_branch()
    ctx.vcs.checkout(default_branch)
    ctx.vcs.pull(default_branch)
    ctx.vcs.checkout_new_branch(branch)

    pushed = False
    try:
        strategy = RalphStrategy(
            agent=ctx.edit_agent,
            prompt_template=RALPH_PROMPT_TEMPLATE,
        )
        t0 = time.monotonic()
        result = loop_until_done(
            work=work,
            strategy=strategy,
            vcs=ctx.vcs,
            max_iterations=max_iterations,
            context=ctx.config.context,
            on_progress=_log_ralph_progress,
        )
        elapsed = int(time.monotonic() - t0)

        if not result.has_changes:
            log_step("⚠️  No changes were made", last=True)
            return

        ctx.vcs.push(branch)
        pushed = True

        status = "completed" if result.converged else f"stopped after {result.iterations} steps"
        pr_body = (
            f"**Goal:** {prompt}\n\n"
            f"**Status:** {status} ({elapsed}s total)\n\n"
            f"---\n\n"
            f"_Opened by `agent-loop ralph` — review before merging._"
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
            ctx.vcs.delete_branch(branch)
