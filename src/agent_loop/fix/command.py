import json
import time
from pathlib import Path

from agent_loop._core import (
    Label,
    claude,
    ensure_label,
    gh,
    git,
    log,
    log_detail,
    log_step,
)
from agent_loop.fix.parse import parse_review_verdict
from agent_loop.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.fix.review import format_review_comment, summarize_feedback


def cmd_fix(project_dir: Path, config: dict, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = config["max_iterations"]

    # Get issues to fix
    if issue_number:
        issues_json = gh(
            "issue", "view", str(issue_number), "--json", "number,title,body,labels"
        )
        issue = json.loads(issues_json)
        labels = {l["name"] for l in issue.get("labels", [])}
        if Label.READY_TO_FIX not in labels:
            log(
                f"⚠️  Issue #{issue_number} is not labeled '{Label.READY_TO_FIX}'. Skipping."
            )
            return
        if Label.AGENT_FIX_IN_PROGRESS in labels:
            log(
                f"⚠️  Issue #{issue_number} already has '{Label.AGENT_FIX_IN_PROGRESS}'. Skipping."
            )
            return
        issues = [issue]
    else:
        issues_json = gh(
            "issue",
            "list",
            "--label",
            Label.READY_TO_FIX,
            "--search",
            f"-label:{Label.AGENT_FIX_IN_PROGRESS}",
            "--json",
            "number,title,body",
            "--limit",
            "100",
        )
        issues = json.loads(issues_json)

    if not issues:
        log(f"💤 No issues labeled '{Label.READY_TO_FIX}'")
        return

    for issue in issues:
        fix_single_issue(project_dir, config, issue, max_iterations)


def fix_single_issue(
    project_dir: Path,
    config: dict,
    issue: dict,
    max_iterations: int,
) -> None:
    """Fix a single issue with the review loop."""
    number = issue["number"]
    title = issue["title"]
    body = issue["body"]
    branch = f"fix/issue-{number}"

    fix_start = time.monotonic()
    log(f"🔧 #{number} {title}")

    # Create branch off the repo's default branch (not whatever is currently checked out).
    # Pull before claiming the issue so a network failure doesn't leave the lock label stuck.
    default_branch = gh(
        "repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"
    )
    git("checkout", default_branch)
    git("pull", "--ff-only", "origin", default_branch)

    # Claim the issue — add lock label
    ensure_label(Label.AGENT_FIX_IN_PROGRESS)
    gh("issue", "edit", str(number), "--add-label", Label.AGENT_FIX_IN_PROGRESS)

    # -B resets the branch if a prior attempt left it behind
    git("checkout", "-B", branch)

    pr_opened = False

    try:
        # Initial fix
        fix_prompt_template = config.get("fix_prompt_template", FIX_PROMPT_TEMPLATE)
        fix_prompt = fix_prompt_template.format(title=title, body=body)
        if config.get("context"):
            fix_prompt = f"Project context:\n{config['context']}\n\n{fix_prompt}"

        t0 = time.monotonic()
        log_step("🤖 Implementing fix...")
        claude(fix_prompt, project_dir)

        # Stage changes
        git("add", "-A")

        # Review loop
        iteration = 0
        review_log: list[dict] = []
        converged = False
        review_prompt_base = config.get("review_prompt", REVIEW_PROMPT)
        while iteration < max_iterations:
            iteration += 1

            diff = git("diff", "--cached")
            if not diff:
                log_step("⚠️  No changes were made", last=True)
                break

            review_prompt = (
                review_prompt_base
                + f"\n\n## Issue being fixed\n\nTitle: {title}\nDescription:\n{body}"
                + f"\n\n## Diff to review\n\n{diff}"
            )
            if config.get("context"):
                review_prompt = (
                    f"Project context:\n{config['context']}\n\n{review_prompt}"
                )

            t0 = time.monotonic()
            feedback = claude(review_prompt, project_dir)
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
                log_step(f"🔎 Review {iteration}/{max_iterations} — ✅ Approved ({review_elapsed}s)")
                converged = True
                break

            is_last_iteration = iteration >= max_iterations
            log_step(
                f"🔎 Review {iteration}/{max_iterations} — 🔄 Changes requested ({review_elapsed}s)",
                last=is_last_iteration,
            )
            log_detail(summarize_feedback(feedback), last_step=is_last_iteration)

            if is_last_iteration:
                break

            # Address feedback
            fix_feedback_prompt = (
                f"Your previous fix received this review feedback:\n\n{feedback}\n\n"
                f"Original issue:\nTitle: {title}\nDescription:\n{body}\n\n"
                f"Please address the concerns. Prefer the simplest solution — if a problem\n"
                f"can be eliminated rather than handled, do that instead."
            )
            log_step("🤖 Addressing feedback...")
            claude(fix_feedback_prompt, project_dir)
            git("add", "-A")

        # Commit and push
        diff_check = git("diff", "--cached")
        if not diff_check:
            log_step(f"⚠️  No changes for #{number}. May already be fixed.", last=True)
            gh(
                "issue",
                "comment",
                str(number),
                "--body",
                "Agent attempted a fix but no changes were needed. This issue may already be resolved.\n\n"
                "Removing `ready-to-fix` — re-add it to retry, or close the issue if it's resolved.",
            )
            gh("issue", "edit", str(number), "--remove-label", Label.READY_TO_FIX)
            return

        git("commit", "-m", f"fix: address issue #{number} - {title}")
        git("push", "--force-with-lease", "-u", "origin", branch)

        # Open PR — "Fixes #N" will close the issue on merge
        pr_body = f"Fixes #{number}"
        gh(
            "pr",
            "create",
            "--title",
            f"Fix #{number}: {title}",
            "--body",
            pr_body,
            "--head",
            branch,
        )

        # Post review trail as a PR comment
        review_comment = format_review_comment(review_log, converged, max_iterations)
        gh("pr", "comment", branch, "--body", review_comment)

        pr_opened = True
        total_elapsed = int(time.monotonic() - fix_start)
        log_step(f"🎉 PR opened ({total_elapsed}s total)", last=True)

    finally:
        # Always return to default branch and clean up if no PR was opened
        git("checkout", default_branch)
        if not pr_opened:
            git("branch", "-D", branch)
            gh(
                "issue",
                "edit",
                str(number),
                "--remove-label",
                Label.AGENT_FIX_IN_PROGRESS,
            )
