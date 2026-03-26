import signal
import time

from agent_loop.domain.context import AppContext
from agent_loop.io.logging import log
from agent_loop.features.analyze.command import cmd_analyze
from agent_loop.features.fix.command import cmd_fix


def cmd_watch(ctx: AppContext, interval: int, max_open_issues: int) -> None:
    """Poll for work: fix ready issues, analyze when queue is low."""
    stopping = False

    def handle_signal(sig: int, frame: object) -> None:
        nonlocal stopping
        stopping = True
        log("\n⏹️  Stopping after current step completes...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log(
        f"👀 Watching {ctx.project_dir.name} (interval={interval}s, max_open={max_open_issues})"
    )
    log("   Press Ctrl+C to stop gracefully.")
    print()

    while not stopping:
        # Step 1: Fix any ready-to-fix issues
        ready_issues = ctx.tracker.list_ready_issues()

        if ready_issues:
            cmd_fix(ctx)
            if stopping:
                break
        else:
            log("💤 No issues ready to fix")

        # Step 2: Analyze if queue is below cap
        open_count = len(ctx.tracker.list_awaiting_review())

        if open_count >= max_open_issues:
            log(
                f"⏸️  {open_count} issue(s) awaiting review (cap: {max_open_issues}) — skipping analysis"
            )
        else:
            log(
                f"🔍 {open_count} issue(s) awaiting review (cap: {max_open_issues}) — running analysis"
            )
            cmd_analyze(ctx)

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
