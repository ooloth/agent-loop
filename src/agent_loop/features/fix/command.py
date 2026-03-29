import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.loop.engine import (
    AddressingFeedback,
    EngineEvent,
    Implementing,
    NoChanges,
    ReviewApproved,
    ReviewRejected,
    loop_until_done,
)
from agent_loop.domain.loop.strategies import AntagonisticStrategy
from agent_loop.domain.loop.work import work_from_issue
from agent_loop.domain.models.issues import Issue
from agent_loop.features.fix.branch_session import BranchSession
from agent_loop.features.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.features.fix.review import format_review_comment
from agent_loop.io.observability.logging import log, log_detail, log_step


def _log_engine_progress(event: EngineEvent) -> None:
    """Translate engine progress events into tree-structured log output."""
    match event:
        case Implementing():
            log_step("🤖 Implementing fix...")
        case NoChanges():
            log_step("⚠️  No changes were made", last=True)
        case ReviewApproved(iteration=i, max_iterations=m, elapsed_seconds=s):
            log_step(f"🔎 Review {i}/{m} — ✅ Approved ({s}s)")
        case ReviewRejected(iteration=i, max_iterations=m, elapsed_seconds=s, summary=summary):
            is_last = i >= m
            log_step(f"🔎 Review {i}/{m} — 🔄 Changes requested ({s}s)", last=is_last)
            log_detail(summary, last_step=is_last)
        case AddressingFeedback():
            log_step("🤖 Addressing feedback...")


def cmd_fix(ctx: AppContext, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = ctx.config.max_iterations

    # Get issues to fix
    if issue_number:
        issue = ctx.tracker.get_issue(issue_number)
        if issue is None:
            log(f"⚠️  Issue #{issue_number} not found. Skipping.")
            return
        if not ctx.tracker.is_ready_to_fix(issue):
            log(f"⚠️  Issue #{issue_number} is not labeled 'ready-to-fix'. Skipping.")
            return
        if ctx.tracker.is_claimed(issue):
            log(f"⚠️  Issue #{issue_number} already has 'agent-fix-in-progress'. Skipping.")
            return
        issues = [issue]
    else:
        issues = ctx.tracker.list_ready_issues()

    if not issues:
        log("💤 No issues ready to fix")
        return

    for issue in issues:
        fix_single_issue(ctx, issue, max_iterations)


def fix_single_issue(ctx: AppContext, issue: Issue, max_iterations: int) -> None:
    """Fix a single issue with the review loop."""
    work = work_from_issue(issue)
    fix_start = time.monotonic()
    log(f"🔧 #{issue.number} {issue.title}")

    with BranchSession(issue, ctx.tracker, ctx.vcs) as session:
        strategy = AntagonisticStrategy(
            implement_agent=ctx.edit_agent,
            review_agent=ctx.read_agent,
            fix_prompt_template=ctx.config.fix_prompt_template or FIX_PROMPT_TEMPLATE,
            review_prompt=ctx.config.review_prompt or REVIEW_PROMPT,
        )
        result = loop_until_done(
            work=work,
            strategy=strategy,
            vcs=ctx.vcs,
            max_iterations=max_iterations,
            context=ctx.config.context,
            on_progress=_log_engine_progress,
        )

        if not result.has_changes:
            log_step(f"⚠️  No changes for #{issue.number}. May already be fixed.", last=True)
            ctx.tracker.comment_on_issue(
                issue.number,
                "## ⚠️ Agent made no changes\n\n"
                "The agent ran but produced no diff. Here's what it said:\n\n"
                f"{strategy.initial_response}\n\n"
                "---\n\n"
                "Removing `ready-to-fix` — re-add it to retry, or close the issue if it's resolved.",
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
