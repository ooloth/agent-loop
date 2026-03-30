"""Work specification — what to work on, decoupled from where it came from.

WorkSpec is the uniform input to loop_until_done(). Factory functions
(from_issue, from_prompt, from_file) adapt different input sources into
the same shape.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from agent_loop.domain.models.issues import Issue


@dataclass(frozen=True)
class WorkSpec:
    """A unit of work to be completed by the loop engine.

    Title is for display (may be truncated). Body is the full description
    or goal text passed to the agent.
    """

    title: str
    body: str


def from_issue(issue: Issue) -> WorkSpec:
    """Create a WorkSpec from a tracked issue."""
    return WorkSpec(title=issue.title, body=issue.body)


def from_prompt(prompt: str) -> WorkSpec:
    """Create a WorkSpec from a user-provided goal prompt.

    Title is a truncation for log display; body is the full prompt.
    """
    max_title = 60
    title = prompt[:max_title].rstrip() + "…" if len(prompt) > max_title else prompt
    return WorkSpec(title=title, body=prompt)


def from_file(path: Path) -> WorkSpec:
    """Create a WorkSpec from a markdown file.

    Title is extracted from the first heading (``# ...``). Falls back to
    a truncated first non-blank line when no heading is present.
    """
    content = path.read_text().strip()
    if not content:
        msg = f"Task file is empty: {path}"
        raise ValueError(msg)

    heading_match = re.match(r"^#\s+(.+)", content, re.MULTILINE)
    if heading_match:
        title = heading_match.group(1).strip()
    else:
        first_line = content.split("\n", 1)[0].strip()
        max_title = 60
        title = first_line[:max_title].rstrip() + "…" if len(first_line) > max_title else first_line

    return WorkSpec(title=title, body=content)
