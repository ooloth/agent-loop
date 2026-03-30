"""Fix command — pick up ready issues, run fix+review loop, open PRs."""

import re
import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.errors import AgentLoopError
from agent_loop.domain.loop.engine import (
    AddressedFeedback,
    EngineEvent,
    Implemented,
    LoopOptions,
    NoChanges,
    ReviewApproved,
    ReviewRejected,
    loop_until_done,
)
from agent_loop.domain.loop.strategies import AntagonisticStrategy
from agent_loop.domain.loop.work import WorkSpec, from_issue
from agent_loop.domain.models.issues import Issue
from agent_loop.domain.ports.agent_backend import AgentBackend
from agent_loop.features.fix.branch_session import BranchSession
from agent_loop.features.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.features.fix.review import format_review_comment
from agent_loop.io.observability.logging import log, log_detail, log_step


def _log_engine_progress(event: EngineEvent) -> None:
    """Translate engine progress events into tree-structured log output."""
    match event:
        case Implemented(elapsed_seconds=s):
            log_step(f"🤖 Implemented fix ({s}s)")
        case NoChanges():
            log_step("⚠️  No changes were made", last=True)
        case ReviewApproved(iteration=i, max_iterations=m, elapsed_seconds=s):
            log_step(f"🔎 Review {i}/{m} — ✅ Approved ({s}s)")
        case ReviewRejected(iteration=i, max_iterations=m, elapsed_seconds=s, summary=summary):
            is_last = i >= m
            log_step(f"🔎 Review {i}/{m} — 🔄 Changes requested ({s}s)", last=is_last)
            log_detail(summary, last_step=is_last)
        case AddressedFeedback(elapsed_seconds=s):
            log_step(f"🤖 Addressed feedback ({s}s)")


