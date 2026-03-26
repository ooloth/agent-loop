import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.issues import Issue
from agent_loop.io.logging import log, log_detail, log_step
from agent_loop.features.fix.branch_session import BranchSession
from agent_loop.features.fix.engine import ImplementAndReviewInput, implement_and_review
from agent_loop.features.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.features.fix.review import format_review_comment


def _log_engine_progress(event: str) -> None:
    """Translate engine progress events into tree-structured log output."""
    if event == "implementing":
        log_step("🤖 Implementing fix...")
    elif event == "no_changes":
        log_step("⚠️  No changes were made", last=True)
    elif event.startswith("review_approved:"):
        # review_approved:1/5:12s
        parts = event.split(":", 3)
        log_step(f"🔎 Review {parts[1]} — ✅ Approved ({parts[2]})")
    elif event.startswith("review_rejected:"):
        # review_rejected:1/5:12s:summary text
        parts = event.split(":", 4)
        iteration, _max = parts[1].split("/")
        is_last = iteration == _max
        log_step(f"🔎 Review {parts[1]} — 🔄 Changes requested ({parts[2]})", last=is_last)
        log_detail(parts[3], last_step=is_last)
    elif event == "addressing_feedback":
        log_step("🤖 Addressing feedback...")


def cmd_fix(ctx: AppContext, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = ctx.config["max_iterations"]

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
    number = issue.number
    title = issue.title
    body = issue.body

    fix_start = time.monotonic()
    log(f"🔧 #{number} {title}")

    with BranchSession(issue, ctx.tracker, ctx.vcs) as session:
        task = ImplementAndReviewInput(
            title=title,
            body=body,
            implement_agent=ctx.edit_agent,
            review_agent=ctx.read_agent,
            vcs=ctx.vcs,
            max_iterations=max_iterations,
            context=ctx.config.get("context", ""),
            fix_prompt_template=ctx.config.get("fix_prompt_template", FIX_PROMPT_TEMPLATE),
            review_prompt=ctx.config.get("review_prompt", REVIEW_PROMPT),
            on_progress=_log_engine_progress,
        )
        result = implement_and_review(task)

        if not result.has_changes:
            log_step(f"⚠️  No changes for #{number}. May already be fixed.", last=True)
            ctx.tracker.comment_on_issue(
                number,
                "## ⚠️ Agent made no changes\n\n"
                "The agent ran but produced no diff. Here's what it said:\n\n"
                f"{result.implement_response}\n\n"
                "---\n\n"
                "Removing `ready-to-fix` — re-add it to retry, or close the issue if it's resolved.",
            )
            ctx.tracker.remove_ready_label(number)
            return

        session.commit_and_push()

        # Open PR — "Fixes #N" will close the issue on merge
        pr_ref = ctx.tracker.open_pr(
            title=f"Fix #{number}: {title}",
            body=f"Fixes #{number}",
            head=session.branch,
        )

        # Post review trail as a PR comment
        review_comment = format_review_comment(result.review_log, result.converged, max_iterations)
        ctx.tracker.comment_on_pr(pr_ref, review_comment)

        total_elapsed = int(time.monotonic() - fix_start)
        log_step(f"🎉 PR opened ({total_elapsed}s total)", last=True)
