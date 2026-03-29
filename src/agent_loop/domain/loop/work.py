"""Work specification — what to work on, decoupled from where it came from."""

from dataclasses import dataclass

from agent_loop.domain.models.issues import Issue


@dataclass(frozen=True)
class WorkSpec:
    """A unit of work to be completed by the loop engine."""

    title: str
    body: str


def work_from_issue(issue: Issue) -> WorkSpec:
    """Create a WorkSpec from a tracked issue."""
    return WorkSpec(title=issue.title, body=issue.body)


def work_from_prompt(prompt: str) -> WorkSpec:
    """Create a WorkSpec from a user-provided goal prompt.

    Title is a truncation for log display; body is the full prompt.
    """
    max_title = 60
    title = prompt[:max_title].rstrip() + "…" if len(prompt) > max_title else prompt
    return WorkSpec(title=title, body=prompt)