def _slugify(text: str, max_len: int = 50) -> str:
    """Convert text to a branch-name-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def cmd_fix(
    ctx: AppContext,
    edit_agent: AgentBackend,
    review_agent: AgentBackend,
    issue_number: int | None = None,
) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = ctx.config.max_iterations

    # Get issues to fix
    if issue_number:
        issue = ctx.tracker.get_issue(issue_number)
        if issue is None:
            log.warning("⚠️  Issue #%d not found. Skipping.", issue_number)
            return
        if not ctx.tracker.is_ready_to_fix(issue):
            log.warning("⚠️  Issue #%d is not labeled 'ready-to-fix'. Skipping.", issue_number)
            return
        if ctx.tracker.is_claimed(issue):
            log.warning("⚠️  Issue #%d already has 'agent-fix-in-progress'. Skipping.", issue_number)
            return
        issues = [issue]
    else:
        issues = ctx.tracker.list_ready_issues()

    if not issues:
        log.info("💤 No issues ready to fix")
        return

    for issue in issues:
        fix_single_issue(ctx, issue, max_iterations, edit_agent, review_agent)


def fix_single_issue(
    ctx: AppContext,
    issue: Issue,
    max_iterations: int,
    edit_agent: AgentBackend,
    review_agent: AgentBackend,
) -> None:
    """Fix a single issue with the review loop."""
    work = from_issue(issue)
    fix_start = time.monotonic()
    log.info("🔧 #%d %s", issue.number, issue.title)

    with BranchSession(issue, ctx.tracker, ctx.vcs) as session:
        strategy = AntagonisticStrategy(
            implement_agent=edit_agent,
            review_agent=review_agent,
            fix_prompt_template=ctx.config.fix_prompt_template or FIX_PROMPT_TEMPLATE,
            review_prompt=ctx.config.review_prompt or REVIEW_PROMPT,
        )
        result = loop_until_done(
            work=work,
            strategy=strategy,
            vcs=ctx.vcs,
            options=LoopOptions(
                max_iterations=max_iterations,
                context=ctx.config.context,
                on_progress=_log_engine_progress,
            ),
        )

        if not result.has_changes:
            log.warning("└── ⚠️  No changes for #%d. May already be fixed.", issue.number)
            ctx.tracker.comment_on_issue(
                issue.number,
                "## ⚠️ Agent made no changes\n\n"
                "The agent ran but produced no diff. Here's what it said:\n\n"
                f"{strategy.initial_response}\n\n"
                "---\n\n"
                "Removing `ready-to-fix` — re-add it to retry,"
                " or close the issue if it's resolved.",
            )
            ctx.tracker.remove_ready_label(issue.number)
            return

        session.commit_and_push()

        # Open PR — "Fixes #N" will close the issue on merge
        pr_ref = ctx.tracker.open_pr(
            title=f"Fix #{issue.number}: {issue.title}",
            body=f"Fixes #{issue.number}",
            head=session.branch,
        )

        # Post review trail as a PR comment
        review_comment = format_review_comment(
            strategy.review_log, converged=result.converged, max_iterations=max_iterations
        )
        ctx.tracker.comment_on_pr(pr_ref, review_comment)

        total_elapsed = int(time.monotonic() - fix_start)
        log_step(f"🎉 PR opened ({total_elapsed}s total)", last=True)


def fix_from_spec(
    ctx: AppContext,
    work: WorkSpec,
    edit_agent: AgentBackend,
    review_agent: AgentBackend,
) -> None:
    """Run the antagonistic fix+review loop from a WorkSpec (file or prompt)."""
    if ctx.vcs.has_uncommitted_changes():
        msg = "Working tree has uncommitted changes. Commit or stash them before running fix."
        raise AgentLoopError(msg)

    max_iterations = ctx.config.max_iterations
    branch = f"fix/{_slugify(work.title)}"

    log.info("🔧 Fix: %s", work.title)

    default_branch = ctx.tracker.get_default_branch()
    ctx.vcs.checkout(default_branch)
    ctx.vcs.pull(default_branch)
    ctx.vcs.checkout_new_branch(branch)

    pushed = False
    try:
        strategy = AntagonisticStrategy(
            implement_agent=edit_agent,
            review_agent=review_agent,
            fix_prompt_template=ctx.config.fix_prompt_template or FIX_PROMPT_TEMPLATE,
            review_prompt=ctx.config.review_prompt or REVIEW_PROMPT,
        )
        t0 = time.monotonic()
        result = loop_until_done(
            work=work,
            strategy=strategy,
            vcs=ctx.vcs,
            options=LoopOptions(
                max_iterations=max_iterations,
                context=ctx.config.context,
                on_progress=_log_engine_progress,
            ),
        )
        elapsed = int(time.monotonic() - t0)

        if not result.has_changes:
            log.warning("└── ⚠️  No changes were made")
            return

        ctx.vcs.commit(f"fix: {work.title}")
        ctx.vcs.push(branch)
        pushed = True

        status = "converged" if result.converged else f"stopped after {result.iterations} reviews"
        pr_body = (
            f"**Goal:** {work.body}\n\n"
            f"**Status:** {status} ({elapsed}s total)\n\n"
            f"---\n\n"
            f"_Opened by `agent-loop fix` — review before merging._"
        )
        pr_ref = ctx.tracker.open_pr(
            title=f"Fix: {work.title}",
            body=pr_body,
            head=branch,
            draft=True,
        )

        # Post review trail as a PR comment
        review_comment = format_review_comment(
            strategy.review_log, converged=result.converged, max_iterations=max_iterations
        )
        ctx.tracker.comment_on_pr(pr_ref, review_comment)

        if result.converged:
            log_step(f"🎉 Done — draft PR opened ({elapsed}s total)", last=True)
        else:
            log_step(
                f"⚠️  Hit iteration cap ({result.iterations}/{max_iterations})"
                f" — draft PR opened ({elapsed}s total)",
                last=True,
            )
    finally:
        ctx.vcs.checkout(default_branch)
        if not pushed:
            log.warning("Cleaning up branch %s (no changes pushed)", branch)
            ctx.vcs.delete_branch(branch)
