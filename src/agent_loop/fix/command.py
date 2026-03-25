import json
import time
from pathlib import Path

from agent_loop._core import (
    ImplementAndReviewInput,
    Label,
    ensure_label,
    gh,
    git,
    implement_and_review,
    log,
    log_step,
)
from agent_loop.fix.prompts import FIX_PROMPT_TEMPLATE, REVIEW_PROMPT
from agent_loop.fix.review import format_review_comment


def cmd_fix(project_dir: Path, config: dict, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = config["max_iterations"]

    # Get issues to fix
    if issue_number:
        issues_json = gh(
            "issue", "view", str(issue_number), "--json", "number,title,body,labels"
        )
        issue = json.loads(issues_json)
        labels = {label["name"] for label in issue.get("labels", [])}
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
        task = ImplementAndReviewInput(
            title=title,
            body=body,
            project_dir=project_dir,
            max_iterations=max_iterations,
            context=config.get("context", ""),
            fix_prompt_template=config.get("fix_prompt_template", FIX_PROMPT_TEMPLATE),
            review_prompt=config.get("review_prompt", REVIEW_PROMPT),
        )
        result = implement_and_review(task)

        # Commit and push
        if not result.has_changes:
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
        review_comment = format_review_comment(result.review_log, result.converged, max_iterations)
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
