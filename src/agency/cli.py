"""CLI entry point — parse args, wire adapters, dispatch to feature commands."""

import argparse
import sys
import textwrap
from pathlib import Path

from agency.domain.config import Config, resolve_planning_model
from agency.domain.context import AppContext
from agency.domain.errors import AgentLoopError
from agency.domain.loop.work import from_file, from_prompt
from agency.features.analyze.command import cmd_analyze
from agency.features.fix.command import cmd_fix, fix_from_spec
from agency.features.plan.command import cmd_plan
from agency.features.ralph.command import cmd_ralph
from agency.features.watch.command import WatchAgents, cmd_watch
from agency.io.adapters.claude_cli import EDIT_TOOLS, READ_ONLY_TOOLS, ClaudeCliBackend
from agency.io.adapters.git import GitBackend
from agency.io.adapters.github import GitHubTracker
from agency.io.bootstrap.config import load_config
from agency.io.observability.logging import configure_logging, log

EFFORT_HELP = "Agent effort level (default: from config or 'high')"


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="agency: automated multi-step workflows for AI coding agents.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            workflow:
              1. agency analyze           → creates GitHub issues
              2. (human adds 'ready-to-fix' label to approved issues)
              3. agency fix               → fixes ready issues and opens PRs
              4. agency fix --issue 42    → fix a specific issue
              5. agency watch             → poll continuously

            standalone:
              agency fix -f spec.md                                   → fix with review from file
              agency fix -p 'handle edge case in parser'              → fix with review from prompt
              agency plan 'add error handling'                        → interactive planning
              agency ralph --plan .agency/plans/add-error-handling.md → execute a plan
              agency ralph -p 'add type hints to foo.py' -n 10       → quick goal
        """),
    )
    parser.add_argument(
        "--project-dir",
        "-d",
        type=Path,
        default=Path.cwd(),
        help="Path to the project (default: current directory)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show debug output (subprocess commands, timing)",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Override the default log file path (.logs/<date>-<command>.log)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    analyze_parser = sub.add_parser("analyze", help="Analyze codebase and create GitHub issues")
    analyze_parser.add_argument("--effort", "-e", help=EFFORT_HELP)

    fix_parser = sub.add_parser("fix", help="Fix ready-to-fix issues")
    fix_source = fix_parser.add_mutually_exclusive_group()
    fix_source.add_argument("--issue", "-i", type=int, help="Fix a specific issue number")
    fix_source.add_argument("--file", "-f", type=Path, help="Markdown file describing the fix")
    fix_source.add_argument("--prompt", "-p", help="Inline description of what to fix")
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
    ralph_goal.add_argument("--plan", "-P", type=Path, help="Plan file from 'agency plan'")
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

    return parser


def _dispatch(args: argparse.Namespace, ctx: AppContext, config: Config) -> None:
    """Wire agent backends and dispatch to the requested feature command."""
    project_dir = ctx.project_dir

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
        if args.file or args.prompt:
            work = from_file(args.file) if args.file else from_prompt(args.prompt)
            fix_from_spec(ctx, work, edit_agent, review_agent)
        else:
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
        agents = WatchAgents(
            analysis=ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.analysis_agent_model,
                effort=config.analysis_agent_effort,
            ),
            coding=ClaudeCliBackend(
                project_dir,
                allowed_tools=EDIT_TOOLS,
                model=config.coding_agent_model,
                effort=config.coding_agent_effort,
            ),
            review=ClaudeCliBackend(
                project_dir,
                allowed_tools=READ_ONLY_TOOLS,
                model=config.review_agent_model,
                effort=config.review_agent_effort,
            ),
        )
        cmd_watch(
            ctx,
            agents,
            interval=args.interval,
            max_open_issues=args.max_open_issues,
        )


def main() -> None:
    """Parse CLI arguments and dispatch to the requested feature command."""
    parser = _build_parser()
    args = parser.parse_args()

    project_dir = args.project_dir.resolve()
    configure_logging(
        verbose=args.verbose,
        command=args.command,
        project_dir=project_dir,
        log_file=args.log_file,
    )
    config = load_config(project_dir)
    ctx = AppContext(
        project_dir=project_dir,
        config=config,
        tracker=GitHubTracker(project_dir),
        vcs=GitBackend(project_dir),
    )

    try:
        _dispatch(args, ctx, config)
    except AgentLoopError as exc:
        # Clean user-facing message — no traceback. TRY400 wants logging.exception()
        # here but that would dump a stack trace for routine operational errors.
        log.error("Error: %s", exc)
        sys.exit(1)
