"""Analyze command — scan codebase and file issues."""

import time

from agency.domain.context import AppContext
from agency.domain.ports.agent_backend import AgentBackend
from agency.features.analyze.parse import parse_analysis_results
from agency.features.analyze.prompts import ANALYZE_PROMPT
from agency.io.observability.logging import log


def cmd_analyze(ctx: AppContext, agent: AgentBackend) -> None:
    """Analyze the codebase and create GitHub issues."""
    log.info("🔍 Analyzing codebase...")

    prompt = ctx.config.analyze_prompt or ANALYZE_PROMPT
    if ctx.config.context:
        prompt = f"Project context:\n{ctx.config.context}\n\n{prompt}"

    t0 = time.monotonic()
    raw = agent.run(prompt)

    found_issues = parse_analysis_results(raw)

    elapsed = int(time.monotonic() - t0)
    log.info("🔍 Analysis complete (%ds) — %d issue(s) found", elapsed, len(found_issues))

    if not found_issues:
        return

    existing_titles = ctx.tracker.list_open_titles()

    created = 0
    for i, found in enumerate(found_issues):
        if found.title in existing_titles:
            log.info("├── ⏭️  Skipped (already exists): %s", found.title)
            continue

        ctx.tracker.create_issue(found)
        is_last = i == len(found_issues) - 1
        connector = "└──" if is_last else "├──"
        log.info("%s 📋 Created: %s", connector, found.title)
        created += 1

    skipped = len(found_issues) - created
    log.info("✅ %d created, %d skipped. Add 'ready-to-fix' when ready.", created, skipped)
