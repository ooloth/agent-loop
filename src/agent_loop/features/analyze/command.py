import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.ports.agent_backend import AgentBackend
from agent_loop.features.analyze.parse import parse_analysis_results
from agent_loop.features.analyze.prompts import ANALYZE_PROMPT
from agent_loop.io.observability.logging import log


def cmd_analyze(ctx: AppContext, agent: AgentBackend) -> None:
    """Analyze the codebase and create GitHub issues."""
    log("🔍 Analyzing codebase...")

    prompt = ctx.config.analyze_prompt or ANALYZE_PROMPT
    if ctx.config.context:
        prompt = f"Project context:\n{ctx.config.context}\n\n{prompt}"

    t0 = time.monotonic()
    raw = agent.run(prompt)

    found_issues = parse_analysis_results(raw)

    elapsed = int(time.monotonic() - t0)
    log(f"🔍 Analysis complete ({elapsed}s) — {len(found_issues)} issue(s) found")

    if not found_issues:
        return

    existing_titles = ctx.tracker.list_open_titles()

    created = 0
    for i, found in enumerate(found_issues):
        if found.title in existing_titles:
            log(f"├── ⏭️  Skipped (already exists): {found.title}")
            continue

        ctx.tracker.create_issue(found)
        is_last = i == len(found_issues) - 1
        connector = "└──" if is_last else "├──"
        log(f"{connector} 📋 Created: {found.title}")
        created += 1

    skipped = len(found_issues) - created
    log(f"✅ {created} created, {skipped} skipped. Add 'ready-to-fix' when ready.")
