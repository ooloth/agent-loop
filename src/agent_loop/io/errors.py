"""IO-layer exceptions for infrastructure concerns (subprocesses, network, etc.)."""

from agent_loop.domain.errors import AgentLoopError


class SubprocessError(AgentLoopError):
    """A subprocess (git, gh, etc.) returned a non-zero exit code."""

    def __init__(self, cmd: str, stderr: str = "") -> None:
        """Store the failed command and its stderr."""
        self.cmd = cmd
        self.stderr = stderr
        detail = f"\n{stderr.rstrip()}" if stderr else ""
        super().__init__(f"Command failed: {cmd}{detail}")
