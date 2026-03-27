from pathlib import Path

from agent_loop.domain.errors import AgentError, SubprocessError
from agent_loop.io.transports.process import run

# Read-only tools for analysis and review (no filesystem writes or shell execution)
READ_ONLY_TOOLS = "Read,Glob,Grep"
# Tools needed to implement fixes (scoped to project dir via cwd)
EDIT_TOOLS = "Read,Write,Edit,MultiEdit,Glob,Grep,Bash"


class ClaudeCliBackend:
    """AgentBackend that calls the claude CLI as a subprocess."""

    def __init__(self, project_dir: Path, allowed_tools: str = EDIT_TOOLS) -> None:
        self._project_dir = project_dir
        self._allowed_tools = allowed_tools

    def run(self, prompt: str) -> str:
        try:
            return run(
                ["claude", "-p", prompt, "--allowedTools", self._allowed_tools],
                cwd=self._project_dir,
            )
        except SubprocessError as exc:
            raise AgentError(stderr=exc.stderr) from exc
