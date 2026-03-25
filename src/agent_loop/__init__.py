"""
agent-loop: analyze a codebase for issues, fix them with review, open PRs.

Workflow:
  1. analyze  — agent scans codebase, creates GitHub issues
  2. (human reviews on GitHub, adds 'ready-to-fix')
  3. fix      — picks up ready-to-fix issues, runs fix+review loop, opens PRs
"""

import argparse
import json
import re
import subprocess
import sys
import textwrap
import time
from datetime import datetime
from enum import StrEnum
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class Label(StrEnum):
    """Issue labels tracking origin and workflow state.

    Agent issue lifecycle:
      agent-reported, needs-human-review  →  ready-to-fix  →  agent-fix-in-progress  →  closed by PR merge

    Human issue lifecycle:
      ready-to-fix  →  agent-fix-in-progress  →  closed by PR merge
    """

    # Permanent — origin
    AGENT_REPORTED = "agent-reported"

    # Transient — workflow state
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    READY_TO_FIX = "ready-to-fix"

    # Permanent — lock
    AGENT_FIX_IN_PROGRESS = "agent-fix-in-progress"


LABEL_DESCRIPTIONS = {
    Label.AGENT_REPORTED: "Issue found by automated analysis",
    Label.NEEDS_HUMAN_REVIEW: "Awaiting human triage",
    Label.READY_TO_FIX: "Approved for agent to fix",
    Label.AGENT_FIX_IN_PROGRESS: "Agent is working on a fix",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "max_iterations": 5,
    "analyze_prompt": textwrap.dedent("""\
        Analyze this codebase for issues. For each issue found, respond with a JSON array
        of objects, each with:
          - "title": short summary (suitable for a GitHub issue title)
          - "body": issue description formatted in markdown using EXACTLY this structure:

            ## 🐛 Problem
            One or two sentences describing what is wrong.

            ## 📍 Location
            - `file.py:42` — `function_name()`
            - (list each relevant location as a bullet)

            ## 💥 Impact
            - What happens as a result
            - Why it matters
            - How severe (e.g. crash, silent data loss, cosmetic)

            ## 🔄 Current Behavior
            What the code does now (briefly, with a short code snippet if helpful).

            ## ✅ Expected Behavior
            What the code should do instead.

            Use bullet lists instead of paragraphs where possible. Keep it scannable.

          - "labels": optional list of additional labels (e.g. "bug", "refactor", "performance")

        Focus on real, actionable problems — not style nitpicks.
        Respond ONLY with the JSON array, no other text.
    """),
    "fix_prompt_template": textwrap.dedent("""\
        Fix the following issue:

        Title: {title}
        Description:
        {body}

        Make the minimal changes needed to address this issue.
        Prefer the simplest solution. If a problem can be avoided entirely (e.g. by
        choosing a different value, removing a constraint, or sidestepping the issue),
        that is better than adding error handling for a problem that doesn't need to exist.
    """),
    "review_prompt": textwrap.dedent("""\
        Review the current git diff as a fix for a GitHub issue.

        You are a strict reviewer. Do NOT rubber-stamp approvals. Your job is to catch
        problems before a human sees this PR. If you are unsure about something, flag it
        as a concern — do not give the benefit of the doubt.

        Be proportionate. Focus on problems that will realistically occur, not hypothetical
        scenarios that require extreme conditions. If an edge case can be avoided entirely
        by a simpler approach (e.g. using a different value, removing an unnecessary
        constraint), suggest that simpler approach instead of requesting error handling.

        You MUST check each of the following IN ORDER and state your finding for each:
        1. Approach: Is this the right way to solve the problem? Is there a simpler, more
           idiomatic, or more robust approach the implementer should have taken instead?
           Consider whether the problem can be avoided entirely rather than handled.
           If the approach is wrong, stop here — do not review the details of a solution
           that should be rewritten.
        2. Correctness: Does the change actually fix the described issue? Fully, not partially?
        3. Regressions: Could this break existing behavior? Consider all callers and code paths.
        4. Edge cases: Are realistic boundary conditions and error cases handled?
        5. Completeness: Is every aspect of the issue addressed? Are there leftover TODOs or gaps?

        Structure your response EXACTLY as follows (use these headings verbatim):

        #### 🧭 Approach
        <your assessment — is this the right solution, or is there a better way?>

        #### ✅ Correctness
        <your finding>

        #### 🔁 Regressions
        <your finding>

        #### 🧪 Edge Cases
        <your finding>

        #### 📋 Completeness
        <your finding>

        ---

        **Verdict**: LGTM or CONCERNS

        If your verdict is CONCERNS, add a final section:

        #### 🔧 Required Changes
        <describe EXACTLY what needs to change — be specific about what code to add,
        modify, or remove. Vague feedback like "needs verification" is not acceptable.>

        Focus on correctness — do NOT nitpick style.
    """),
    "context": "",
}


