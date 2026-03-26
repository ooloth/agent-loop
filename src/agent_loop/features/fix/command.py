import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.issues import Issue
from agent_loop.io.adapters.claude_cli import EDIT_TOOLS, READ_ONLY_TOOLS, ClaudeCliBackend
from agent_loop.io.adapters.git import GitBackend
from agent_loop.io.logging import log, log_step
from agent_loop.features.fix.engine import ImplementAndReviewInput, implement_and_review
from agent_loop.features.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.features.fix.review import format_review_comment


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
    branch = f"fix/issue-{number}"

    # Local git backend for branch workflow operations
    git = GitBackend()

    fix_start = time.monotonic()
    log(f"🔧 #{number} {title}")

    # Create branch off the repo's default branch (not whatever is currently checked out).
    # Pull before claiming the issue so a network failure doesn't leave the lock label stuck.
    default_branch = ctx.tracker.get_default_branch()
    git.checkout(default_branch)
    git.pull(default_branch)

    # Claim the issue — add lock label
    ctx.tracker.claim_issue(number)

    # -B resets the branch if a prior attempt left it behind
    git.checkout_new_branch(branch)

    pr_opened = False

    try:
        implement_agent = ClaudeCliBackend(ctx.project_dir, allowed_tools=EDIT_TOOLS)
        review_agent = ClaudeCliBackend(ctx.project_dir, allowed_tools=READ_ONLY_TOOLS)

        task = ImplementAndReviewInput(
            title=title,
            body=body,
            implement_agent=implement_agent,
            review_agent=review_agent,
            vcs=git,
            max_iterations=max_iterations,
            context=ctx.config.get("context", ""),
            fix_prompt_template=ctx.config.get(
                "fix_prompt_template", FIX_PROMPT_TEMPLATE
            ),
            review_prompt=ctx.config.get("review_prompt", REVIEW_PROMPT),
        )
        result = implement_and_review(task)

        # Commit and push
        if not result.has_changes:
            log_step(f"⚠️  No changes for #{number}. May already be fixed.", last=True)
            ctx.tracker.comment_on_issue(
                number,
                "Agent attempted a fix but no changes were needed. This issue may already be resolved.\n\n"
                "Removing `ready-to-fix` — re-add it to retry, or close the issue if it's resolved.",
            )
            ctx.tracker.remove_ready_label(number)
            return

        git.commit(f"fix: address issue #{number} - {title}")
        git.push(branch)

        # Open PR — "Fixes #N" will close the issue on merge
        pr_ref = ctx.tracker.open_pr(
            title=f"Fix #{number}: {title}",
            body=f"Fixes #{number}",
            head=branch,
        )

        # Post review trail as a PR comment
        review_comment = format_review_comment(result.review_log, result.converged, max_iterations)
        ctx.tracker.comment_on_pr(pr_ref, review_comment)

        pr_opened = True
        total_elapsed = int(time.monotonic() - fix_start)
        log_step(f"🎉 PR opened ({total_elapsed}s total)", last=True)

    finally:
        # Always return to default branch and clean up if no PR was opened
        git.checkout(default_branch)
        if not pr_opened:
            git.delete_branch(branch)
            ctx.tracker.release_issue(number)
