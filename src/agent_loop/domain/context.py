from dataclasses import dataclass

from agent_loop.domain.types import Config


@dataclass(frozen=True)
class AppContext:
    """The fully wired application context passed to every feature pipeline.

    Starts with config only. AgentBackend, VCSBackend, and IssueTracker
    fields will be added here when concrete adapters are extracted from io/shell.py.
    """

    config: Config