def load_config(project_dir: Path) -> dict:
    """Load config from .agent-loop.yml in the project directory, merged with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_file = project_dir / ".agent-loop.yml"
    if config_file.exists():
        with open(config_file) as f:
            # Filter out null values so they fall back to defaults rather than overriding them
            overrides = {k: v for k, v in (yaml.safe_load(f) or {}).items() if v is not None}
        config.update(overrides)
    return config


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------


def run(cmd: list[str], check: bool = True, capture: bool = True) -> str:
    """Run a command and return stdout."""
    result = subprocess.run(cmd, capture_output=capture, text=True)
    if check and result.returncode != 0:
        print(f"Command failed: {' '.join(cmd)}", file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip() if capture else ""


def gh(*args: str) -> str:
    """Run a gh CLI command."""
    return run(["gh", *args])


def git(*args: str) -> str:
    """Run a git command."""
    return run(["git", *args])


# Read-only tools for analysis and review (no filesystem writes or shell execution)
_READ_ONLY_TOOLS = "Read,Glob,Grep"
# Tools needed to implement fixes (scoped to project dir via cwd)
_EDIT_TOOLS = "Read,Write,Edit,MultiEdit,Glob,Grep,Bash"


def claude(prompt: str, project_dir: Path, allowed_tools: str = _EDIT_TOOLS) -> str:
    """Run a prompt through the claude CLI with restricted tool access."""
    result = subprocess.run(
        ["claude", "-p", prompt, "--allowedTools", allowed_tools],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    if result.returncode != 0:
        print(f"Claude failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


def ensure_label(label: Label) -> None:
    """Ensure a label exists in the repo."""
    gh("label", "create", label.value, "--force", "--description", LABEL_DESCRIPTIONS[label])


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def log(msg: str, prefix: str = "") -> None:
    """Log a timestamped message."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[{timestamp}] {prefix}{msg}")


def log_step(msg: str, last: bool = False) -> None:
    """Log a step under the current issue."""
    connector = "└──" if last else "├──"
    log(f"{connector} {msg}")


def log_detail(msg: str, last_step: bool = False) -> None:
    """Log a detail line under the current step."""
    rail = " " if last_step else "│"
    log(f"{rail}      {msg}")


def summarize_feedback(feedback: str, max_len: int = 80) -> str:
    """Extract a one-line summary from reviewer feedback."""
    # Look for the Required Changes section first
    match = re.search(r"#### 🔧 Required Changes\s*\n(.+)", feedback)
    if match:
        summary = match.group(1).strip().rstrip(".")
    else:
        # Fall back to first substantive line after a heading
        for line in feedback.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("**") and not line.startswith("---"):
                summary = line.rstrip(".")
                break
        else:
            summary = "(no details)"
    if len(summary) > max_len:
        summary = summary[:max_len - 1] + "…"
    return summary


