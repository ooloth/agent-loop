"""Fix command — pick up ready issues, run fix+review loop, open PRs.

Two modes:
- Issue-based (cmd_fix): fetches issues from the tracker, runs through
  BranchSession for branch lifecycle and issue locking.
- Spec-based (fix_from_spec): works from a file or prompt, manages its
  own branch lifecycle without issue locking.

Both modes use AntagonisticStrategy and post a review trail on the PR.
"""

import re
import time
from collections.abc import Callable

from agency.domain.context import AppContext
from agency.domain.errors import AgentLoopError
from agency.domain.loop.engine import (
    AddressedFeedback,
    DiffReady,
    EngineEvent,
    Implemented,
    LoopOptions,
    NoChanges,
    ReviewApproved,
    ReviewRejected,
    loop_until_done,
)
from agency.domain.loop.strategies import AntagonisticStrategy
from agency.domain.loop.work import WorkSpec, from_issue
from agency.domain.models.issues import Issue
from agency.domain.ports.agent_backend import AgentBackend
from agency.features.fix.branch_session import BranchSession
from agency.features.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agency.features.fix.review import format_review_comment
from agency.io.observability.logging import log, log_detail, log_step


def _make_progress_logger(
    issue_number: int | None = None,
) -> Callable[[EngineEvent], None]:
    """Build a progress callback that prefixes log lines with the issue number."""
    tag = f"#{issue_number} " if issue_number else ""

    def on_progress(event: EngineEvent) -> None:
        match event:
            case Implemented(elapsed_seconds=s):
                log_step(f"{tag}🤖 Implemented fix ({s}s)")
            case NoChanges():
                log_step(f"{tag}⚠️  No changes were made", last=True)
            case DiffReady(lines=n):
                log.debug("%sDiff size: %d lines", tag, n)
                large_diff_threshold = 500
                if n > large_diff_threshold:
                    log.warning("%sLarge diff (%d lines) — agent may have over-scoped", tag, n)
            case ReviewApproved(iteration=i, max_iterations=m, elapsed_seconds=s):
                log.debug("%sReview verdict: approved", tag)
                log_step(f"{tag}🔎 Review {i}/{m} — ✅ Approved ({s}s)")
            case ReviewRejected(iteration=i, max_iterations=m, elapsed_seconds=s, summary=summary):
                log.debug("%sReview verdict: rejected", tag)
                is_last = i >= m
                log_step(f"{tag}🔎 Review {i}/{m} — 🔄 Changes requested ({s}s)", last=is_last)
                log_detail(f"{tag}{summary}", last_step=is_last)
            case AddressedFeedback(elapsed_seconds=s):
                log_step(f"{tag}🤖 Addressed feedback ({s}s)")

    return on_progress


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
    """Pick up ready-to-fix issues and run the fix+review loop.

    Guards (evaluated before acquiring any lock):
    - --issue N with missing issue → log warning, skip.
    - --issue N not ready-to-fix → log warning, skip.
    - --issue N already claimed → log warning, skip.
    - No ready issues → log "no issues ready to fix", return.
    """
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
    """Fix a single issue with the review loop.

    No-changes path: if the engine produces no diff, posts a comment on the
    issue with the implement agent's initial response for diagnostic context,
    removes the ready-to-fix label, and lets BranchSession cleanup release
    the lock and delete the branch. The human can re-add ready-to-fix to retry.
    """
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
                on_progress=_make_progress_logger(issue.number),
            ),
        )

        if not result.has_changes:
            log.warning("└── #%d ⚠️  No changes. May already be fixed.", issue.number)
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
        log_step(f"#{issue.number} 🎉 PR opened ({total_elapsed}s total)", last=True)


def fix_from_spec(
    ctx: AppContext,
    work: WorkSpec,
    edit_agent: AgentBackend,
    review_agent: AgentBackend,
) -> None:
    """Run the antagonistic fix+review loop from a WorkSpec (file or prompt).

    Branch lifecycle:
    - Rejects uncommitted changes upfront (raises AgentLoopError).
    - Creates fix/<slugified-title> branch from the default branch.
    - Opens a draft PR on success (converged or not).
    - Always returns to the default branch on exit.
    - Deletes the fix branch if nothing was pushed (early return or exception).
    """
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
                on_progress=_make_progress_logger(),
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
            f"_Opened by `agency fix` — review before merging._"
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
