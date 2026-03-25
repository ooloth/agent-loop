import textwrap
from pathlib import Path

import yaml

from agent_loop._core.types import Config

DEFAULT_CONFIG: Config = {
    "max_iterations": 5,
    "analyze_prompt": textwrap.dedent("""\
        Analyze this codebase for issues. For each issue found, respond with a JSON array
        of objects, each with:
          - "title": short summary (suitable for a GitHub issue title)
          - "body": issue description formatted in markdown using EXACTLY this structure:

            ## 🐛 Problem
            One or two sentences describing what is wrong.

            ## 📍 Location
            - `file.py:42` — `function_name()`
            - (list each relevant location as a bullet)

            ## 💥 Impact
            - What happens as a result
            - Why it matters
            - How severe (e.g. crash, silent data loss, cosmetic)

            ## 🔄 Current Behavior
            What the code does now (briefly, with a short code snippet if helpful).

            ## ✅ Expected Behavior
            What the code should do instead.

            Use bullet lists instead of paragraphs where possible. Keep it scannable.

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
        Prefer the simplest solution. If a problem can be avoided entirely (e.g. by
        choosing a different value, removing a constraint, or sidestepping the issue),
        that is better than adding error handling for a problem that doesn't need to exist.
    """),
    "review_prompt": textwrap.dedent("""\
        Review the current git diff as a fix for a GitHub issue.

        You are a strict reviewer. Do NOT rubber-stamp approvals. Your job is to catch
        problems before a human sees this PR. If you are unsure about something, flag it
        as a concern — do not give the benefit of the doubt.

        Be proportionate. Focus on problems that will realistically occur, not hypothetical
        scenarios that require extreme conditions. If an edge case can be avoided entirely
        by a simpler approach (e.g. using a different value, removing an unnecessary
        constraint), suggest that simpler approach instead of requesting error handling.

        You MUST check each of the following IN ORDER and state your finding for each:
        1. Approach: Is this the right way to solve the problem? Is there a simpler, more
           idiomatic, or more robust approach the implementer should have taken instead?
           Consider whether the problem can be avoided entirely rather than handled.
           If the approach is wrong, stop here — do not review the details of a solution
           that should be rewritten.
        2. Correctness: Does the change actually fix the described issue? Fully, not partially?
        3. Regressions: Could this break existing behavior? Consider all callers and code paths.
        4. Edge cases: Are realistic boundary conditions and error cases handled?
        5. Completeness: Is every aspect of the issue addressed? Are there leftover TODOs or gaps?

        Structure your response EXACTLY as follows (use these headings verbatim).
        Use bullet lists under each heading — no paragraphs. One finding per bullet.

        #### 🧭 Approach
        - <your assessment — is this the right solution, or is there a better way?>

        #### ✅ Correctness
        - <finding>
        - <finding>

        #### 🔁 Regressions
        - <finding>

        #### 🧪 Edge Cases
        - <finding>
        - <finding>

        #### 📋 Completeness
        - <finding>

        ---

        **Verdict**: LGTM or CONCERNS

        If your verdict is CONCERNS, add a final section:

        #### 🔧 Required Changes
        - <describe EXACTLY what needs to change — be specific about what code to add,
          modify, or remove. Vague feedback like "needs verification" is not acceptable.>

        Focus on correctness — do NOT nitpick style.
    """),
    "context": "",
}


def load_config(project_dir: Path) -> Config:
    """Load config from .agent-loop.yml in the project directory, merged with defaults."""
    config = dict(DEFAULT_CONFIG)
    config_file = project_dir / ".agent-loop.yml"
    if config_file.exists():
        with open(config_file) as f:
            # Filter out null values so they fall back to defaults rather than overriding them
            overrides = {
                k: v for k, v in (yaml.safe_load(f) or {}).items() if v is not None
            }
        config.update(overrides)
    return config  # type: ignore[return-value]