def format_review_comment(review_log: list[dict], converged: bool, max_iterations: int) -> str:
    """Format the review trail as a readable GitHub comment."""
    total = len(review_log)
    approved_count = sum(1 for r in review_log if r["approved"])
    rejected_count = total - approved_count

    # Header with status
    if converged:
        status = f"✅ Passed after {total} iteration{'s' if total != 1 else ''}"
    else:
        status = f"⚠️ Did not converge after {max_iterations} iterations"

    lines = [
        f"## 🔍 Agent Review — {status}",
        "",
        f"> **{total}** iteration{'s' if total != 1 else ''}"
        f" · **{approved_count}** approved"
        f" · **{rejected_count}** requested changes",
        "",
        "---",
        "",
    ]

    for r in review_log:
        iteration = r["iteration"]
        approved = r["approved"]
        feedback = r["feedback"]
        icon = "✅" if approved else "🔄"
        label = "Approved" if approved else "Changes requested"
        is_last = iteration == total

        # Last iteration is open, previous ones are collapsed
        if is_last:
            lines.append(f"### {icon} Iteration {iteration} — {label}")
            lines.append("")
            lines.append(feedback)
            lines.append("")
        else:
            lines.append(f"<details>")
            lines.append(f"<summary>{icon} <strong>Iteration {iteration}</strong> — {label}</summary>")
            lines.append("")
            lines.append(feedback)
            lines.append("")
            lines.append("</details>")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_analyze(project_dir: Path, config: dict) -> None:
    """Analyze the codebase and create GitHub issues."""
    log("🔍 Analyzing codebase...")

    prompt = config["analyze_prompt"]
    if config["context"]:
        prompt = f"Project context:\n{config['context']}\n\n{prompt}"

    t0 = time.monotonic()
    raw = claude(prompt, project_dir)

    # Parse JSON from response (handle markdown code fences)
    json_str = raw
    if "```" in json_str:
        lines = json_str.split("\n")
        in_block = False
        block_lines = []
        for line in lines:
            if line.startswith("```"):
                in_block = not in_block
                continue
            if in_block:
                block_lines.append(line)
        json_str = "\n".join(block_lines)

    try:
        issues = json.loads(json_str)
    except json.JSONDecodeError:
        print("Failed to parse agent response as JSON:", file=sys.stderr)
        print(raw, file=sys.stderr)
        sys.exit(1)

    elapsed = int(time.monotonic() - t0)
    log(f"🔍 Analysis complete ({elapsed}s) — {len(issues)} issue(s) found")

    if not issues:
        return

    # Ensure workflow labels exist
    ensure_label(Label.AGENT_REPORTED)
    ensure_label(Label.NEEDS_HUMAN_REVIEW)

    # Fetch existing open issue titles to avoid duplicates
    existing_json = gh("issue", "list", "--state", "open", "--json", "title", "--limit", "2000")
    existing_titles = {i["title"] for i in json.loads(existing_json)}

    created = 0
    for issue in issues:
        title = issue["title"]
        if title in existing_titles:
            log(f"├── ⏭️  Skipped (already exists): {title}")
            continue

        body = issue.get("body", "")
        extra_labels = issue.get("labels", [])

        # Ensure extra labels exist
        for l in extra_labels:
            gh("label", "create", l, "--force", "--description", "")

        all_labels = [Label.AGENT_REPORTED, Label.NEEDS_HUMAN_REVIEW] + extra_labels
        label_args = [arg for l in all_labels for arg in ("--label", str(l))]
        gh("issue", "create", "--title", title, "--body", body, *label_args)
        is_last = issue is issues[-1]
        connector = "└──" if is_last else "├──"
        log(f"{connector} 📋 Created: {title}")
        created += 1

    skipped = len(issues) - created
    log(f"✅ {created} created, {skipped} skipped. Add '{Label.READY_TO_FIX}' when ready.")


