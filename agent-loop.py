#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = ["PyYAML"]
# ///

"""
agent-loop: analyze a codebase for issues, fix them with review, open PRs.

Workflow:
  1. analyze  — agent scans codebase, creates GitHub issues labeled `needs-review`
  2. (human triages on GitHub, relabels to `ready-to-fix`)
  3. fix      — picks up `ready-to-fix` issues, runs fix+review loop, opens PR
"""

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "max_iterations": 3,
    "labels": {
        "needs_review": "needs-review",
        "ready_to_fix": "ready-to-fix",
        "in_progress": "in-progress",
    },
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
        # Merge (shallow for labels)
        if "labels" in overrides:
            config["labels"] = {**config["labels"], **overrides.pop("labels")}
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
        ["claude", "--print", "--no-input", "--prompt", prompt],
        capture_output=True,
        text=True,
        cwd=project_dir,
    )
    if result.returncode != 0:
        print(f"Claude failed: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return result.stdout.strip()


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

    label = config["labels"]["needs_review"]

    # Ensure label exists
    gh("label", "create", label, "--force", "--description", "Agent-found issue awaiting human review")

    for issue in issues:
        title = issue["title"]
        body = issue.get("body", "")
        extra_labels = issue.get("labels", [])
        all_labels = [label] + extra_labels
        label_args = [arg for l in all_labels for arg in ("--label", l)]

        gh("issue", "create", "--title", title, "--body", body, *label_args)
        print(f"  📋 Created: {title}")

    print(f"\n✅ Created {len(issues)} issue(s) labeled '{label}'.")
    print("   Review them on GitHub and relabel to 'ready-to-fix' when ready.")


def cmd_fix(project_dir: Path, config: dict, issue_number: int | None = None) -> None:
    """Pick up ready-to-fix issues and run the fix+review loop."""
    label_ready = config["labels"]["ready_to_fix"]
    label_in_progress = config["labels"]["in_progress"]
    max_iterations = config["max_iterations"]

    # Get issues to fix
    if issue_number:
        issues_json = gh("issue", "view", str(issue_number), "--json", "number,title,body")
        issues = [json.loads(issues_json)]
    else:
        issues_json = gh("issue", "list", "--label", label_ready, "--json", "number,title,body", "--limit", "100")
        issues = json.loads(issues_json)

    if not issues:
        print(f"No issues labeled '{label_ready}' found.")
        return

    print(f"Found {len(issues)} issue(s) to fix.\n")

    for issue in issues:
        fix_single_issue(project_dir, config, issue, label_ready, label_in_progress, max_iterations)


def fix_single_issue(
    project_dir: Path,
    config: dict,
    issue: dict,
    label_ready: str,
    label_in_progress: str,
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

    # Mark as in progress
    gh("issue", "edit", str(number), "--remove-label", label_ready, "--add-label", label_in_progress)

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

        # Open PR
        pr_body = f"Fixes #{number}\n\nAgent review {'passed' if iteration < max_iterations else f'did not converge after {max_iterations} iterations'}."
        gh(
            "pr", "create",
            "--title", f"Fix #{number}: {title}",
            "--body", pr_body,
            "--label", "ready-for-human-review",
            "--head", branch,
        )
        print(f"\n  🎉 PR opened for #{number}!")

        # Clean up issue label
        gh("issue", "edit", str(number), "--remove-label", label_in_progress)

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
              1. agent-loop analyze         → creates GitHub issues labeled 'needs-review'
              2. (human reviews on GitHub, relabels to 'ready-to-fix')
              3. agent-loop fix             → fixes issues and opens PRs
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

    fix_parser = sub.add_parser("fix", help="Fix ready-to-fix issues")
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
