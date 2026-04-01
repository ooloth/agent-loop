"""Watch command — poll for work in a continuous loop."""

import signal
import time
from dataclasses import dataclass

from agency.domain.context import AppContext
from agency.domain.errors import AgentLoopError, invariant
from agency.domain.ports.agent_backend import AgentBackend
from agency.features.analyze.command import cmd_analyze
from agency.features.fix.command import cmd_fix
from agency.io.observability.logging import log


@dataclass(frozen=True)
class WatchAgents:
    """The three agent backends needed by the watch loop."""

    analysis: AgentBackend
    coding: AgentBackend
    review: AgentBackend


def cmd_watch(
    ctx: AppContext,
    agents: WatchAgents,
    interval: int,
    max_open_issues: int,
) -> None:
    """Poll for work: fix ready issues, analyze when queue is low.

    Catches AgentLoopError per iteration so a transient failure (bad network,
    flaky subprocess) doesn't kill the daemon. The error is logged and the
    loop continues on the next cycle.
    """
    invariant(interval >= 1, "interval should never be < 1", interval=interval)
    invariant(
        max_open_issues >= 1,
        "max_open_issues should never be < 1",
        max_open_issues=max_open_issues,
    )

    stopping = False

    def handle_signal(_sig: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True
        log.info("\n⏹️  Stopping after current step completes...")

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    log.info(
        "👀 Watching %s (interval=%ds, max_open=%d)",
        ctx.project_dir.name,
        interval,
        max_open_issues,
    )
    log.info("   Press Ctrl+C to stop gracefully.")
    log.info("")

    cycle = 0
    while not stopping:
        cycle += 1
        log.info("🔄 Cycle %d", cycle)

        try:
            _poll_once(ctx, agents, max_open_issues)
        except AgentLoopError as exc:
            log.warning("❌ Error during cycle %d: %s", cycle, exc)
            log.warning("   Will retry next cycle.")

        if stopping:
            break

        # Sleep in small increments so Ctrl+C is responsive
        log.info("😴 Sleeping %ds...", interval)
        log.info("")
        for _ in range(interval):
            if stopping:
                break
            time.sleep(1)

    log.info("👋 Stopped after %d cycle(s).", cycle)


def _poll_once(
    ctx: AppContext,
    agents: WatchAgents,
    max_open_issues: int,
) -> None:
    """Run one fix + analyze cycle. Exceptions propagate to the caller."""
    # Step 1: Fix any ready-to-fix issues
    cmd_fix(ctx, agents.coding, agents.review)

    # Step 2: Analyze if queue is below cap
    open_count = len(ctx.tracker.list_awaiting_review())

    if open_count >= max_open_issues:
        log.info(
            "⏸️  %d issue(s) awaiting review (cap: %d) — skipping analysis",
            open_count,
            max_open_issues,
        )
    else:
        log.info(
            "🔍 %d issue(s) awaiting review (cap: %d) — running analysis",
            open_count,
            max_open_issues,
        )
        cmd_analyze(ctx, agents.analysis)
