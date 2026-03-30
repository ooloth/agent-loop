"""CLI entry point — parse args, wire adapters, dispatch to feature commands."""

import argparse
import sys
import textwrap
from pathlib import Path

from agent_loop.domain.config import resolve_planning_model
from agent_loop.domain.context import AppContext
from agent_loop.domain.errors import AgentLoopError
from agent_loop.features.analyze.command import cmd_analyze
from agent_loop.features.fix.command import cmd_fix
from agent_loop.features.plan.command import cmd_plan
from agent_loop.features.ralph.command import cmd_ralph
from agent_loop.features.watch.command import cmd_watch
from agent_loop.io.adapters.claude_cli import EDIT_TOOLS, READ_ONLY_TOOLS, ClaudeCliBackend
from agent_loop.io.adapters.git import GitBackend
from agent_loop.io.adapters.github import GitHubTracker
from agent_loop.io.bootstrap.config import load_config

EFFORT_HELP = "Agent effort level (default: from config or 'high')"


def main() -> None:
    """Parse CLI arguments and dispatch to the requested feature command."""
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

            standalone:
              agent-loop plan 'add error handling'                   → interactive planning
              agent-loop ralph --plan .plans/add-error-handling.md   → execute a plan
              agent-loop ralph -p 'add type hints to foo.py' -n 10  → quick goal
        """),
    )
    parser.add_argument(
        "--project-dir",
        "-d",
        type=Path,
        default=Path.cwd(),
        help="Path to the project (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    analyze_parser = sub.add_parser("analyze", help="Analyze codebase and create GitHub issues")
    analyze_parser.add_argument("--effort", "-e", help=EFFORT_HELP)

    fix_parser = sub.add_parser("fix", help="Fix ready-to-fix issues")
    fix_parser.add_argument("--issue", "-i", type=int, help="Fix a specific issue number")
    fix_parser.add_argument("--effort", "-e", help=EFFORT_HELP)
    fix_parser.add_argument(
        "--review-effort", help="Review agent effort level (default: from config or 'high')"
    )

    plan_parser = sub.add_parser(
        "plan",
        help="Interactive planning session to produce a ralph-ready plan file",
    )
    plan_parser.add_argument(
        "idea", nargs="?", help="Your rough idea (optional — the agent will ask)"
    )
    plan_parser.add_argument(
        "--model",
        "-m",
        help="Model override (default: ANTHROPIC_DEFAULT_OPUS_MODEL or claude-opus-4-6)",
    )
    plan_parser.add_argument("--effort", "-e", help=EFFORT_HELP)

    ralph_parser = sub.add_parser("ralph", help="Iterative fresh-eyes refinement toward a goal")
    ralph_goal = ralph_parser.add_mutually_exclusive_group(required=True)
    ralph_goal.add_argument("--prompt", "-p", help="Goal for the agent to achieve")
    ralph_goal.add_argument("--file", "-f", type=Path, help="Markdown file containing the goal")
    ralph_goal.add_argument("--plan", "-P", type=Path, help="Plan file from 'agent-loop plan'")
    ralph_parser.add_argument(
        "--max-iterations",
        "-n",
        type=int,
        default=5,
        help="Maximum iterations before stopping (default: 5)",
    )
    ralph_parser.add_argument("--effort", "-e", help=EFFORT_HELP)

    watch_parser = sub.add_parser("watch", help="Poll continuously for work")
    watch_parser.add_argument(
        "--interval", type=int, default=300, help="Seconds between polls (default: 300)"
    )
    watch_parser.add_argument(
        "--max-open-issues",
        type=int,
        default=3,
        help="Max issues awaiting review before pausing analysis (default: 3)",
    )

    args = parser.parse_args()
    project_dir = args.project_dir.resolve()
    config = load_config(project_dir)

    ctx = AppContext(
        project_dir=project_dir,
        config=config,
        tracker=GitHubTracker(),
        vcs=GitBackend(project_dir),
    )

    try:
        if args.command == "analyze":
            agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.analysis_agent_model,
                effort=args.effort or config.analysis_agent_effort,
            )
            cmd_analyze(ctx, agent)

        elif args.command == "fix":
            edit_agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=EDIT_TOOLS,
                model=config.coding_agent_model,
                effort=args.effort or config.coding_agent_effort,
            )
            review_agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.review_agent_model,
                effort=args.review_effort or config.review_agent_effort,
            )
            cmd_fix(ctx, edit_agent, review_agent, issue_number=args.issue)

        elif args.command == "plan":
            resolved_model = resolve_planning_model(config.planning_agent_model, args.model)
            agent = ClaudeCliBackend(
                project_dir,
                model=resolved_model,
                effort=args.effort or config.planning_agent_effort,
            )
            cmd_plan(ctx, agent, idea=args.idea)

        elif args.command == "ralph":
            agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=EDIT_TOOLS,
                model=config.coding_agent_model,
                effort=args.effort or config.coding_agent_effort,
            )
            plan_or_file = args.plan or args.file
            cmd_ralph(
                ctx,
                agent,
                prompt=args.prompt,
                file=plan_or_file,
                max_iterations=args.max_iterations,
            )

        elif args.command == "watch":
            analysis_agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.analysis_agent_model,
                effort=config.analysis_agent_effort,
            )
            coding_agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=EDIT_TOOLS,
                model=config.coding_agent_model,
                effort=config.coding_agent_effort,
            )
            review_agent = ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.review_agent_model,
                effort=config.review_agent_effort,
            )
            cmd_watch(
                ctx,
                analysis_agent,
                coding_agent,
                review_agent,
                interval=args.interval,
                max_open_issues=args.max_open_issues,
            )

    except AgentLoopError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
