import argparse
import textwrap
from pathlib import Path

from agent_loop.domain.context import AppContext
from agent_loop.io.config import load_config
from agent_loop.io.adapters.claude_cli import ClaudeCliBackend
from agent_loop.io.adapters.github import GitHubTracker
from agent_loop.features.analyze.command import cmd_analyze
from agent_loop.features.fix.command import cmd_fix
from agent_loop.features.watch.command import cmd_watch


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
        "--project-dir",
        "-d",
        type=Path,
        default=Path.cwd(),
        help="Path to the project (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("analyze", help="Analyze codebase and create GitHub issues")

    fix_parser = sub.add_parser("fix", help="Fix ready-to-fix issues")
    fix_parser.add_argument(
        "--issue", "-i", type=int, help="Fix a specific issue number"
    )

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
        agent=ClaudeCliBackend(project_dir),
        tracker=GitHubTracker(),
    )

    if args.command == "analyze":
        cmd_analyze(ctx)
    elif args.command == "fix":
        cmd_fix(ctx, issue_number=args.issue)
    elif args.command == "watch":
        cmd_watch(ctx, interval=args.interval, max_open_issues=args.max_open_issues)