def cmd_fix(project_dir: Path, config: dict, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    max_iterations = config["max_iterations"]

    # Get issues to fix
    if issue_number:
        issues_json = gh("issue", "view", str(issue_number), "--json", "number,title,body,labels")
        issue = json.loads(issues_json)
        labels = {l["name"] for l in issue.get("labels", [])}
        if Label.READY_TO_FIX not in labels:
            log(f"⚠️  Issue #{issue_number} is not labeled '{Label.READY_TO_FIX}'. Skipping.")
            return
        if Label.AGENT_FIX_IN_PROGRESS in labels:
            log(f"⚠️  Issue #{issue_number} already has '{Label.AGENT_FIX_IN_PROGRESS}'. Skipping.")
            return
        issues = [issue]
    else:
        issues_json = gh(
            "issue", "list",
            "--label", Label.READY_TO_FIX,
            "--search", f"-label:{Label.AGENT_FIX_IN_PROGRESS}",
            "--json", "number,title,body",
            "--limit", "100",
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

    # Claim the issue — add lock label
    ensure_label(Label.AGENT_FIX_IN_PROGRESS)
    gh("issue", "edit", str(number), "--add-label", Label.AGENT_FIX_IN_PROGRESS)

    # Create branch off the repo's default branch (not whatever is currently checked out)
    default_branch = gh("repo", "view", "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name")
    git("checkout", default_branch)
    git("checkout", "-B", branch)
    pr_opened = False

    try:
        # Initial fix
        fix_prompt = config["fix_prompt_template"].format(title=title, body=body)
        if config["context"]:
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
        while iteration < max_iterations:
            iteration += 1

            diff = git("diff", "--cached")
            if not diff:
                log_step("⚠️  No changes were made", last=True)
                break

            review_prompt = (
                config["review_prompt"]
                + f"\n\n## Issue being fixed\n\nTitle: {title}\nDescription:\n{body}"
                + f"\n\n## Diff to review\n\n{diff}"
            )
            if config["context"]:
                review_prompt = f"Project context:\n{config['context']}\n\n{review_prompt}"

            t0 = time.monotonic()
            feedback = claude(review_prompt, project_dir)
            review_elapsed = int(time.monotonic() - t0)
            approved = bool(re.search(r"\bLGTM\b", feedback, re.IGNORECASE))

            review_log.append({
                "iteration": iteration,
                "approved": approved,
                "feedback": feedback,
            })

            if approved:
                log_step(f"🔎 Review {iteration}/{max_iterations} — ✅ Approved ({review_elapsed}s)", last=True)
                converged = True
                break

            is_last_iteration = iteration >= max_iterations
            log_step(f"🔎 Review {iteration}/{max_iterations} — 🔄 Changes requested ({review_elapsed}s)", last=is_last_iteration)
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
            gh("issue", "comment", str(number), "--body",
               "Agent attempted a fix but no changes were needed. This issue may already be resolved.\n\n"
               "Removing `ready-to-fix` — re-add it to retry, or close the issue if it's resolved.")
            gh("issue", "edit", str(number), "--remove-label", Label.READY_TO_FIX)
            return

        git("commit", "-m", f"fix: address issue #{number} - {title}")
        git("push", "--force-with-lease", "-u", "origin", branch)

        # Open PR — "Fixes #N" will close the issue on merge
        pr_body = f"Fixes #{number}"
        gh(
            "pr", "create",
            "--title", f"Fix #{number}: {title}",
            "--body", pr_body,
            "--head", branch,
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
            gh("issue", "edit", str(number), "--remove-label", Label.AGENT_FIX_IN_PROGRESS)


# ---------------------------------------------------------------------------
# Watch
# ---------------------------------------------------------------------------


def cmd_watch(
    project_dir: Path,
    config: dict,
    interval: int,
    max_open_issues: int,
) -> None:
    """Poll for work: fix ready issues, analyze when queue is low."""
    import signal

    stopping = False

    def handle_signal(sig: int, frame: object) -> None:
        nonlocal stopping
        stopping = True
        log("\n⏹️  Stopping after current step completes...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log(f"👀 Watching {project_dir.name} (interval={interval}s, max_open={max_open_issues})")
    log(f"   Press Ctrl+C to stop gracefully.")
    print()

    while not stopping:
        # Step 1: Fix any ready-to-fix issues
        ready_json = gh(
            "issue", "list",
            "--label", Label.READY_TO_FIX,
            "--search", f"-label:{Label.AGENT_FIX_IN_PROGRESS}",
            "--json", "number,title",
            "--limit", "100",
        )
        ready_issues = json.loads(ready_json)

        if ready_issues:
            cmd_fix(project_dir, config)
            if stopping:
                break
        else:
            log("💤 No issues ready to fix")

        # Step 2: Analyze if queue is below cap
        open_json = gh(
            "issue", "list",
            "--label", Label.NEEDS_HUMAN_REVIEW,
            "--json", "number",
            "--limit", "100",
        )
        open_count = len(json.loads(open_json))

        if open_count >= max_open_issues:
            log(f"⏸️  {open_count} issue(s) awaiting review (cap: {max_open_issues}) — skipping analysis")
        else:
            log(f"🔍 {open_count} issue(s) awaiting review (cap: {max_open_issues}) — running analysis")
            cmd_analyze(project_dir, config)

        if stopping:
            break

        # Sleep in small increments so Ctrl+C is responsive
        log(f"😴 Sleeping {interval}s...")
        print()
        for _ in range(interval):
            if stopping:
                break
            time.sleep(1)

    log("👋 Stopped.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="agent-loop: analyze, fix, and review code with AI agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            workflow:
              1. agent-loop analyze           → creates GitHub issues
              2. (human adds 'ready-to-fix' label to approved issues)
              3. agent-loop fix               → fixes ready issues and opens PRs
              4. agent-loop fix --issue 42    → fix a specific issue
              5. agent-loop watch             → poll continuously
        """),
    )
    parser.add_argument(
        "--project-dir", "-d",
        type=Path,
        default=Path.cwd(),
        help="Path to the project (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("analyze", help="Analyze codebase and create GitHub issues")

    fix_parser = sub.add_parser("fix", help="Fix ready-to-fix issues")
    fix_parser.add_argument("--issue", "-i", type=int, help="Fix a specific issue number")

    watch_parser = sub.add_parser("watch", help="Poll continuously for work")
    watch_parser.add_argument("--interval", type=int, default=300, help="Seconds between polls (default: 300)")
    watch_parser.add_argument("--max-open-issues", type=int, default=3, help="Max issues awaiting review before pausing analysis (default: 3)")

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    config = load_config(project_dir)

    if args.command == "analyze":
        cmd_analyze(project_dir, config)
    elif args.command == "fix":
        cmd_fix(project_dir, config, issue_number=args.issue)
    elif args.command == "watch":
        cmd_watch(project_dir, config, interval=args.interval, max_open_issues=args.max_open_issues)


if __name__ == "__main__":
    main()
