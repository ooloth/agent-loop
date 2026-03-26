from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict


class Label(StrEnum):
    """Issue labels tracking origin and workflow state.

    Agent issue lifecycle:
      agent-reported, needs-human-review  →  ready-to-fix  →  agent-fix-in-progress  →  closed by PR merge

    Human issue lifecycle:
      ready-to-fix  →  agent-fix-in-progress  →  closed by PR merge
    """

    # Permanent — origin
    AGENT_REPORTED = "agent-reported"

    # Transient — workflow state
    NEEDS_HUMAN_REVIEW = "needs-human-review"
    READY_TO_FIX = "ready-to-fix"

    # Permanent — lock
    AGENT_FIX_IN_PROGRESS = "agent-fix-in-progress"


LABEL_DESCRIPTIONS = {
    Label.AGENT_REPORTED: "Issue found by automated analysis",
    Label.NEEDS_HUMAN_REVIEW: "Awaiting human triage",
    Label.READY_TO_FIX: "Approved for agent to fix",
    Label.AGENT_FIX_IN_PROGRESS: "Agent is working on a fix",
}


class _ConfigRequired(TypedDict):
    max_iterations: int
    context: str


class Config(_ConfigRequired, total=False):
    # Prompt overrides — optional because commands fall back to their own defaults
    # when these keys are absent. Users can set them in .agent-loop.yml.
    analyze_prompt: str
    fix_prompt_template: str
    review_prompt: str


DEFAULT_CONFIG: Config = {
    "max_iterations": 5,
    "context": "",
}


@dataclass(frozen=True)
class Issue:
    """A work item in the issue tracker."""

    number: int
    title: str
    body: str
    labels: frozenset[str]


@dataclass(frozen=True)
class FoundIssue:
    """An issue discovered by the analyzer, before it is filed in a tracker."""

    title: str
    body: str
    labels: list[str] = field(default_factory=list)
