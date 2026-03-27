import json
import re
import time

from agent_loop.domain.context import AppContext
from agent_loop.domain.errors import AnalysisParseError
from agent_loop.domain.issues import FoundIssue
from agent_loop.io.observability.logging import log
from agent_loop.features.analyze.prompts import ANALYZE_PROMPT


def parse_analysis_results(raw: str) -> list[dict]:
    """Parse the JSON issue list from an agent response.

    Agents sometimes wrap JSON in a fenced code block; this handles both
    the bare-JSON and fenced-block cases.

    Raises AnalysisParseError if the response isn't valid JSON.
    """
    match = re.search(r"```(?:\w+)?\n(.*?)```", raw, re.DOTALL)
    json_str = match.group(1) if match else raw

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        raise AnalysisParseError(raw) from None


def cmd_analyze(ctx: AppContext) -> None:
    """Analyze the codebase and create GitHub issues."""
    log("🔍 Analyzing codebase...")

    prompt = ctx.config.analyze_prompt or ANALYZE_PROMPT
    if ctx.config.context:
        prompt = f"Project context:\n{ctx.config.context}\n\n{prompt}"

    t0 = time.monotonic()
    raw = ctx.read_agent.run(prompt)

    issues = parse_analysis_results(raw)

    elapsed = int(time.monotonic() - t0)
    log(f"🔍 Analysis complete ({elapsed}s) — {len(issues)} issue(s) found")

    if not issues:
        return

    existing_titles = ctx.tracker.list_open_titles()

    created = 0
    for i, issue in enumerate(issues):
        found = FoundIssue(
            title=issue["title"],
            body=issue.get("body", ""),
            labels=issue.get("labels", []),
        )
        if found.title in existing_titles:
            log(f"├── ⏭️  Skipped (already exists): {found.title}")
            continue

        ctx.tracker.create_issue(found)
        is_last = i == len(issues) - 1
        connector = "└──" if is_last else "├──"
        log(f"{connector} 📋 Created: {found.title}")
        created += 1

    skipped = len(issues) - created
    log(f"✅ {created} created, {skipped} skipped. Add 'ready-to-fix' when ready.")
