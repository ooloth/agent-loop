#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML"]
# ///

"""
agent-loop: analyze a codebase for issues, fix them with review, open PRs.

Workflow:
  1. analyze  — agent scans codebase, creates GitHub issues
  2. (human reviews on GitHub, approves issues for fixing)
  3. fix      — picks up approved issues, runs fix+review loop, opens PRs
"""

import argparse
import json
import subprocess
import sys
import textwrap
from enum import StrEnum
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Labels
# ---------------------------------------------------------------------------


class Label(StrEnum):
    """Issue labels tracking origin, approval, and workflow state.

    Lifecycle:
      REPORTED (analyzer)  →  APPROVED (human)  →  FIX_IN_PROGRESS (fixer)  →  issue closed by PR merge
                                                                                (all labels persist)
    """

    # Permanent — origin and audit trail
    AGENT_REPORTED = "agent-reported"
    HUMAN_APPROVED = "human-approved"

    # Transient — workflow state
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    AGENT_FIX_IN_PROGRESS = "agent-fix-in-progress"


LABEL_DESCRIPTIONS = {
    Label.AGENT_REPORTED: "Issue found by automated analysis",
    Label.HUMAN_APPROVED: "Reviewed and approved by a human",
    Label.NEEDS_HUMAN_REVIEW: "Awaiting human triage",
    Label.AGENT_FIX_IN_PROGRESS: "Agent is working on a fix",
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "max_iterations": 3,
    "analyze_prompt": textwrap.dedent("""\
        Analyze this codebase for issues. For each issue found, respond with a JSON array
        of objects, each with:
          - "title": short summary (suitable for a GitHub issue title)
          - "body": detailed description including file paths, line numbers, and why it matters
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
    """),
    "review_prompt": textwrap.dedent("""\
        Review the current git diff for problems. You are reviewing a fix for a GitHub issue.

        Check for:
        1. Does the change actually fix the described issue?
        2. Could it introduce regressions?
        3. Are there obvious correctness problems?
        4. Are edge cases handled?

        If everything looks good, respond with exactly: LGTM
        If there are concerns, describe them clearly so they can be addressed.
        Do NOT nitpick style — focus on correctness and completeness.

        Respond with ONLY "LGTM" or your concerns. No other text.
    """),
    "context": "",
}


