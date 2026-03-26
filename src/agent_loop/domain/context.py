from dataclasses import dataclass
from pathlib import Path

from agent_loop.domain.config import Config
from agent_loop.domain.protocols import AgentBackend, IssueTracker


@dataclass(frozen=True)
class AppContext:
    """The fully wired application context passed to every feature pipeline."""

    project_dir: Path
    config: Config
    agent: AgentBackend
    tracker: IssueTracker
