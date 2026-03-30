from dataclasses import dataclass
from pathlib import Path

from agent_loop.domain.config import Config
from agent_loop.domain.ports.issue_tracker import IssueTracker
from agent_loop.domain.ports.vcs_backend import VCSBackend


@dataclass(frozen=True)
class AppContext:
    """The fully wired application context passed to every feature pipeline.

    Commands construct their own agent backends from config — the context
    provides project-level resources (VCS, issue tracker, config) only.
    """

    project_dir: Path
    config: Config
    tracker: IssueTracker
    vcs: VCSBackend
