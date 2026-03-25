import json
import time
from pathlib import Path

from agent_loop._core import (
    Label,
    claude,
    ensure_label,
    gh,
    log,
)
from agent_loop.analyze.parse import extract_json_from_response
from agent_loop.analyze.prompts import ANALYZE_PROMPT


def cmd_analyze(project_dir: Path, config: dict) -> None:
    """Analyze the codebase and create GitHub issues."""
    log("🔍 Analyzing codebase...")

    prompt = config.get("analyze_prompt", ANALYZE_PROMPT)
    if config.get("context"):
        prompt = f"Project context:\n{config['context']}\n\n{prompt}"

    t0 = time.monotonic()
    raw = claude(prompt, project_dir)

    issues = extract_json_from_response(raw)

    elapsed = int(time.monotonic() - t0)
    log(f"🔍 Analysis complete ({elapsed}s) — {len(issues)} issue(s) found")

    if not issues:
        return

    # Ensure workflow labels exist
    ensure_label(Label.AGENT_REPORTED)
    ensure_label(Label.NEEDS_HUMAN_REVIEW)

    # Fetch existing open issue titles to avoid duplicates
    existing_json = gh(
        "issue", "list", "--state", "open", "--json", "title", "--limit", "2000"
    )
    existing_titles = {i["title"] for i in json.loads(existing_json)}

    created = 0
    for issue in issues:
        title = issue["title"]
        if title in existing_titles:
            log(f"├── ⏭️  Skipped (already exists): {title}")
            continue

        body = issue.get("body", "")
        extra_labels = issue.get("labels", [])

        # Ensure extra labels exist
        for l in extra_labels:
            gh("label", "create", l, "--force", "--description", "")

        all_labels = [Label.AGENT_REPORTED, Label.NEEDS_HUMAN_REVIEW] + extra_labels
        label_args = [arg for l in all_labels for arg in ("--label", str(l))]
        gh("issue", "create", "--title", title, "--body", body, *label_args)
        is_last = issue is issues[-1]
        connector = "└──" if is_last else "├──"
        log(f"{connector} 📋 Created: {title}")
        created += 1

    skipped = len(issues) - created
    log(
        f"✅ {created} created, {skipped} skipped. Add '{Label.READY_TO_FIX}' when ready."
    )