def load_config(project_dir: Path) -> dict:
    """Load config from .agent-loop.yml in the project directory, merged with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_file = project_dir / ".agent-loop.yml"
    if config_file.exists():
        with open(config_file) as f:
            overrides = yaml.safe_load(f) or {}
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


def claude(prompt: str, project_dir: Path) -> str:
    """Run a prompt through the claude CLI."""
    result = subprocess.run(
        ["claude", "-p", prompt],
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
# Commands
# ---------------------------------------------------------------------------


def cmd_analyze(project_dir: Path, config: dict) -> None:
    """Analyze the codebase and create GitHub issues."""
    print("🔍 Analyzing codebase...")

    prompt = config["analyze_prompt"]
    if config["context"]:
        prompt = f"Project context:\n{config['context']}\n\n{prompt}"

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

    if not issues:
        print("✅ No issues found.")
        return

    # Ensure workflow labels exist
    ensure_label(Label.AGENT_REPORTED)
    ensure_label(Label.NEEDS_HUMAN_REVIEW)

    for issue in issues:
        title = issue["title"]
        body = issue.get("body", "")
        extra_labels = issue.get("labels", [])

        # Ensure extra labels exist
        for l in extra_labels:
            gh("label", "create", l, "--force", "--description", "")

        all_labels = [Label.AGENT_REPORTED, Label.NEEDS_HUMAN_REVIEW] + extra_labels
        label_args = [arg for l in all_labels for arg in ("--label", str(l))]
        gh("issue", "create", "--title", title, "--body", body, *label_args)
        print(f"  📋 Created: {title}")

    print(f"\n✅ Created {len(issues)} issue(s).")
    print(f"   Review them on GitHub: swap '{Label.NEEDS_HUMAN_REVIEW}' for '{Label.HUMAN_APPROVED}' when ready.")


def cmd_fix(project_dir: Path, config: dict, issue_number: int | None = None) -> None:
    """Pick up human-approved issues and run the fix+review loop."""
    max_iterations = config["max_iterations"]

    # Get issues to fix
    if issue_number:
        issues_json = gh("issue", "view", str(issue_number), "--json", "number,title,body,labels")
        issue = json.loads(issues_json)
        labels = {l["name"] for l in issue.get("labels", [])}
        if Label.HUMAN_APPROVED not in labels:
            print(f"⚠️  Issue #{issue_number} is not labeled '{Label.HUMAN_APPROVED}'. Skipping.")
            return
        if Label.AGENT_FIX_IN_PROGRESS in labels:
            print(f"⚠️  Issue #{issue_number} already has '{Label.AGENT_FIX_IN_PROGRESS}'. Skipping.")
            return
        issues = [issue]
    else:
        issues_json = gh(
            "issue", "list",
            "--label", Label.HUMAN_APPROVED,
            "--search", f"-label:{Label.AGENT_FIX_IN_PROGRESS}",
            "--json", "number,title,body",
            "--limit", "100",
        )
        issues = json.loads(issues_json)

    if not issues:
        print(f"No issues labeled '{Label.HUMAN_APPROVED}' (without '{Label.AGENT_FIX_IN_PROGRESS}') found.")
        return

    print(f"Found {len(issues)} issue(s) to fix.\n")

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

    print(f"{'='*60}")
    print(f"🔧 Fixing #{number}: {title}")
    print(f"{'='*60}\n")

    # Claim the issue — add lock label
    ensure_label(Label.AGENT_FIX_IN_PROGRESS)
    gh("issue", "edit", str(number), "--add-label", Label.AGENT_FIX_IN_PROGRESS)

    # Create branch
    default_branch = git("rev-parse", "--abbrev-ref", "HEAD")
    git("checkout", "-b", branch)

    try:
        # Initial fix
        fix_prompt = config["fix_prompt_template"].format(title=title, body=body)
        if config["context"]:
            fix_prompt = f"Project context:\n{config['context']}\n\n{fix_prompt}"

        print("  🤖 Agent is implementing fix...")
        claude(fix_prompt, project_dir)

        # Stage changes
        git("add", "-A")

        # Review loop
        iteration = 0
        while iteration < max_iterations:
            iteration += 1
            print(f"\n  🔎 Review iteration {iteration}/{max_iterations}...")

            diff = git("diff", "--cached")
            if not diff:
                print("  ⚠️  No changes were made. Skipping.")
                break

            review_prompt = config["review_prompt"] + f"\n\nHere is the diff:\n\n{diff}"
            if config["context"]:
                review_prompt = f"Project context:\n{config['context']}\n\n{review_prompt}"

            feedback = claude(review_prompt, project_dir)

            if "LGTM" in feedback.upper().split():
                print("  ✅ Review passed!")
                break

            print(f"  💬 Reviewer concerns:\n{textwrap.indent(feedback, '     ')}\n")

            if iteration >= max_iterations:
                print(f"  ⚠️  Max iterations ({max_iterations}) reached. Opening PR with concerns noted.")
                break

            # Address feedback
            fix_feedback_prompt = (
                f"Your previous fix received this review feedback:\n\n{feedback}\n\n"
                f"Original issue:\nTitle: {title}\nDescription:\n{body}\n\n"
                f"Please address the concerns."
            )
            print("  🤖 Agent is addressing feedback...")
            claude(fix_feedback_prompt, project_dir)
            git("add", "-A")

        # Commit and push
        diff_check = git("diff", "--cached")
        if not diff_check:
            print(f"\n  ⚠️  No changes for #{number}. Skipping PR.")
            git("checkout", default_branch)
            git("branch", "-D", branch)
            return

        git("commit", "-m", f"fix: address issue #{number} - {title}")
        git("push", "-u", "origin", branch)

        # Open PR — "Fixes #N" will close the issue on merge
        converged = iteration < max_iterations
        pr_body = (
            f"Fixes #{number}\n\n"
            f"Agent review {'passed' if converged else f'did not converge after {max_iterations} iterations'}."
        )
        gh(
            "pr", "create",
            "--title", f"Fix #{number}: {title}",
            "--body", pr_body,
            "--head", branch,
        )
        print(f"\n  🎉 PR opened for #{number}!")

    finally:
        # Always return to default branch
        git("checkout", default_branch)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="agent-loop: analyze, fix, and review code with AI agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            workflow:
              1. agent-loop analyze         → creates GitHub issues
              2. (human reviews on GitHub, swaps 'needs-human-review' for 'human-approved')
              3. agent-loop fix             → fixes approved issues and opens PRs
              3. agent-loop fix --issue 42  → fix a specific issue
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

    fix_parser = sub.add_parser("fix", help="Fix human-approved issues")
    fix_parser.add_argument("--issue", "-i", type=int, help="Fix a specific issue number")

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    config = load_config(project_dir)

    if args.command == "analyze":
        cmd_analyze(project_dir, config)
    elif args.command == "fix":
        cmd_fix(project_dir, config, issue_number=args.issue)


if __name__ == "__main__":
    main()
